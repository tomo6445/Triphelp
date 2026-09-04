/* Italy 2027 - Mission Control front end. Vanilla JS, no build step, no deps. */
(function () {
  "use strict";

  // ------------------------------------------------------------- helpers ---
  const $ = (sel, el) => (el || document).querySelector(sel);
  const $$ = (sel, el) => Array.from((el || document).querySelectorAll(sel));

  async function getJSON(url) {
    const r = await fetch(url, { cache: "no-store" });
    if (!r.ok) throw new Error(url + " -> " + r.status);
    return r.json();
  }
  async function postJSON(url, body) {
    const r = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {}),
    });
    if (!r.ok) throw new Error(url + " -> " + r.status);
    return r.json();
  }

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    }[c]));
  }
  function money(n) {
    n = Number(n || 0);
    return "A$" + n.toLocaleString(undefined, { maximumFractionDigits: 0 });
  }
  function num(n) {
    return Number(n || 0).toLocaleString();
  }
  function fmtDate(s) {
    if (!s) return "-";
    try {
      const d = new Date(String(s).slice(0, 10) + "T00:00:00");
      if (isNaN(d.getTime())) return s;
      return d.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
    } catch (e) { return s; }
  }
  function fmtDateTime(s) {
    if (!s) return "-";
    try {
      const d = new Date(s);
      if (isNaN(d.getTime())) return s;
      return d.toLocaleString(undefined, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
    } catch (e) { return s; }
  }
  function relDays(n) {
    n = Number(n);
    if (n === 0) return "today";
    if (n === 1) return "in 1 day";
    if (n === -1) return "1 day ago";
    if (n > 0) return `in ${n} days`;
    return `${-n} days ago`;
  }
  function todayISO() {
    return new Date().toISOString().slice(0, 10);
  }

  let toastTimer = null;
  function toast(msg, isError) {
    const el = $("#toast");
    el.textContent = msg;
    el.classList.toggle("error", !!isError);
    el.classList.add("show");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => el.classList.remove("show"), 4500);
  }

  // ------------------------------------------------------------ SVG chart ---
  // A generic, dependency-free line chart. series: [{name, color, points:[{x:ISOdate,y:number}]}]
  function lineChart(series, opts) {
    opts = opts || {};
    const W = opts.width || 900, H = opts.height || 260;
    const padL = 56, padR = 16, padT = 16, padB = 30;
    const fmt = opts.fmt || ((v) => num(Math.round(v)));
    const nonEmpty = series.filter((s) => s.points && s.points.length);
    if (!nonEmpty.length) {
      return '<div class="empty-note">No data logged yet.</div>';
    }
    const allX = [], allY = [];
    nonEmpty.forEach((s) => s.points.forEach((p) => { allX.push(+new Date(p.x)); allY.push(p.y); }));
    if (opts.target) allY.push(opts.target);
    let minX = Math.min(...allX), maxX = Math.max(...allX);
    if (minX === maxX) { minX -= 86400000; maxX += 86400000; }
    let minY = Math.min(0, ...allY), maxY = Math.max(...allY);
    if (minY === maxY) maxY = minY + 1;
    const pad = (maxY - minY) * 0.08;
    maxY += pad;

    const xs = (x) => padL + ((+new Date(x) - minX) / (maxX - minX)) * (W - padL - padR);
    const ys = (y) => H - padB - ((y - minY) / (maxY - minY)) * (H - padT - padB);

    let svg = `<svg class="chart" viewBox="0 0 ${W} ${H}" preserveAspectRatio="xMidYMid meet">`;

    // gridlines
    const rows = 4;
    for (let i = 0; i <= rows; i++) {
      const gy = padT + (i / rows) * (H - padT - padB);
      const val = maxY - (i / rows) * (maxY - minY);
      svg += `<line class="gridline" x1="${padL}" y1="${gy.toFixed(1)}" x2="${W - padR}" y2="${gy.toFixed(1)}"/>`;
      svg += `<text class="axis-label" x="4" y="${(gy + 3).toFixed(1)}">${fmt(val)}</text>`;
    }

    // x-axis date labels (first, middle, last)
    const xTicks = [minX, (minX + maxX) / 2, maxX];
    xTicks.forEach((t) => {
      const lbl = new Date(t).toLocaleDateString(undefined, { day: "numeric", month: "short" });
      svg += `<text class="axis-label" x="${xs(t).toFixed(1)}" y="${H - 8}" text-anchor="middle">${lbl}</text>`;
    });

    if (opts.target) {
      const ty = ys(opts.target);
      svg += `<line class="target-line" x1="${padL}" y1="${ty.toFixed(1)}" x2="${W - padR}" y2="${ty.toFixed(1)}"/>`;
    }

    nonEmpty.forEach((s) => {
      const pts = s.points.slice().sort((a, b) => +new Date(a.x) - +new Date(b.x));
      const path = pts.map((p, i) => `${i ? "L" : "M"}${xs(p.x).toFixed(1)},${ys(p.y).toFixed(1)}`).join(" ");
      svg += `<path class="series-line" d="${path}" stroke="${s.color}"/>`;
      pts.forEach((p) => {
        svg += `<circle class="series-point" cx="${xs(p.x).toFixed(1)}" cy="${ys(p.y).toFixed(1)}" r="3.5" fill="${s.color}">` +
          `<title>${esc(s.name)}: ${fmt(p.y)} on ${fmtDate(String(p.x).slice(0, 10))}${p.label ? " - " + esc(p.label) : ""}</title></circle>`;
      });
    });

    svg += "</svg>";
    let legend = '<div class="chart-legend">';
    nonEmpty.forEach((s) => {
      legend += `<span><span class="swatch" style="background:${s.color}"></span>${esc(s.name)}</span>`;
    });
    if (opts.target) legend += `<span><span class="swatch" style="background:var(--warn)"></span>Target: ${fmt(opts.target)}</span>`;
    legend += "</div>";
    return svg + legend;
  }

  const PALETTE = ["#4fa3ff", "#3ecf8e", "#e3b341", "#f0883e", "#c792ea", "#f85149", "#6ecbff"];

  function dailyMinSeriesByRoute(fares) {
    const byRoute = {};
    fares.forEach((f) => {
      const day = String(f.ts).slice(0, 10);
      const key = f.route || "?";
      byRoute[key] = byRoute[key] || {};
      if (!(day in byRoute[key]) || f.price_aud < byRoute[key][day].y) {
        byRoute[key][day] = { x: day, y: f.price_aud, label: f.airline };
      }
    });
    return Object.keys(byRoute).sort().map((route, i) => ({
      name: route, color: PALETTE[i % PALETTE.length],
      points: Object.values(byRoute[route]),
    }));
  }

  function pointsLogSeries(log) {
    const byProgram = {};
    log.forEach((r) => {
      byProgram[r.program] = byProgram[r.program] || [];
      byProgram[r.program].push({ x: String(r.ts).slice(0, 10), y: r.balance, label: r.note });
    });
    return Object.keys(byProgram).sort().map((prog, i) => ({
      name: prog, color: PALETTE[i % PALETTE.length], points: byProgram[prog],
    }));
  }

  // ------------------------------------------------------------ dashboard ---
  let lastDashboard = null;

  async function refreshHeader() {
    try {
      const d = await getJSON("/api/dashboard");
      lastDashboard = d;
      $("#hs-route").textContent = `${esc(d.depart)} -> ${esc(d.return)} (+/-${d.flex_days}d)`;
      $("#hs-days").textContent = relDays(d.days_to_departure);
      const nextRel = (d.releases || []).filter((r) => r.days_to_outbound >= 0)
        .sort((a, b) => a.days_to_outbound - b.days_to_outbound)[0];
      $("#hs-release").textContent = nextRel ? `${nextRel.program} ${relDays(nextRel.days_to_outbound)}` : "-";
      $("#hs-lastcheck").textContent = d.last_check ? fmtDateTime(d.last_check) : "never";
      const badgeAlerts = $("#badge-alerts");
      if (d.unseen_alerts > 0) { badgeAlerts.hidden = false; badgeAlerts.textContent = d.unseen_alerts; }
      else badgeAlerts.hidden = true;
      const badgePlan = $("#badge-plan");
      if (d.overdue > 0) { badgePlan.hidden = false; badgePlan.textContent = d.overdue; }
      else badgePlan.hidden = true;
      return d;
    } catch (e) {
      console.error("dashboard refresh failed", e);
      return null;
    }
  }

  function providerPill(label, on) {
    return `<span class="pill ${on ? "on" : "off"}"><span class="dot"></span>${label}: ${on ? "on" : "off"}</span>`;
  }

  function renderDashboard(d) {
    const el = $("#tab-dashboard");
    const nextRel = (d.releases || []).filter((r) => r.days_to_outbound >= 0)
      .sort((a, b) => a.days_to_outbound - b.days_to_outbound)[0];
    const bestFare = d.best_ever_fare;
    const anyProvider = d.providers.fast_flights || d.providers.amadeus || d.providers.seats_aero;

    let html = "";
    html += `<div class="kpi-row">
      <div class="kpi"><div class="label">Days to departure</div><div class="value">${d.days_to_departure}</div><div class="sub">${fmtDate(d.depart)} - ${fmtDate(d.return)} (${d.trip_nights} nights)</div></div>
      <div class="kpi"><div class="label">Next award release</div><div class="value">${nextRel ? relDays(nextRel.days_to_outbound) : "-"}</div><div class="sub">${nextRel ? esc(nextRel.program) : "no upcoming releases"}</div></div>
      <div class="kpi"><div class="label">Best fare logged</div><div class="value">${bestFare ? money(bestFare.price_aud) : "-"}</div><div class="sub">${bestFare ? esc(bestFare.route) + " on " + esc(bestFare.airline) : "log one on Cash fares"}</div></div>
      <div class="kpi"><div class="label">Points still needed</div><div class="value">${num(d.points.shortfall)}</div><div class="sub">of ${num(d.points.target)} ${esc(d.points.program)}</div></div>
    </div>`;

    html += `<div class="pill-row">
      ${providerPill("Google Flights", d.providers.fast_flights)}
      ${providerPill("Amadeus", d.providers.amadeus)}
      ${providerPill("seats.aero", d.providers.seats_aero)}
      ${providerPill("Auto-checks", d.auto_enabled)}
    </div>`;

    if (!anyProvider) {
      html += `<div class="warning-card"><b>Manual mode.</b> No data provider is configured, so nothing is fetched
        automatically. The app instead reminds you to sweep the searches yourself, more often as release dates
        approach - see the <a href="#links">Search links</a> tab, and log what you find on Cash fares / Award seats.
        Add <code>fast-flights</code> (free) or a seats.aero key in <a href="#settings">Settings</a> to automate it.</div>`;
    }

    html += `<div class="cards-2col">
      <div class="card">
        <h2>Award release countdown</h2>
        <div class="table-wrap"><table><thead><tr><th>Program</th><th>Currency</th><th>Outbound opens</th><th>Return opens</th></tr></thead><tbody>
        ${(d.releases || []).map((r) => `<tr><td>${esc(r.program)}</td><td>${esc(r.currency)}</td>
          <td>${fmtDate(r.outbound_release)}<br><span class="meta" style="color:var(--text-faint)">${relDays(r.days_to_outbound)}</span></td>
          <td>${fmtDate(r.return_release)}<br><span class="meta" style="color:var(--text-faint)">${relDays(r.days_to_return)}</span></td></tr>`).join("")}
        </tbody></table></div>
      </div>
      <div class="card">
        <h2>Next actions</h2>
        ${(d.next_tasks || []).length ? d.next_tasks.map((t) => taskRowHtml(t)).join("") : '<div class="empty-note">Nothing pending.</div>'}
      </div>
    </div>`;

    const fareSeries = dailyMinSeriesByRoute(d.fares || []);
    html += `<div class="card"><h2>Cash fare history</h2>${lineChart(fareSeries, { fmt: money, target: d.target_cash })}</div>`;

    const p = d.points;
    const target = p.target || 1;
    const bankedPct = Math.min(100, (p.banked / target) * 100);
    const appliedPct = Math.min(100 - bankedPct, (p.in_flight / target) * 100);
    const plannedPct = Math.min(100 - bankedPct - appliedPct, (p.on_paper / target) * 100);
    html += `<div class="card">
      <h2>Points runway - ${esc(p.program)}</h2>
      <div class="stack-bar">
        ${bankedPct > 0 ? `<div class="seg banked" style="width:${bankedPct}%">${num(p.banked)}</div>` : ""}
        ${appliedPct > 0 ? `<div class="seg applied" style="width:${appliedPct}%">+${num(p.in_flight)}</div>` : ""}
        ${plannedPct > 0 ? `<div class="seg planned" style="width:${plannedPct}%">+${num(p.on_paper)}</div>` : ""}
        ${bankedPct + appliedPct + plannedPct < 100 ? `<div class="seg empty"></div>` : ""}
      </div>
      <div class="legend">
        <span><span class="swatch" style="background:var(--good)"></span>Banked ${num(p.banked)}</span>
        <span><span class="swatch" style="background:var(--brand)"></span>Applied for ${num(p.in_flight)}</span>
        <span><span class="swatch" style="background:var(--neutral)"></span>Planned ${num(p.on_paper)}</span>
        <span>Target ${num(p.target)}</span>
      </div>
    </div>`;

    if ((d.seats_found || []).length) {
      html += `<div class="card"><h2>Award seats found</h2><div class="table-wrap"><table><thead>
        <tr><th>When logged</th><th>Program</th><th>Route</th><th>Flight date</th><th>Seats</th><th>Points</th><th>Taxes</th></tr></thead><tbody>
        ${d.seats_found.map((a) => `<tr><td>${fmtDateTime(a.ts)}</td><td>${esc(a.program)}</td><td>${esc(a.route)}</td><td>${fmtDate(a.flight_date)}</td>
          <td><b style="color:var(--good)">${a.seats}</b></td><td>${num(a.points)}</td><td>${money(a.taxes_aud)}</td></tr>`).join("")}
        </tbody></table></div></div>`;
    }

    html += `<div class="card"><h2>Tips</h2><ul class="tips-list">${(d.tips || []).map((t) => `<li>${esc(t)}</li>`).join("")}</ul></div>`;

    el.innerHTML = html;
  }

  function taskRowHtml(t) {
    const overdue = t.due_date < todayISO();
    const soon = !overdue && t.due_date <= addDaysISO(todayISO(), 14);
    return `<div class="task-row ${overdue ? "overdue" : soon ? "soon" : ""}">
      <input type="checkbox" data-action="toggle-milestone" data-id="${t.id}" ${t.status === "done" ? "checked" : ""}>
      <div>
        <div class="title">${esc(t.title)}</div>
        <div class="detail">${esc(t.detail || "")}</div>
      </div>
      <div class="due">${fmtDate(t.due_date)}<br>${relDays(daysBetween(todayISO(), t.due_date))}</div>
    </div>`;
  }

  function daysBetween(fromISO, toISOStr) {
    const a = new Date(fromISO + "T00:00:00"), b = new Date(String(toISOStr).slice(0, 10) + "T00:00:00");
    return Math.round((b - a) / 86400000);
  }
  function addDaysISO(iso, n) {
    const d = new Date(iso + "T00:00:00");
    d.setDate(d.getDate() + n);
    return d.toISOString().slice(0, 10);
  }

  // ----------------------------------------------------------------- plan ---
  const CATEGORY_ORDER = ["Setup", "Points", "Award release", "Cash", "Decision", "Trip", "Custom"];

  async function renderPlan() {
    const el = $("#tab-plan");
    const rows = await getJSON("/api/milestones");
    const showCompleted = localStorage.getItem("italy2027.showCompleted") === "1";

    const byCat = {};
    rows.forEach((r) => {
      const cat = CATEGORY_ORDER.includes(r.category) ? r.category : "Custom";
      byCat[cat] = byCat[cat] || [];
      byCat[cat].push(r);
    });

    let html = `<div class="actions-row">
      <label class="checkbox-row"><input type="checkbox" id="show-completed" ${showCompleted ? "checked" : ""}> Show completed</label>
      <button id="regenerate-btn">Regenerate plan from dates</button>
    </div>`;

    CATEGORY_ORDER.forEach((cat) => {
      let items = (byCat[cat] || []).slice().sort((a, b) => (a.due_date || "").localeCompare(b.due_date || ""));
      if (!showCompleted) items = items.filter((i) => i.status !== "done");
      if (!items.length) return;
      html += `<div class="category-heading">${esc(cat)}</div><div class="card">`;
      items.forEach((t) => {
        const overdue = t.status !== "done" && t.due_date < todayISO();
        const soon = t.status !== "done" && !overdue && t.due_date <= addDaysISO(todayISO(), 14);
        html += `<div class="task-row ${t.status === "done" ? "done" : overdue ? "overdue" : soon ? "soon" : ""}">
          <input type="checkbox" data-action="toggle-milestone" data-id="${t.id}" ${t.status === "done" ? "checked" : ""}>
          <div>
            <div class="title">${esc(t.title)}${!t.generated ? ' <span class="tag">custom</span>' : ""}</div>
            <div class="detail">${esc(t.detail || "")}</div>
          </div>
          <div class="due">
            ${fmtDate(t.due_date)}<br>${relDays(daysBetween(todayISO(), t.due_date))}
            ${!t.generated ? `<br><button class="small danger" data-action="delete-milestone" data-id="${t.id}">delete</button>` : ""}
          </div>
        </div>`;
      });
      html += `</div>`;
    });

    html += `<div class="card"><h2>Add your own</h2>
      <form id="add-milestone-form" class="grid-form">
        <div class="field"><label>Title</label><input name="title" required></div>
        <div class="field"><label>Category</label>
          <select name="category">${CATEGORY_ORDER.map((c) => `<option>${esc(c)}</option>`).join("")}</select>
        </div>
        <div class="field"><label>Due date</label><input type="date" name="due_date" value="${todayISO()}" required></div>
        <div class="field"><label>Detail</label><input name="detail"></div>
        <div class="field"><button class="primary" type="submit">Add task</button></div>
      </form>
    </div>`;

    el.innerHTML = html;

    $("#show-completed").addEventListener("change", (e) => {
      localStorage.setItem("italy2027.showCompleted", e.target.checked ? "1" : "0");
      renderPlan();
    });
    $("#regenerate-btn").addEventListener("click", async () => {
      await postJSON("/api/regenerate", {});
      toast("Plan regenerated from current dates.");
      renderPlan();
      refreshHeader();
    });
    $("#add-milestone-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      const fd = new FormData(e.target);
      await postJSON("/api/milestones", Object.fromEntries(fd.entries()));
      toast("Task added.");
      renderPlan();
    });
  }

  // -------------------------------------------------------------- options ---
  async function renderOptions() {
    const el = $("#tab-options");
    const data = await getJSON("/api/options");
    let html = `<p class="section-intro">Cents-per-point (cpp) values each option against the current cash
      benchmark of <b>${money(data.benchmark)}</b> (the most recent fare you've logged, or the average of all
      logged fares, or A$8,500 if nothing has been logged yet). 3.0c or better is good, 2.0-3.0c is fair, below
      2.0c is weak - you'd do better paying cash.</p>`;
    data.options.forEach((o) => {
      const tagClass = o.cpp == null ? "" : o.cpp >= 3 ? "good" : o.cpp >= 2 ? "neutral" : "warn";
      html += `<div class="card option-card">
        <div class="opt-head"><h2>#${o.priority} ${esc(o.name)}</h2><span class="tag">${esc(o.program)}</span></div>
        <div class="section-intro" style="margin-bottom:6px">${esc(o.airline)} - ${esc(o.routing)} - ${o.distance_mi ? num(o.distance_mi) + " mi" : "distance n/a"}</div>
        <div class="opt-figures">
          <div><span>Points return</span><span>${o.points_return ? num(o.points_return) : "-"}</span></div>
          <div><span>Cash outlay (taxes)</span><span>${money(o.taxes_return_aud)}</span></div>
          <div><span>Cents per point</span><span class="tag ${tagClass}">${o.cpp != null ? o.cpp.toFixed(2) + "c" : "n/a"}</span></div>
        </div>
        <div class="opt-notes">${esc(o.notes || "")}</div>
      </div>`;
    });
    el.innerHTML = html;
  }

  // ---------------------------------------------------------------- fares ---
  async function renderFares() {
    const el = $("#tab-fares");
    const rows = await getJSON("/api/fares");
    const s = await getJSON("/api/settings");
    const series = dailyMinSeriesByRoute(rows);
    let html = `<div class="card"><h2>Fare history</h2>${lineChart(series, { fmt: money, target: Number(s.target_cash_aud) })}</div>`;

    html += `<div class="card"><h2>Log a fare</h2>
      <form id="add-fare-form" class="grid-form">
        <div class="field"><label>Route</label><input name="route" placeholder="PER-FCO" value="PER-${esc((s.destinations || "FCO").split(",")[0])}" required></div>
        <div class="field"><label>Airline</label><input name="airline" placeholder="SQ"></div>
        <div class="field"><label>Price (AUD, return)</label><input name="price_aud" type="number" step="1" required></div>
        <div class="field"><label>Depart date</label><input name="depart_date" type="date" value="${esc(s.depart_date)}"></div>
        <div class="field"><label>Return date</label><input name="return_date" type="date" value="${esc(s.return_date)}"></div>
        <div class="field"><label>Source</label><input name="source" placeholder="Google Flights"></div>
        <div class="field"><label>Notes</label><input name="notes"></div>
        <div class="field"><button class="primary" type="submit">Log fare</button></div>
      </form>
    </div>`;

    html += `<div class="card"><h2>All quotes</h2><div class="table-wrap"><table><thead>
      <tr><th>Logged</th><th>Route</th><th>Airline</th><th>Price</th><th>Travel dates</th><th>Source</th><th>Notes</th></tr>
      </thead><tbody>
      ${rows.map((f) => {
        let cls = "";
        if (Number(s.instant_buy_cash_aud) && f.price_aud <= Number(s.instant_buy_cash_aud)) cls = "good";
        else if (Number(s.target_cash_aud) && f.price_aud <= Number(s.target_cash_aud)) cls = "neutral";
        return `<tr><td>${fmtDateTime(f.ts)}</td><td>${esc(f.route)}</td><td>${esc(f.airline)}</td>
          <td><span class="tag ${cls}">${money(f.price_aud)}</span></td>
          <td>${fmtDate(f.depart_date)} - ${fmtDate(f.return_date)}</td><td>${esc(f.source)}</td><td>${esc(f.notes || "")}</td></tr>`;
      }).join("") || '<tr><td colspan="7"><div class="empty-note">No fares logged yet.</div></td></tr>'}
      </tbody></table></div>
    </div>`;

    el.innerHTML = html;
    $("#add-fare-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      const fd = new FormData(e.target);
      await postJSON("/api/fares", Object.fromEntries(fd.entries()));
      toast("Fare logged.");
      renderFares();
      refreshHeader();
    });
  }

  // --------------------------------------------------------------- awards ---
  async function renderAwards() {
    const el = $("#tab-awards");
    const data = await getJSON("/api/awards");
    const s = await getJSON("/api/settings");

    let html = `<div class="card"><h2>Log an availability check</h2>
      <form id="add-award-form" class="grid-form">
        <div class="field"><label>Program</label><input name="program" placeholder="KrisFlyer" required></div>
        <div class="field"><label>Route</label><input name="route" placeholder="PER-SIN" required></div>
        <div class="field"><label>Flight date</label><input name="flight_date" type="date"></div>
        <div class="field"><label>Seats</label><input name="seats" type="number" min="0" value="0"></div>
        <div class="field"><label>Points (one way)</label><input name="points" type="number" min="0"></div>
        <div class="field"><label>Taxes (AUD)</label><input name="taxes_aud" type="number" step="1"></div>
        <div class="field"><label>Notes</label><input name="notes"></div>
        <div class="field"><button class="primary" type="submit">Log check</button></div>
      </form>
    </div>`;

    html += `<div class="card"><h2>Watch list</h2><div class="table-wrap"><table><thead>
      <tr><th>Program</th><th>Origin</th><th>Dest</th><th>Cabin</th><th>Enabled</th><th></th></tr></thead><tbody>
      ${data.watches.map((w) => `<tr><td>${esc(w.program)}</td><td>${esc(w.origin)}</td><td>${esc(w.dest)}</td><td>${esc(w.cabin)}</td>
        <td><input type="checkbox" data-action="toggle-watch" data-id="${w.id}" ${w.enabled ? "checked" : ""}></td>
        <td><button class="small danger" data-action="delete-watch" data-id="${w.id}">delete</button></td></tr>`).join("")}
      </tbody></table></div>
      <form id="add-watch-form" class="grid-form" style="margin-top:12px">
        <div class="field"><label>Program</label><input name="program" placeholder="KrisFlyer" required></div>
        <div class="field"><label>Origin</label><input name="origin" value="${esc(s.origin)}" required></div>
        <div class="field"><label>Dest</label><input name="dest" placeholder="MXP" required></div>
        <div class="field"><button class="primary" type="submit">Add watch</button></div>
      </form>
    </div>`;

    html += `<div class="card"><h2>Check history</h2><div class="table-wrap"><table><thead>
      <tr><th>Logged</th><th>Program</th><th>Route</th><th>Flight date</th><th>Seats</th><th>Points</th><th>Taxes</th><th>Source</th></tr></thead><tbody>
      ${data.checks.map((a) => `<tr ${a.seats > 0 ? 'style="background:rgba(62,207,142,0.08)"' : ""}>
        <td>${fmtDateTime(a.ts)}</td><td>${esc(a.program)}</td><td>${esc(a.route)}</td><td>${fmtDate(a.flight_date)}</td>
        <td>${a.seats > 0 ? `<b style="color:var(--good)">${a.seats}</b>` : a.seats}</td><td>${num(a.points)}</td><td>${money(a.taxes_aud)}</td><td>${esc(a.source)}</td></tr>`).join("")
        || '<tr><td colspan="8"><div class="empty-note">No checks logged yet.</div></td></tr>'}
      </tbody></table></div>
    </div>`;

    el.innerHTML = html;
    $("#add-award-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      const fd = new FormData(e.target);
      await postJSON("/api/awards", Object.fromEntries(fd.entries()));
      toast("Award check logged.");
      renderAwards();
      refreshHeader();
    });
    $("#add-watch-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      const fd = new FormData(e.target);
      await postJSON("/api/watches", Object.fromEntries(fd.entries()));
      toast("Watch added.");
      renderAwards();
    });
  }

  // --------------------------------------------------------- points/cards ---
  const CARD_STATUSES = ["planned", "applied", "approved", "spending", "bonus_received", "skipped"];

  async function renderPoints() {
    const el = $("#tab-points");
    const [cardsData, pointsData] = await Promise.all([getJSON("/api/cards"), getJSON("/api/points")]);
    const proj = cardsData.projection;

    let html = `<div class="kpi-row">
      <div class="kpi"><div class="label">Banked</div><div class="value">${num(proj.banked)}</div></div>
      <div class="kpi"><div class="label">Applied for</div><div class="value">${num(proj.in_flight)}</div><div class="sub">projected ${num(proj.projected)}</div></div>
      <div class="kpi"><div class="label">Still needed</div><div class="value">${num(proj.shortfall)}</div></div>
      <div class="kpi"><div class="label">If every planned card lands</div><div class="value">${num(proj.potential)}</div><div class="sub">shortfall then: ${num(proj.potential_shortfall)}</div></div>
    </div>`;

    const pct = Math.min(100, Math.round((proj.projected / (proj.target || 1)) * 100));
    html += `<div class="card"><h2>${esc(proj.program)} - progress to ${num(proj.target)}</h2>
      <div class="stack-bar"><div class="seg banked" style="width:${pct}%">${pct}%</div>${pct < 100 ? '<div class="seg empty"></div>' : ""}</div>
    </div>`;

    html += `<div class="card"><h2>Card sequence</h2><div class="table-wrap"><table><thead>
      <tr><th>#</th><th>Card</th><th>Issuer</th><th>Bonus</th><th>-&gt; ${esc(proj.program.split(" ")[0])}</th><th>Min spend</th><th>Fee</th><th>Status</th><th>Applied</th><th></th></tr></thead><tbody>
      ${cardsData.cards.map((c) => `<tr>
        <td>${c.priority}</td>
        <td>${esc(c.name)}<div class="meta" style="color:var(--text-faint);font-size:11px">${esc(c.notes || "")}</div></td>
        <td>${esc(c.issuer)}</td>
        <td>${num(c.bonus_points)} ${esc(c.currency)}</td>
        <td>${num(Math.round(c.bonus_points * (c.convert_ratio || 1)))}</td>
        <td>${money(c.min_spend)} / ${c.spend_days}d</td>
        <td>${money(c.annual_fee)}</td>
        <td><select class="status-select" data-action="card-status" data-id="${c.id}">
          ${CARD_STATUSES.map((st) => `<option value="${st}" ${c.status === st ? "selected" : ""}>${st.replace("_", " ")}</option>`).join("")}
        </select></td>
        <td><input type="date" data-action="card-applied" data-id="${c.id}" value="${c.applied_date || ""}"></td>
        <td><button class="small danger" data-action="delete-card" data-id="${c.id}">delete</button></td>
      </tr>`).join("")}
      </tbody></table></div>

      <form id="add-card-form" class="grid-form" style="margin-top:12px">
        <div class="field"><label>Card name</label><input name="name" required></div>
        <div class="field"><label>Issuer</label><input name="issuer"></div>
        <div class="field"><label>Currency</label><input name="currency"></div>
        <div class="field"><label>Converts to</label><input name="converts_to" value="Velocity"></div>
        <div class="field"><label>Convert ratio</label><input name="convert_ratio" type="number" step="0.1" value="1"></div>
        <div class="field"><label>Bonus points</label><input name="bonus_points" type="number" required></div>
        <div class="field"><label>Min spend</label><input name="min_spend" type="number"></div>
        <div class="field"><label>Spend days</label><input name="spend_days" type="number" value="90"></div>
        <div class="field"><label>Annual fee</label><input name="annual_fee" type="number"></div>
        <div class="field"><label>Priority</label><input name="priority" type="number" value="99"></div>
        <div class="field"><button class="primary" type="submit">Add card</button></div>
      </form>
    </div>`;

    const series = pointsLogSeries(pointsData.log);
    html += `<div class="card"><h2>Balance history</h2>${lineChart(series, { fmt: num })}
      <form id="add-balance-form" class="grid-form" style="margin-top:12px">
        <div class="field"><label>Program</label><input name="program" value="Velocity Points" required></div>
        <div class="field"><label>Balance</label><input name="balance" type="number" required></div>
        <div class="field"><label>Note</label><input name="note"></div>
        <div class="field"><button class="primary" type="submit">Log balance</button></div>
      </form>
    </div>`;

    html += `<div class="card"><h2>Ways to accelerate</h2><ul class="accel-list">${cardsData.accelerators.map((a) => `<li>${esc(a)}</li>`).join("")}</ul></div>`;

    el.innerHTML = html;

    $("#add-card-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      const fd = new FormData(e.target);
      await postJSON("/api/cards", Object.fromEntries(fd.entries()));
      toast("Card added.");
      renderPoints();
    });
    $("#add-balance-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      const fd = new FormData(e.target);
      await postJSON("/api/points", Object.fromEntries(fd.entries()));
      toast("Balance logged.");
      renderPoints();
      refreshHeader();
    });
    $$('[data-action="card-status"]', el).forEach((sel) => {
      sel.addEventListener("change", async () => {
        await postJSON("/api/cards", { id: sel.dataset.id, status: sel.value });
        toast("Card status updated.");
        renderPoints();
        refreshHeader();
      });
    });
    $$('[data-action="card-applied"]', el).forEach((inp) => {
      inp.addEventListener("change", async () => {
        await postJSON("/api/cards", { id: inp.dataset.id, applied_date: inp.value });
        toast("Applied date updated.");
        renderPoints();
      });
    });
    $$('[data-action="delete-card"]', el).forEach((btn) => {
      btn.addEventListener("click", async () => {
        await postJSON("/api/cards/delete", { id: btn.dataset.id });
        toast("Card deleted.");
        renderPoints();
      });
    });
  }

  // ---------------------------------------------------------------- alerts ---
  async function renderAlerts() {
    const el = $("#tab-alerts");
    const rows = await getJSON("/api/alerts");
    let html = `<div class="actions-row"><button id="mark-read-btn">Mark all read</button></div>`;
    html += `<div class="card">${rows.length ? rows.map((a) => `
      <div class="alert-row">
        <span class="sev-dot sev-${esc(a.severity)}"></span>
        <div>
          <div class="sev-${esc(a.severity)}">${esc(a.message)}</div>
          <div class="meta">${fmtDateTime(a.ts)} - ${esc(a.kind)}${a.seen ? "" : " - <b>new</b>"}</div>
        </div>
      </div>`).join("") : '<div class="empty-note">No alerts yet.</div>'}</div>`;
    el.innerHTML = html;
    $("#mark-read-btn").addEventListener("click", async () => {
      await postJSON("/api/alerts/seen", {});
      toast("All alerts marked read.");
      renderAlerts();
      refreshHeader();
    });
  }

  // ----------------------------------------------------------------- links ---
  async function renderLinks() {
    const el = $("#tab-links");
    const links = await getJSON("/api/links");
    const groups = ["Cash", "Award", "Points", "Deals"];
    let html = "";
    groups.forEach((g) => {
      const items = links.filter((l) => l.group === g);
      if (!items.length) return;
      html += `<div class="card link-group"><h2>${esc(g)}</h2><div class="link-list">
        ${items.map((l) => `<a href="${esc(l.url)}" target="_blank" rel="noopener">${esc(l.label)} &rarr;</a>`).join("")}
      </div></div>`;
    });
    el.innerHTML = html;
  }

  // -------------------------------------------------------------- settings ---
  async function renderSettings() {
    const el = $("#tab-settings");
    const s = await getJSON("/api/settings");
    const field = (name, label, type, extra) =>
      `<div class="field"><label>${esc(label)}</label><input name="${name}" type="${type || "text"}" value="${esc(s[name] ?? "")}" ${extra || ""}></div>`;

    let html = `<form id="settings-form">
      <div class="card"><h2>Trip</h2><div class="grid-form">
        ${field("origin", "Origin")}
        ${field("destinations", "Destinations (comma-separated)")}
        ${field("depart_date", "Depart date", "date")}
        ${field("return_date", "Return date", "date")}
        ${field("date_flex_days", "Flex days", "number")}
        ${field("passengers", "Passengers", "number")}
      </div></div>

      <div class="card"><h2>Targets</h2><div class="grid-form">
        ${field("target_cash_aud", "Cash target (AUD)", "number")}
        ${field("instant_buy_cash_aud", "Instant-buy price (AUD)", "number")}
        ${field("points_target_program", "Points target program")}
        ${field("points_target", "Points target", "number")}
      </div></div>

      <div class="card"><h2>Automation</h2><div class="grid-form">
        <div class="field"><label class="checkbox-row"><input type="checkbox" name="auto_checks_enabled" value="1" ${s.auto_checks_enabled === "1" ? "checked" : ""}> Auto-checks enabled</label></div>
        ${field("check_interval_hours", "Check interval (hours)", "number")}
        ${field("seats_aero_key", "seats.aero Partner API key")}
        ${field("amadeus_key", "Amadeus API key")}
        ${field("amadeus_secret", "Amadeus API secret", "password")}
      </div></div>

      <div class="card"><h2>Email</h2><div class="grid-form">
        <div class="field"><label class="checkbox-row"><input type="checkbox" name="email_enabled" value="1" ${s.email_enabled === "1" ? "checked" : ""}> Email alerts enabled</label></div>
        ${field("smtp_host", "SMTP host")}
        ${field("smtp_port", "SMTP port", "number")}
        ${field("smtp_user", "SMTP user")}
        ${field("smtp_pass", "SMTP password", "password")}
        ${field("email_to", "Send alerts to")}
      </div></div>

      <div class="actions-row">
        <button class="primary" type="submit">Save</button>
        <button type="button" id="settings-regenerate-btn">Regenerate plan</button>
        <button type="button" id="settings-export-btn">Export JSON</button>
      </div>
    </form>`;

    el.innerHTML = html;

    $("#settings-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      const fd = new FormData(e.target);
      const body = {};
      // checkboxes only appear in FormData when checked
      body.auto_checks_enabled = fd.has("auto_checks_enabled") ? "1" : "0";
      body.email_enabled = fd.has("email_enabled") ? "1" : "0";
      for (const [k, v] of fd.entries()) {
        if (k === "auto_checks_enabled" || k === "email_enabled") continue;
        body[k] = v;
      }
      await postJSON("/api/settings", body);
      toast("Settings saved.");
      refreshHeader();
    });
    $("#settings-regenerate-btn").addEventListener("click", async () => {
      await postJSON("/api/regenerate", {});
      toast("Plan regenerated.");
      refreshHeader();
    });
    $("#settings-export-btn").addEventListener("click", () => {
      window.open("/api/export", "_blank");
    });
  }

  // ------------------------------------------------------------------ tabs ---
  const RENDERERS = {
    dashboard: async () => renderDashboard(lastDashboard || (await refreshHeader())),
    plan: renderPlan,
    options: renderOptions,
    fares: renderFares,
    awards: renderAwards,
    points: renderPoints,
    alerts: renderAlerts,
    links: renderLinks,
    settings: renderSettings,
  };

  async function showTab(name) {
    if (!RENDERERS[name]) name = "dashboard";
    $$(".tab").forEach((s) => s.classList.remove("active"));
    $$("#tabs a").forEach((a) => a.classList.remove("active"));
    const section = $("#tab-" + name);
    const link = $(`#tabs a[data-tab="${name}"]`);
    if (section) section.classList.add("active");
    if (link) link.classList.add("active");
    try {
      await RENDERERS[name]();
    } catch (e) {
      console.error("render " + name + " failed", e);
      if (section) section.innerHTML = `<div class="empty-note">Could not load this tab: ${esc(e.message)}</div>`;
    }
  }

  function currentTabName() {
    return (location.hash || "#dashboard").replace("#", "") || "dashboard";
  }

  window.addEventListener("hashchange", () => showTab(currentTabName()));

  // ------------------------------------------------------------ delegation ---
  document.addEventListener("change", async (e) => {
    const t = e.target;
    if (t.dataset && t.dataset.action === "toggle-milestone") {
      await postJSON("/api/milestones", { id: t.dataset.id, status: t.checked ? "done" : "pending" });
      toast(t.checked ? "Marked done." : "Marked pending.");
      refreshHeader();
      const active = currentTabName();
      if (active === "plan") renderPlan();
      else if (active === "dashboard") renderDashboard(await refreshHeader());
    }
    if (t.dataset && t.dataset.action === "toggle-watch") {
      await postJSON("/api/watches", { id: t.dataset.id, enabled: t.checked });
      toast("Watch updated.");
    }
  });

  document.addEventListener("click", async (e) => {
    const t = e.target.closest("[data-action]");
    if (!t) return;
    if (t.dataset.action === "delete-milestone") {
      if (!confirm("Delete this task?")) return;
      await postJSON("/api/milestones/delete", { id: t.dataset.id });
      toast("Task deleted.");
      renderPlan();
    }
    if (t.dataset.action === "delete-watch") {
      if (!confirm("Delete this watch?")) return;
      await postJSON("/api/watches", { id: t.dataset.id, delete: true });
      toast("Watch deleted.");
      renderAwards();
    }
  });

  $("#run-checks-btn").addEventListener("click", async (e) => {
    const btn = e.currentTarget;
    btn.disabled = true;
    btn.textContent = "Running...";
    try {
      const summary = await postJSON("/api/run-checks", {});
      const parts = [`${summary.fares} fare(s)`, `${summary.awards} award check(s)`];
      if (summary.alerts && summary.alerts.length) parts.push(`${summary.alerts.length} new alert(s)`);
      if (summary.errors && summary.errors.length) parts.push(`${summary.errors.length} error(s)`);
      toast("Check complete: " + parts.join(", "), summary.errors && summary.errors.length > 0);
    } catch (err) {
      toast("Run checks failed: " + err.message, true);
    } finally {
      btn.disabled = false;
      btn.textContent = "Run checks now";
      refreshHeader();
      const active = currentTabName();
      if (RENDERERS[active]) showTab(active);
    }
  });

  // -------------------------------------------------------------------- go ---
  (async function init() {
    await refreshHeader();
    await showTab(currentTabName());
    setInterval(async () => {
      await refreshHeader();
      if (currentTabName() === "dashboard") renderDashboard(lastDashboard);
    }, 120000);
  })();
})();
