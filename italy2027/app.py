#!/usr/bin/env python3
"""
Italy 2027 - Business Class Mission Control
===========================================

A local, self-contained planner and tracker for getting from Perth to Italy in
business class in September/October 2027, for as little cash as possible.

Runs on the Python 3 standard library alone. No pip install required.

    python3 app.py            -> http://127.0.0.1:8777

Optional extras (the app works fully without them):
    pip install fast-flights  -> automatic Google Flights cash-fare polling
    Amadeus API key           -> second cash-fare source
    seats.aero API key        -> automatic award-seat polling
"""

import json
import os
import re
import sqlite3
import ssl
import sys
import threading
import time
import smtplib
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta
from email.message import EmailMessage
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import seed

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "tracker.db")
STATIC_DIR = os.path.join(BASE_DIR, "static")
HOST = os.environ.get("ITALY_HOST", "127.0.0.1")
PORT = int(os.environ.get("ITALY_PORT", "8777"))

DEFAULT_SETTINGS = {
    "origin": "PER",
    "destinations": "FCO,MXP",
    "depart_date": "2027-09-24",
    "return_date": "2027-10-08",
    "date_flex_days": "4",
    "cabin": "business",
    "passengers": "1",
    "target_cash_aud": "6000",
    "instant_buy_cash_aud": "5500",
    "points_target_program": "Velocity Frequent Flyer",
    "points_target": "278000",
    "check_interval_hours": "12",
    "amadeus_key": "",
    "amadeus_secret": "",
    "seats_aero_key": "",
    "email_enabled": "0",
    "smtp_host": "",
    "smtp_port": "587",
    "smtp_user": "",
    "smtp_pass": "",
    "email_to": "",
    "auto_checks_enabled": "1",
}

_lock = threading.Lock()


# ------------------------------------------------------------------ database ---
def db():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);

CREATE TABLE IF NOT EXISTS milestones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT, detail TEXT, category TEXT,
    due_date TEXT, status TEXT DEFAULT 'pending',
    generated INTEGER DEFAULT 0, sort_key TEXT
);

CREATE TABLE IF NOT EXISTS options (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT, program TEXT, airline TEXT, routing TEXT,
    points_ow INTEGER, taxes_return_aud REAL, distance_mi INTEGER,
    priority INTEGER, notes TEXT, active INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS fares (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT, route TEXT, airline TEXT, cabin TEXT,
    price_aud REAL, depart_date TEXT, return_date TEXT,
    source TEXT, url TEXT, notes TEXT
);

CREATE TABLE IF NOT EXISTS award_checks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT, program TEXT, route TEXT, flight_date TEXT, cabin TEXT,
    seats INTEGER, points INTEGER, taxes_aud REAL, source TEXT, notes TEXT
);

CREATE TABLE IF NOT EXISTS watches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    program TEXT, origin TEXT, dest TEXT, cabin TEXT, enabled INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS cards (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT, issuer TEXT, currency TEXT, converts_to TEXT,
    convert_ratio REAL, bonus_points INTEGER, min_spend REAL,
    spend_days INTEGER, annual_fee REAL, priority INTEGER,
    status TEXT DEFAULT 'planned', applied_date TEXT, approved_date TEXT,
    spend_progress REAL DEFAULT 0, bonus_received_date TEXT, notes TEXT
);

CREATE TABLE IF NOT EXISTS points_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT, program TEXT, balance INTEGER, note TEXT
);

CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT, kind TEXT, severity TEXT, message TEXT, seen INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS jobs (
    name TEXT PRIMARY KEY, last_run TEXT, last_result TEXT
);
"""


def init_db():
    fresh = not os.path.exists(DB_PATH)
    conn = db()
    conn.executescript(SCHEMA)
    for k, v in DEFAULT_SETTINGS.items():
        conn.execute("INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)", (k, v))
    if conn.execute("SELECT COUNT(*) c FROM options").fetchone()["c"] == 0:
        for o in seed.OPTIONS:
            codes = re.split(r"[- ]+", o["routing"].split("/")[0])
            codes = [c for c in codes if c in seed.AIRPORTS]
            conn.execute(
                """INSERT INTO options(name,program,airline,routing,points_ow,
                   taxes_return_aud,distance_mi,priority,notes)
                   VALUES(?,?,?,?,?,?,?,?,?)""",
                (o["name"], o["program"], o["airline"], o["routing"], o["points_ow"],
                 o["taxes_return_aud"], seed.route_distance(codes) if len(codes) > 1 else 0,
                 o["priority"], o["notes"]))
    if conn.execute("SELECT COUNT(*) c FROM cards").fetchone()["c"] == 0:
        for c in seed.CARDS:
            conn.execute(
                """INSERT INTO cards(name,issuer,currency,converts_to,convert_ratio,
                   bonus_points,min_spend,spend_days,annual_fee,priority,notes)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                (c["name"], c["issuer"], c["currency"], c["converts_to"], c["convert_ratio"],
                 c["bonus_points"], c["min_spend"], c["spend_days"], c["annual_fee"],
                 c["priority"], c["notes"]))
    if conn.execute("SELECT COUNT(*) c FROM watches").fetchone()["c"] == 0:
        for w in seed.WATCHES:
            conn.execute("INSERT INTO watches(program,origin,dest,cabin) VALUES(?,?,?,?)",
                         (w["program"], w["origin"], w["dest"], w["cabin"]))
    conn.commit()
    conn.close()
    regenerate_milestones()
    if fresh:
        log_alert("system", "info", "Mission control initialised. Plan generated from your travel dates.")


