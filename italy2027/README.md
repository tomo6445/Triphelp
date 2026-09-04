# Italy 2027 — Business Class Mission Control

A local web app that plans and tracks getting you from **Perth to Italy in business class**,
departing around **24 Sep 2027** and returning **8 Oct 2027**, for the least money possible.

It runs entirely on your own machine. Nothing is sent anywhere except to the flight-data
sources you choose to enable.

---

## Run it

```bash
cd italy2027
python3 app.py
```

Then open **http://127.0.0.1:8777**

That's the whole install. It uses only the Python 3 standard library — no `pip install` needed
to get going. Python 3.9+ (any recent macOS or Linux has this; on Windows install Python from
python.org and use `py app.py`).

Leave the terminal window open and it keeps checking in the background on the interval you set
(default every 12 hours). Close it and nothing is lost — all state lives in `tracker.db`.

Handy flags:

```bash
python3 app.py --check-now     # run one check cycle, print the result, exit
python3 app.py --verbose       # log every HTTP request
ITALY_PORT=9000 python3 app.py # different port
```

Or just double-click `start.command` (macOS/Linux) or `start.bat` (Windows).

---

## Making it fully autonomous

The app works without any of this — it just falls back to reminding you to sweep manually,
more often as your release dates get close. To have it collect data on its own:

**Cash fares, free, no account (recommended):**

```bash
pip3 install fast-flights
```

Restart the app. Checks now pull business-class quotes from Google Flights for every `Cash`
watch on your list and chart them over time.

**Cash fares, second source (optional):** create a free account at
`developers.amadeus.com`, make a Self-Service app, and paste the API key and secret into
Settings. Useful as a cross-check; the free tier is limited so don't set the check interval
below a few hours.

**Award seats, automatic (optional, paid):** a seats.aero Pro subscription includes a Partner
API key. Paste it into Settings and the app monitors reward-seat availability across every
program on your watch list, and raises a critical alert the moment business seats appear on
your dates. This is the single upgrade that makes the whole thing hands-off, because award
seats are the thing that appears and disappears within hours.

**Email alerts (optional):** fill in the SMTP section in Settings. For Gmail use
`smtp.gmail.com`, port 587, and an app password rather than your real one. Every new alert
is then pushed to your inbox as it fires.

Note: for 2027 dates, the cash-fare providers will return nothing until the airlines actually
open schedules and inventory for sale — that's correct behaviour, not a bug. The award-release
countdown tells you when to expect each program to start returning something.

---

## The tabs

| Tab | What it does |
|---|---|
| **Dashboard** | Countdown to departure, countdown to every award release date, best fare seen, points runway, next actions. |
| **Plan** | The full playbook as dated tasks, generated from your travel dates. Tick things off; add your own. |
| **Options** | Every realistic way of making this trip, priced in points and cash, with a live cents-per-point valuation against the current cash benchmark. |
| **Cash fares** | Every quote ever logged, charted, with target and instant-buy thresholds. |
| **Award seats** | Watch list, availability history, and a place to log what you find. |
| **Points & cards** | The credit card sequence, status tracking, and a projection of your points balance against the target. |
| **Alerts** | Everything the rules have fired, newest first. |
| **Search links** | One-click searches pre-filled with your dates, plus the deal feeds worth watching. |
| **Settings** | Dates, targets, API keys, email, and a full JSON export. |

---

## The alert rules

The app raises an alert automatically when:

- a logged fare is at or below your **target price** (default A$6,000)
- a logged fare is at or below your **instant-buy price** (default A$5,500) — this one is marked critical
- **award seats appear** in business on your dates
- an **award release date** is 30, 14, 7, 3, 1 or 0 days away
- a **planned task falls due** or goes 3 / 7 / 14 days overdue
- (manual mode only) a **sweep is due** — weekly normally, daily once a release window is within 45 days

Alerts are de-duplicated within a 20-hour window, so nothing spams you.

---

## Changing anything

- **Different dates or cities?** Settings → change them → *Regenerate plan from dates*. Every
  release-date countdown and every dated task recomputes.
- **Different cards or points targets?** Points & cards tab — edit, add, delete.
- **Different routes to watch?** Award seats tab → watch list.
- **Starting fresh?** Delete `tracker.db` and restart. Seed data reloads.
- **Backing up?** `tracker.db` is the whole thing. Copy it anywhere. Settings → Export also
  dumps everything as JSON.

The starting figures live in `seed.py` — award charts, card offers, release windows, the
playbook, the route options. All plain Python dictionaries with comments, so they're easy to
update as offers change. Award charts and card bonuses move a few times a year; check them
against your own research every few months.

---

## What this app does not do

It does not book anything, hold your card details, or log into any airline account for you.
It watches, prices, reminds, and keeps the record. The booking is yours to make — which
matters, because the moment a seat appears you want a human clicking, not a script.