def get_settings():
    conn = db()
    rows = conn.execute("SELECT key,value FROM settings").fetchall()
    conn.close()
    s = dict(DEFAULT_SETTINGS)
    s.update({r["key"]: r["value"] for r in rows})
    return s


def set_settings(updates):
    conn = db()
    for k, v in updates.items():
        conn.execute("INSERT INTO settings(key,value) VALUES(?,?) "
                     "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (k, str(v)))
    conn.commit()
    conn.close()


def log_alert(kind, severity, message):
    conn = db()
    conn.execute("INSERT INTO alerts(ts,kind,severity,message) VALUES(?,?,?,?)",
                 (datetime.now().isoformat(timespec="seconds"), kind, severity, message))
    conn.commit()
    conn.close()


# ----------------------------------------------------------------- milestones ---
def parse_date(s, fallback=None):
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except Exception:
        return fallback


def regenerate_milestones():
    """Rebuild the auto-generated plan from the current travel dates.
    Manually added milestones and completed statuses are preserved."""
    s = get_settings()
    dep = parse_date(s["depart_date"], date(2027, 9, 24))
    ret = parse_date(s["return_date"], date(2027, 10, 8))
    today = date.today()

    conn = db()
    done = {r["title"]: r["status"] for r in
            conn.execute("SELECT title,status FROM milestones WHERE generated=1").fetchall()}
    conn.execute("DELETE FROM milestones WHERE generated=1")

    rows = []
    for item in seed.PLAYBOOK:
        if item["anchor"] == "today":
            due = today + timedelta(days=item["offset"])
        else:
            due = dep - timedelta(days=item["offset"])
        rows.append((item["title"], item["detail"], item["category"], due.isoformat(),
                     done.get(item["title"], "pending"), 1, due.isoformat()))

    # one release-date milestone per program, for the return leg too
    for p in seed.PROGRAMS:
        r_out = dep - timedelta(days=p["release_days"])
        r_ret = ret - timedelta(days=p["release_days"])
        title = f"{p['name']}: return leg opens (T-{p['release_days']})"
        rows.append((title,
                     f"Reward seats for your {ret.strftime('%d %b %Y')} return leg load around now. {p['notes']}",
                     "Award release", r_ret.isoformat(), done.get(title, "pending"), 1, r_ret.isoformat()))
        if p["code"] not in ("QF", "VA", "SQ", "QR", "CX"):
            title2 = f"{p['name']}: outbound opens (T-{p['release_days']})"
            rows.append((title2,
                         f"Reward seats for your {dep.strftime('%d %b %Y')} outbound load around now. {p['notes']}",
                         "Award release", r_out.isoformat(), done.get(title2, "pending"), 1, r_out.isoformat()))

    conn.executemany(
        """INSERT INTO milestones(title,detail,category,due_date,status,generated,sort_key)
           VALUES(?,?,?,?,?,?,?)""", rows)
    conn.commit()
    conn.close()


def release_dates():
    s = get_settings()
    dep = parse_date(s["depart_date"], date(2027, 9, 24))
    ret = parse_date(s["return_date"], date(2027, 10, 8))
    today = date.today()
    out = []
    for p in seed.PROGRAMS:
        od = dep - timedelta(days=p["release_days"])
        rd = ret - timedelta(days=p["release_days"])
        out.append({
            "program": p["name"], "code": p["code"], "currency": p["currency"],
            "release_days": p["release_days"], "notes": p["notes"], "url": p["search_url"],
            "outbound_release": od.isoformat(), "return_release": rd.isoformat(),
            "days_to_outbound": (od - today).days, "days_to_return": (rd - today).days,
        })
    out.sort(key=lambda x: x["outbound_release"])
    return out


# ------------------------------------------------------------------ providers ---
def http_json(url, data=None, headers=None, timeout=25):
    ctx = ssl.create_default_context()
    req = urllib.request.Request(url, data=data, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
        return json.loads(r.read().decode("utf-8"))


def amadeus_token(key, secret):
    body = urllib.parse.urlencode({
        "grant_type": "client_credentials", "client_id": key, "client_secret": secret
    }).encode()
    res = http_json("https://api.amadeus.com/v1/security/oauth2/token", data=body,
                    headers={"Content-Type": "application/x-www-form-urlencoded"})
    return res.get("access_token")


def fetch_amadeus(s, origin, dest, dep, ret):
    """Cash fares via the Amadeus Self-Service API. Returns a list of dicts."""
    key, secret = s.get("amadeus_key"), s.get("amadeus_secret")
    if not key or not secret:
        return []
    token = amadeus_token(key, secret)
    q = urllib.parse.urlencode({
        "originLocationCode": origin, "destinationLocationCode": dest,
        "departureDate": dep, "returnDate": ret,
        "adults": s.get("passengers", "1"), "travelClass": "BUSINESS",
        "currencyCode": "AUD", "max": "8", "nonStop": "false",
    })
    res = http_json("https://api.amadeus.com/v2/shopping/flight-offers?" + q,
                    headers={"Authorization": "Bearer " + token})
    out = []
    for offer in res.get("data", [])[:8]:
        try:
            price = float(offer["price"]["grandTotal"])
            carriers = {seg["carrierCode"] for it in offer["itineraries"]
                        for seg in it["segments"]}
            out.append({"price_aud": price, "airline": "/".join(sorted(carriers)),
                        "source": "amadeus", "url": ""})
        except Exception:
            continue
    return out


def _price_of(obj):
    """fast-flights returns price as an int in v3 and a display string in v2."""
    v = getattr(obj, "price", None)
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v) or None
    digits = re.sub(r"[^\d]", "", str(v).split(".")[0])
    return float(digits) if digits else None


def _airline_of(obj):
    a = getattr(obj, "airlines", None)
    if isinstance(a, (list, tuple)) and a:
        return "/".join(str(x) for x in a[:3])
    return str(getattr(obj, "name", "") or "?")


def fetch_fast_flights(s, origin, dest, dep, ret):
    """Cash fares via the optional fast-flights package (Google Flights).

    Supports both the v3 API (create_query / FlightQuery, result is a list)
    and the older v2 API (FlightData kwargs, result.flights)."""
    try:
        import fast_flights as ff
    except Exception:
        return []

    pax = int(s.get("passengers", "1") or 1)
    rows = []
    try:
        if hasattr(ff, "create_query") and hasattr(ff, "FlightQuery"):
            q = ff.create_query(
                flights=[ff.FlightQuery(date=dep, from_airport=origin, to_airport=dest),
                         ff.FlightQuery(date=ret, from_airport=dest, to_airport=origin)],
                seat="business", trip="round-trip",
                passengers=ff.Passengers(adults=pax), currency="AUD")
            result = ff.get_flights(q)
            rows = list(result)
        else:  # pragma: no cover - older releases
            result = ff.get_flights(
                flight_data=[ff.FlightData(date=dep, from_airport=origin, to_airport=dest),
                             ff.FlightData(date=ret, from_airport=dest, to_airport=origin)],
                trip="round-trip", seat="business",
                passengers=ff.Passengers(adults=pax), fetch_mode="fallback")
            rows = list(getattr(result, "flights", []) or [])
    except Exception as e:
        raise RuntimeError(f"fast-flights: {e}")

    out = []
    for f in rows[:8]:
        price = _price_of(f)
        if not price:
            continue
        out.append({"price_aud": price, "airline": _airline_of(f),
                    "source": "google-flights", "url": ""})
    return out


def fetch_seats_aero(s, origin, dest, start, end, cabin="business"):
    """Award availability via the seats.aero Partner API (needs a Pro key)."""
    key = s.get("seats_aero_key")
    if not key:
        return []
    q = urllib.parse.urlencode({
        "origin_airport": origin, "destination_airport": dest,
        "start_date": start, "end_date": end, "take": "50",
    })
    res = http_json("https://seats.aero/partnerapi/search?" + q,
                    headers={"Partner-Authorization": key, "Accept": "application/json"})
    out = []
    for row in res.get("data", []):
        try:
            if cabin == "business" and not row.get("JAvailable"):
                continue
            out.append({
                "program": row.get("Source", "?"),
                "flight_date": row.get("Date", ""),
                "seats": int(row.get("JRemainingSeats") or 0),
                "points": int(row.get("JMileageCost") or 0),
                "taxes_aud": float(row.get("JTotalTaxes") or 0) / 100.0,
                "source": "seats.aero",
                "notes": row.get("JAirlines", ""),
            })
        except Exception:
            continue
    return out


def date_window(s):
    dep = parse_date(s["depart_date"], date(2027, 9, 24))
    ret = parse_date(s["return_date"], date(2027, 10, 8))
    flex = int(s.get("date_flex_days") or 0)
    return dep, ret, flex


# --------------------------------------------------------------- check runner ---
def run_checks(manual=False):
    """The autonomous heartbeat: poll every enabled source, store results,
    evaluate alert rules. Safe to call at any time; never raises."""
    s = get_settings()
    dep, ret, flex = date_window(s)
    summary = {"fares": 0, "awards": 0, "errors": [], "alerts": []}
    now = datetime.now().isoformat(timespec="seconds")

    if dep <= date.today():
        summary["errors"].append("Departure date is in the past - update it in Settings.")

    conn = db()
    watches = conn.execute("SELECT * FROM watches WHERE enabled=1").fetchall()
    conn.close()

    for w in watches:
        origin, dest = w["origin"], w["dest"]
        if w["program"] == "Cash":
            rows = []
            for fn in (fetch_fast_flights, fetch_amadeus):
                try:
                    rows.extend(fn(s, origin, dest, dep.isoformat(), ret.isoformat()))
                except Exception as e:
                    summary["errors"].append(f"{fn.__name__} {origin}-{dest}: {e}")
            conn = db()
            for r in rows:
                conn.execute(
                    """INSERT INTO fares(ts,route,airline,cabin,price_aud,depart_date,
                       return_date,source,url,notes) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                    (now, f"{origin}-{dest}", r["airline"], "business", r["price_aud"],
                     dep.isoformat(), ret.isoformat(), r["source"], r.get("url", ""), "auto"))
                summary["fares"] += 1
            conn.commit()
            conn.close()
        else:
            try:
                rows = fetch_seats_aero(s, origin, dest,
                                        (dep - timedelta(days=flex)).isoformat(),
                                        (dep + timedelta(days=flex)).isoformat())
            except Exception as e:
                rows = []
                summary["errors"].append(f"seats.aero {origin}-{dest}: {e}")
            conn = db()
            for r in rows:
                conn.execute(
                    """INSERT INTO award_checks(ts,program,route,flight_date,cabin,seats,
                       points,taxes_aud,source,notes) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                    (now, r["program"], f"{origin}-{dest}", r["flight_date"], "business",
                     r["seats"], r["points"], r["taxes_aud"], r["source"], r["notes"]))
                summary["awards"] += 1
            conn.commit()
            conn.close()

    summary["providers"] = {
        "google_flights": _has_fast_flights(),
        "amadeus": bool(s.get("amadeus_key") and s.get("amadeus_secret")),
        "seats_aero": bool(s.get("seats_aero_key")),
    }
    summary["automatic"] = any(summary["providers"].values())
    summary["alerts"] = evaluate_alerts(s)
    conn = db()
    conn.execute("INSERT INTO jobs(name,last_run,last_result) VALUES(?,?,?) "
                 "ON CONFLICT(name) DO UPDATE SET last_run=excluded.last_run, "
                 "last_result=excluded.last_result",
                 ("checks", now, json.dumps(summary)))
    conn.commit()
    conn.close()
    return summary


def evaluate_alerts(s=None):
    """Alert rules. Deduplicated so the same alert is not raised twice a day."""
    s = s or get_settings()
    today = date.today()
    fired = []
    conn = db()
    recent = {r["message"] for r in conn.execute(
        "SELECT message FROM alerts WHERE ts > ?",
        ((datetime.now() - timedelta(hours=20)).isoformat(),)).fetchall()}

    target = float(s.get("target_cash_aud") or 0)
    instant = float(s.get("instant_buy_cash_aud") or 0)
    best = conn.execute(
        "SELECT * FROM fares WHERE ts > ? ORDER BY price_aud ASC LIMIT 1",
        ((datetime.now() - timedelta(days=2)).isoformat(),)).fetchone()
    if best:
        p = best["price_aud"]
        if instant and p <= instant:
            fired.append(("price", "critical",
                          f"BUY NOW: {best['route']} business return A${p:,.0f} on {best['airline']} "
                          f"- at or below your instant-buy price of A${instant:,.0f}."))
        elif target and p <= target:
            fired.append(("price", "high",
                          f"Target hit: {best['route']} business return A${p:,.0f} on {best['airline']} "
                          f"- below your A${target:,.0f} target."))

    for a in conn.execute(
            "SELECT * FROM award_checks WHERE ts > ? AND seats > 0",
            ((datetime.now() - timedelta(days=1)).isoformat(),)).fetchall():
        fired.append(("award", "critical",
                      f"AWARD SEATS: {a['seats']} x business {a['route']} on {a['flight_date']} "
                      f"via {a['program']} for {a['points']:,} points."))

    for r in release_dates():
        for label, d in (("outbound", r["days_to_outbound"]), ("return", r["days_to_return"])):
            if d in (30, 14, 7, 3, 1):
                fired.append(("release", "high",
                              f"{r['program']} {label} reward seats open in {d} day(s) "
                              f"({r['outbound_release'] if label == 'outbound' else r['return_release']})."))
            elif d == 0:
                fired.append(("release", "critical",
                              f"TODAY: {r['program']} {label} reward seats open. Search now."))

    # If no automatic data source is configured, prompt a manual sweep instead.
    # Cadence tightens as release dates and departure approach.
    have_auto = (_has_fast_flights()
                 or (s.get("amadeus_key") and s.get("amadeus_secret"))
                 or s.get("seats_aero_key"))
    if not have_auto:
        rels = release_dates()
        hot = any(0 <= r["days_to_outbound"] <= 45 or 0 <= r["days_to_return"] <= 45 for r in rels)
        dep = parse_date(s["depart_date"], date(2027, 9, 24))
        hot = hot or (dep - today).days <= 150
        if hot or today.weekday() == 5:
            fired.append(("manual", "medium",
                          f"Manual sweep due ({today.isoformat()}): run the searches on the "
                          f"Search links tab and log what you find under Cash fares / Award seats. "
                          f"{'Release window is close.' if hot else 'Weekly check.'}"))

    for m in conn.execute(
            "SELECT * FROM milestones WHERE status='pending' AND due_date <= ?",
            (today.isoformat(),)).fetchall():
        overdue = (today - parse_date(m["due_date"], today)).days
        if overdue in (0, 3, 7, 14):
            fired.append(("task", "medium" if overdue else "high",
                          f"Task due: {m['title']}" + (f" ({overdue} days overdue)" if overdue else "")))

    new = []
    for kind, sev, msg in fired:
        if msg in recent:
            continue
        conn.execute("INSERT INTO alerts(ts,kind,severity,message) VALUES(?,?,?,?)",
                     (datetime.now().isoformat(timespec="seconds"), kind, sev, msg))
        new.append({"kind": kind, "severity": sev, "message": msg})
    conn.commit()
    conn.close()

    if new and s.get("email_enabled") == "1":
        try:
            send_email(s, new)
        except Exception as e:
            log_alert("system", "low", f"Email send failed: {e}")
    return new


def send_email(s, alerts):
    msg = EmailMessage()
    msg["Subject"] = f"[Italy 2027] {len(alerts)} new alert(s)"
    msg["From"] = s["smtp_user"]
    msg["To"] = s["email_to"]
    msg.set_content("\n\n".join(f"[{a['severity'].upper()}] {a['message']}" for a in alerts))
    with smtplib.SMTP(s["smtp_host"], int(s["smtp_port"]), timeout=30) as srv:
        srv.starttls()
        srv.login(s["smtp_user"], s["smtp_pass"])
        srv.send_message(msg)


def scheduler_loop():
    """Background thread: runs checks on the configured interval, forever."""
    time.sleep(5)
    while True:
        try:
            s = get_settings()
            if s.get("auto_checks_enabled") == "1":
                conn = db()
                row = conn.execute("SELECT last_run FROM jobs WHERE name='checks'").fetchone()
                conn.close()
                interval = max(1.0, float(s.get("check_interval_hours") or 12))
                due = True
                if row and row["last_run"]:
                    last = datetime.fromisoformat(row["last_run"])
                    due = (datetime.now() - last) >= timedelta(hours=interval)
                if due:
                    run_checks()
        except Exception as e:
            try:
                log_alert("system", "low", f"Scheduler error: {e}")
            except Exception:
                pass
        time.sleep(600)


# ---------------------------------------------------------------- computation ---
def points_projection():
    """Expected points balance over time from the card plan plus logged balances."""
    conn = db()
    cards = [dict(r) for r in conn.execute("SELECT * FROM cards ORDER BY priority").fetchall()]
    logged = [dict(r) for r in conn.execute(
        "SELECT * FROM points_log ORDER BY ts").fetchall()]
    conn.close()
    s = get_settings()
    target_prog = s.get("points_target_program", "Velocity Frequent Flyer")
    target_word = "Velocity" if "Velocity" in target_prog else "Qantas"

    banked = 0
    latest = {}
    for l in logged:
        latest[l["program"]] = l["balance"]
    for prog, bal in latest.items():
        if target_word.lower() in prog.lower():
            banked += bal

    committed, planned = [], []
    for c in cards:
        if target_word.lower() not in (c["converts_to"] or "").lower():
            continue
        if c["status"] == "skipped":
            continue
        value = int(round(c["bonus_points"] * (c["convert_ratio"] or 1)))
        eta = None
        if c["applied_date"]:
            applied = parse_date(c["applied_date"])
            if applied:
                eta = (applied + timedelta(days=(c["spend_days"] or 90) + 21)).isoformat()
        entry = {"card": c["name"], "points": value, "status": c["status"],
                 "eta": eta, "annual_fee": c["annual_fee"], "min_spend": c["min_spend"]}
        # bonus_received points are assumed to show up in a logged balance already
        if c["status"] in ("applied", "approved", "spending"):
            committed.append(entry)
        elif c["status"] == "planned":
            planned.append(entry)

    target = int(s.get("points_target") or 0)
    in_flight = sum(p["points"] for p in committed)
    on_paper = sum(p["points"] for p in planned)
    projected = banked + in_flight
    return {
        "program": target_prog, "target": target, "banked": banked,
        "pipeline": committed, "planned": planned,
        "in_flight": in_flight, "on_paper": on_paper,
        "projected": projected, "potential": projected + on_paper,
        "shortfall": max(0, target - projected),
        "potential_shortfall": max(0, target - projected - on_paper),
        "annual_fees": sum((c["annual_fee"] or 0) for c in cards
                           if c["status"] in ("applied", "approved", "spending", "bonus_received")),
    }


def option_value():
    """Value each redemption option in cents per point against the live cash benchmark."""
    conn = db()
    opts = [dict(r) for r in conn.execute(
        "SELECT * FROM options WHERE active=1 ORDER BY priority").fetchall()]
    best = conn.execute("SELECT price_aud FROM fares ORDER BY ts DESC, price_aud ASC LIMIT 1").fetchone()
    median = conn.execute("SELECT AVG(price_aud) a FROM fares").fetchone()
    conn.close()
    benchmark = (best["price_aud"] if best else None) or (median["a"] if median and median["a"] else 8500)
    for o in opts:
        pts = (o["points_ow"] or 0) * 2
        o["points_return"] = pts
        o["cash_benchmark"] = round(benchmark)
        if pts:
            saved = benchmark - (o["taxes_return_aud"] or 0)
            o["cpp"] = round(saved / pts * 100, 2)
        else:
            o["cpp"] = None
    return {"options": opts, "benchmark": round(benchmark)}


def dashboard():
    s = get_settings()
    dep, ret, flex = date_window(s)
    today = date.today()
    conn = db()
    fares = [dict(r) for r in conn.execute(
        "SELECT * FROM fares ORDER BY ts DESC LIMIT 400").fetchall()]
    best = conn.execute("SELECT * FROM fares ORDER BY price_aud ASC LIMIT 1").fetchone()
    recent_best = conn.execute(
        "SELECT * FROM fares WHERE ts > ? ORDER BY price_aud ASC LIMIT 1",
        ((datetime.now() - timedelta(days=7)).isoformat(),)).fetchone()
    next_tasks = [dict(r) for r in conn.execute(
        "SELECT * FROM milestones WHERE status='pending' ORDER BY due_date LIMIT 6").fetchall()]
    overdue = conn.execute(
        "SELECT COUNT(*) c FROM milestones WHERE status='pending' AND due_date < ?",
        (today.isoformat(),)).fetchone()["c"]
    unseen = conn.execute("SELECT COUNT(*) c FROM alerts WHERE seen=0").fetchone()["c"]
    job = conn.execute("SELECT * FROM jobs WHERE name='checks'").fetchone()
    seats = [dict(r) for r in conn.execute(
        "SELECT * FROM award_checks WHERE seats>0 ORDER BY ts DESC LIMIT 20").fetchall()]
    conn.close()

    return {
        "today": today.isoformat(),
        "depart": dep.isoformat(), "return": ret.isoformat(),
        "days_to_departure": (dep - today).days,
        "trip_nights": (ret - dep).days,
        "flex_days": flex,
        "window": [(dep - timedelta(days=flex)).isoformat(), (dep + timedelta(days=flex)).isoformat()],
        "releases": release_dates(),
        "best_ever_fare": dict(best) if best else None,
        "best_recent_fare": dict(recent_best) if recent_best else None,
        "target_cash": float(s.get("target_cash_aud") or 0),
        "instant_buy": float(s.get("instant_buy_cash_aud") or 0),
        "fares": fares,
        "next_tasks": next_tasks,
        "overdue": overdue,
        "unseen_alerts": unseen,
        "points": points_projection(),
        "options": option_value(),
        "seats_found": seats,
        "last_check": job["last_run"] if job else None,
        "last_result": json.loads(job["last_result"]) if job and job["last_result"] else None,
        "auto_enabled": s.get("auto_checks_enabled") == "1",
        "providers": {
            "fast_flights": _has_fast_flights(),
            "amadeus": bool(s.get("amadeus_key") and s.get("amadeus_secret")),
            "seats_aero": bool(s.get("seats_aero_key")),
        },
        "tips": seed.TIPS,
        "accelerators": seed.ACCELERATORS,
    }


def _has_fast_flights():
    try:
        import fast_flights  # noqa: F401
        return True
    except Exception:
        return False


def search_links():
    """One-click deep links for the manual checks the app cannot automate."""
    s = get_settings()
    dep, ret, flex = date_window(s)
    d, r = dep.isoformat(), ret.isoformat()
    origin = s["origin"]
    links = []
    for dest in [x.strip() for x in s["destinations"].split(",") if x.strip()]:
        links.append({
            "label": f"Google Flights {origin}-{dest} business",
            "group": "Cash",
            "url": (f"https://www.google.com/travel/flights?q=Flights%20to%20{dest}%20from%20"
                    f"{origin}%20on%20{d}%20through%20{r}%20business%20class"),
        })
        links.append({
            "label": f"Skyscanner {origin}-{dest} (whole month)",
            "group": "Cash",
            "url": (f"https://www.skyscanner.com.au/transport/flights/{origin.lower()}/"
                    f"{dest.lower()}/{dep.strftime('%y%m')}/{ret.strftime('%y%m')}/"
                    f"?cabinclass=business&adults={s.get('passengers','1')}"),
        })
        links.append({
            "label": f"Matrix ITA {origin}-{dest}",
            "group": "Cash",
            "url": "https://matrix.itasoftware.com/search",
        })
    links += [
        {"label": "Velocity reward seat search (books SQ at 139k)", "group": "Award",
         "url": "https://www.velocityfrequentflyer.com/"},
        {"label": "KrisFlyer award search (Saver 131.5k)", "group": "Award",
         "url": "https://www.singaporeair.com/en_UK/us/ppsclub-krisflyer/use-miles/redeem-miles/"},
        {"label": "KrisFlyer miles calculator", "group": "Award",
         "url": "https://www.singaporeair.com/en_UK/us/ppsclub-krisflyer/use-miles/miles-calculator/"},
        {"label": "Cathay / Asia Miles award search", "group": "Award",
         "url": "https://www.cathaypacific.com/cx/en_AU/book-a-trip/redeem-flights/redeem-flight-awards.html"},
        {"label": "Qantas Classic Reward finder (Cathay via HKG)", "group": "Award",
         "url": "https://flightrewardfinder.qantas.com/"},
        {"label": "Qatar Privilege Club (fallback)", "group": "Award",
         "url": "https://www.qatarairways.com/en/Privilege-Club.html"},
        {"label": "SQ schedule: Singapore to Milan", "group": "Award",
         "url": "https://www.flightsfrom.com/SIN-MXP"},
        {"label": "China Southern (cheapest cash via Guangzhou)", "group": "Cash",
         "url": "https://www.csair.com/au/en/"},
        {"label": "seats.aero award search", "group": "Award",
         "url": f"https://seats.aero/search?origins={origin}&destinations=FCO,MXP&cabin=business"},
        {"label": "seats.aero release-date reference", "group": "Award",
         "url": "https://seats.aero/tools/releases"},
        {"label": "Point Hacks - best card offers", "group": "Points",
         "url": "https://www.pointhacks.com.au/credit-cards/"},
        {"label": "Australian Frequent Flyer - card offers", "group": "Points",
         "url": "https://www.australianfrequentflyer.com.au/best-qantas-credit-card-offers/"},
        {"label": "Amex transfer partners + ratios", "group": "Points",
         "url": "https://www.australianfrequentflyer.com.au/amex-membership-rewards-transfer-partners/"},
        {"label": "I Know The Pilot (deal feed)", "group": "Deals",
         "url": "https://iknowthepilot.com.au/"},
        {"label": "Australian Frequent Flyer deals forum", "group": "Deals",
         "url": "https://www.australianfrequentflyer.com.au/community/forums/flight-deals.55/"},
        {"label": "Beat That Flight", "group": "Deals", "url": "https://beatthatflight.com.au/"},
    ]
    return links


# ---------------------------------------------------------------- HTTP server ---
class Handler(BaseHTTPRequestHandler):
    server_version = "Italy2027/1.0"

    def log_message(self, fmt, *args):
        if "--verbose" in sys.argv:
            sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    # -- helpers
    def _send(self, code, body, ctype="application/json"):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, default=str).encode()
        elif isinstance(body, str):
            body = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        if not n:
            return {}
        try:
            return json.loads(self.rfile.read(n).decode())
        except Exception:
            return {}

    def _static(self, path):
        name = path.lstrip("/") or "index.html"
        full = os.path.normpath(os.path.join(STATIC_DIR, name))
        if not full.startswith(STATIC_DIR) or not os.path.isfile(full):
            return self._send(404, "not found", "text/plain")
        ctype = {"html": "text/html; charset=utf-8", "js": "text/javascript",
                 "css": "text/css", "svg": "image/svg+xml"}.get(name.rsplit(".", 1)[-1],
                                                                "application/octet-stream")
        with open(full, "rb") as f:
            self._send(200, f.read(), ctype)

    # -- routes
    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        p, q = u.path, urllib.parse.parse_qs(u.query)
        try:
            if p == "/favicon.ico":
                return self._send(200, b"", "image/x-icon")
            if p == "/api/dashboard":
                return self._send(200, dashboard())
            if p == "/api/settings":
                return self._send(200, get_settings())
            if p == "/api/milestones":
                conn = db()
                rows = [dict(r) for r in conn.execute(
                    "SELECT * FROM milestones ORDER BY due_date, id").fetchall()]
                conn.close()
                return self._send(200, rows)
            if p == "/api/cards":
                conn = db()
                rows = [dict(r) for r in conn.execute(
                    "SELECT * FROM cards ORDER BY priority, id").fetchall()]
                conn.close()
                return self._send(200, {"cards": rows, "projection": points_projection(),
                                        "accelerators": seed.ACCELERATORS})
            if p == "/api/fares":
                conn = db()
                rows = [dict(r) for r in conn.execute(
                    "SELECT * FROM fares ORDER BY ts DESC, price_aud ASC LIMIT 500").fetchall()]
                conn.close()
                return self._send(200, rows)
            if p == "/api/awards":
                conn = db()
                rows = [dict(r) for r in conn.execute(
                    "SELECT * FROM award_checks ORDER BY ts DESC LIMIT 300").fetchall()]
                watches = [dict(r) for r in conn.execute("SELECT * FROM watches").fetchall()]
                conn.close()
                return self._send(200, {"checks": rows, "watches": watches,
                                        "releases": release_dates()})
            if p == "/api/options":
                return self._send(200, option_value())
            if p == "/api/alerts":
                conn = db()
                rows = [dict(r) for r in conn.execute(
                    "SELECT * FROM alerts ORDER BY ts DESC LIMIT 200").fetchall()]
                conn.close()
                return self._send(200, rows)
            if p == "/api/points":
                conn = db()
                rows = [dict(r) for r in conn.execute(
                    "SELECT * FROM points_log ORDER BY ts DESC LIMIT 200").fetchall()]
                conn.close()
                return self._send(200, {"log": rows, "projection": points_projection()})
            if p == "/api/links":
                return self._send(200, search_links())
            if p == "/api/export":
                conn = db()
                out = {}
                for t in ("settings", "milestones", "options", "fares", "award_checks",
                          "watches", "cards", "points_log", "alerts"):
                    out[t] = [dict(r) for r in conn.execute(f"SELECT * FROM {t}").fetchall()]
                conn.close()
                return self._send(200, out)
            if p.startswith("/api/"):
                return self._send(404, {"error": "unknown endpoint"})
            return self._static(p)
        except Exception as e:
            return self._send(500, {"error": str(e)})

    def do_POST(self):
        u = urllib.parse.urlparse(self.path)
        p = u.path
        b = self._body()
        try:
            with _lock:
                if p == "/api/settings":
                    set_settings(b)
                    if any(k in b for k in ("depart_date", "return_date")):
                        regenerate_milestones()
                    return self._send(200, get_settings())

                if p == "/api/run-checks":
                    return self._send(200, run_checks(manual=True))

                if p == "/api/fares":
                    conn = db()
                    conn.execute(
                        """INSERT INTO fares(ts,route,airline,cabin,price_aud,depart_date,
                           return_date,source,url,notes) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                        (datetime.now().isoformat(timespec="seconds"),
                         b.get("route", "PER-FCO"), b.get("airline", ""), b.get("cabin", "business"),
                         float(b.get("price_aud") or 0), b.get("depart_date", ""),
                         b.get("return_date", ""), b.get("source", "manual"),
                         b.get("url", ""), b.get("notes", "")))
                    conn.commit()
                    conn.close()
                    evaluate_alerts()
                    return self._send(200, {"ok": True})

                if p == "/api/awards":
                    conn = db()
                    conn.execute(
                        """INSERT INTO award_checks(ts,program,route,flight_date,cabin,seats,
                           points,taxes_aud,source,notes) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                        (datetime.now().isoformat(timespec="seconds"),
                         b.get("program", ""), b.get("route", ""), b.get("flight_date", ""),
                         b.get("cabin", "business"), int(b.get("seats") or 0),
                         int(b.get("points") or 0), float(b.get("taxes_aud") or 0),
                         b.get("source", "manual"), b.get("notes", "")))
                    conn.commit()
                    conn.close()
                    evaluate_alerts()
                    return self._send(200, {"ok": True})

                if p == "/api/milestones":
                    conn = db()
                    if b.get("id"):
                        fields, vals = [], []
                        for k in ("title", "detail", "category", "due_date", "status"):
                            if k in b:
                                fields.append(f"{k}=?")
                                vals.append(b[k])
                        if fields:
                            vals.append(b["id"])
                            conn.execute(f"UPDATE milestones SET {','.join(fields)} WHERE id=?", vals)
                    else:
                        conn.execute(
                            """INSERT INTO milestones(title,detail,category,due_date,status,
                               generated,sort_key) VALUES(?,?,?,?,?,0,?)""",
                            (b.get("title", "Untitled"), b.get("detail", ""),
                             b.get("category", "Custom"), b.get("due_date", date.today().isoformat()),
                             "pending", b.get("due_date", "")))
                    conn.commit()
                    conn.close()
                    return self._send(200, {"ok": True})

                if p == "/api/milestones/delete":
                    conn = db()
                    conn.execute("DELETE FROM milestones WHERE id=? AND generated=0", (b.get("id"),))
                    conn.commit()
                    conn.close()
                    return self._send(200, {"ok": True})

                if p == "/api/cards":
                    conn = db()
                    if b.get("id"):
                        fields, vals = [], []
                        for k in ("status", "applied_date", "approved_date", "spend_progress",
                                  "bonus_received_date", "notes", "bonus_points", "min_spend",
                                  "annual_fee", "name", "issuer", "converts_to", "convert_ratio"):
                            if k in b:
                                fields.append(f"{k}=?")
                                vals.append(b[k])
                        if fields:
                            vals.append(b["id"])
                            conn.execute(f"UPDATE cards SET {','.join(fields)} WHERE id=?", vals)
                    else:
                        conn.execute(
                            """INSERT INTO cards(name,issuer,currency,converts_to,convert_ratio,
                               bonus_points,min_spend,spend_days,annual_fee,priority,status,notes)
                               VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                            (b.get("name", ""), b.get("issuer", ""), b.get("currency", ""),
                             b.get("converts_to", "Velocity"), float(b.get("convert_ratio") or 1),
                             int(b.get("bonus_points") or 0), float(b.get("min_spend") or 0),
                             int(b.get("spend_days") or 90), float(b.get("annual_fee") or 0),
                             int(b.get("priority") or 99), b.get("status", "planned"),
                             b.get("notes", "")))
                    conn.commit()
                    conn.close()
                    return self._send(200, {"ok": True})

                if p == "/api/cards/delete":
                    conn = db()
                    conn.execute("DELETE FROM cards WHERE id=?", (b.get("id"),))
                    conn.commit()
                    conn.close()
                    return self._send(200, {"ok": True})

                if p == "/api/points":
                    conn = db()
                    conn.execute("INSERT INTO points_log(ts,program,balance,note) VALUES(?,?,?,?)",
                                 (b.get("ts") or datetime.now().isoformat(timespec="seconds"),
                                  b.get("program", ""), int(b.get("balance") or 0),
                                  b.get("note", "")))
                    conn.commit()
                    conn.close()
                    return self._send(200, {"ok": True})

                if p == "/api/watches":
                    conn = db()
                    if b.get("delete"):
                        conn.execute("DELETE FROM watches WHERE id=?", (b.get("id"),))
                    elif b.get("id"):
                        conn.execute("UPDATE watches SET enabled=? WHERE id=?",
                                     (1 if b.get("enabled") else 0, b["id"]))
                    else:
                        conn.execute(
                            "INSERT INTO watches(program,origin,dest,cabin) VALUES(?,?,?,?)",
                            (b.get("program", "Cash"), b.get("origin", "PER"),
                             b.get("dest", "FCO"), b.get("cabin", "business")))
                    conn.commit()
                    conn.close()
                    return self._send(200, {"ok": True})

                if p == "/api/alerts/seen":
                    conn = db()
                    conn.execute("UPDATE alerts SET seen=1")
                    conn.commit()
                    conn.close()
                    return self._send(200, {"ok": True})

                if p == "/api/regenerate":
                    regenerate_milestones()
                    return self._send(200, {"ok": True})

                return self._send(404, {"error": "unknown endpoint"})
        except Exception as e:
            return self._send(500, {"error": str(e)})


def main():
    init_db()
    if "--check-now" in sys.argv:
        print(json.dumps(run_checks(manual=True), indent=2))
        return
    threading.Thread(target=scheduler_loop, daemon=True).start()
    srv = ThreadingHTTPServer((HOST, PORT), Handler)
    url = f"http://{HOST}:{PORT}"
    print("=" * 62)
    print("  ITALY 2027 - BUSINESS CLASS MISSION CONTROL")
    print("=" * 62)
    s = get_settings()
    dep = parse_date(s["depart_date"], date(2027, 9, 24))
    print(f"  Target: {s['origin']} -> {s['destinations']}  {s['depart_date']} / {s['return_date']}")
    print(f"  {(dep - date.today()).days} days to departure")
    print(f"  Auto-checks: {'on' if s['auto_checks_enabled'] == '1' else 'off'} "
          f"(every {s['check_interval_hours']}h)")
    print(f"\n  Open  ->  {url}\n")
    print("  Ctrl+C to stop.")
    print("=" * 62)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
