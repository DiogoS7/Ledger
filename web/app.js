/* Ledger report: reads data.json (written by `python -m ledger report`) and draws
   every chart as plain SVG. No libraries. */
"use strict";

const $ = (s, el = document) => el.querySelector(s);
const NS = "http://www.w3.org/2000/svg";
const css = v => getComputedStyle(document.documentElement).getPropertyValue(v).trim();

/* ---------- formatting ---------- */
const nf0 = new Intl.NumberFormat("en-GB", { maximumFractionDigits: 0 });
const nf1 = new Intl.NumberFormat("en-GB", { maximumFractionDigits: 1, minimumFractionDigits: 1 });
const eur = v => "€" + nf0.format(v);
const eur2 = v => "€" + v.toLocaleString("en-GB", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const eurC = v => Math.abs(v) >= 1e6 ? "€" + (v / 1e6).toFixed(2) + "M" : Math.abs(v) >= 1e3 ? "€" + (v / 1e3).toFixed(v >= 1e4 ? 0 : 1) + "k" : "€" + nf0.format(v);
const pct = (v, d = 0) => (v * 100).toFixed(d) + "%";
const int = v => nf0.format(v);

/* ---------- DOM helpers (labels are data: always textContent) ---------- */
function el(tag, attrs = {}, text) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);
  if (text != null) n.textContent = text;
  return n;
}
function svgEl(tag, attrs = {}, parent) {
  const n = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);
  if (parent) parent.appendChild(n);
  return n;
}
function svgText(parent, x, y, text, attrs = {}) {
  const t = svgEl("text", { x, y, ...attrs }, parent);
  t.textContent = text;
  return t;
}

/* ---------- tooltip ---------- */
const tip = $("#tip");
function showTip(evt, head, rows) {
  tip.replaceChildren();
  if (head) tip.appendChild(el("div", { class: "tt-h" }, head));
  for (const r of rows) {
    const row = el("div", { class: "tt-r" });
    if (r.color) { const i = el("i"); i.style.background = r.color; row.appendChild(i); }
    row.appendChild(el("b", {}, r.value));
    if (r.label) row.appendChild(el("span", {}, r.label));
    tip.appendChild(row);
  }
  tip.hidden = false;
  let x, y;
  if (evt.clientX != null && evt.type !== "focus") { x = evt.clientX; y = evt.clientY; }
  else { const b = evt.target.getBoundingClientRect(); x = b.left + b.width / 2; y = b.top; }
  const w = tip.offsetWidth, h = tip.offsetHeight;
  tip.style.left = Math.min(window.innerWidth - w - 8, Math.max(8, x + 14)) + "px";
  tip.style.top = Math.max(8, y - h - 12) + "px";
}
const hideTip = () => { tip.hidden = true; };
function hover(node, fn) {
  node.setAttribute("tabindex", "0");
  node.addEventListener("pointermove", e => fn(e));
  node.addEventListener("focus", e => fn(e));
  node.addEventListener("pointerleave", hideTip);
  node.addEventListener("blur", hideTip);
}

/* ---------- scales ---------- */
function niceStep(raw) {
  const p = Math.pow(10, Math.floor(Math.log10(raw)));
  for (const m of [1, 2, 2.5, 5, 10]) if (m * p >= raw) return m * p;
  return 10 * p;
}
/* axis with round steps: returns {max, n} so every tick is a clean number */
function niceAxis(v, target = 4) {
  if (v <= 0) return { max: 1, n: target };
  const step = niceStep(v / target), n = Math.max(1, Math.ceil(v / step - 1e-9));
  return { max: step * n, n };
}
const niceMax = v => niceAxis(v).max;
const ticks = (max, n = 4) => Array.from({ length: n + 1 }, (_, i) => (max / n) * i);

/* rounded-top bar anchored to the baseline */
function barPath(x, y, w, h, r = 4) {
  if (h <= 0) return "";
  r = Math.min(r, w / 2, h);
  return `M${x},${y + h}V${y + r}Q${x},${y} ${x + r},${y}H${x + w - r}Q${x + w},${y} ${x + w},${y + r}V${y + h}Z`;
}

function frame(host, height, m) {
  host.replaceChildren();
  const W = Math.max(260, host.clientWidth);
  const svg = svgEl("svg", { viewBox: `0 0 ${W} ${height}`, height, role: "img" });
  host.appendChild(svg);
  return { svg, W, H: height, iw: W - m.l - m.r, ih: height - m.t - m.b, m };
}

function yAxis(f, max, fmt, n = 4) {
  const g = svgEl("g", { class: "axis" }, f.svg);
  for (const t of ticks(max, n)) {
    const y = f.m.t + f.ih - (t / max) * f.ih;
    svgEl("line", { x1: f.m.l, x2: f.m.l + f.iw, y1: y, y2: y, class: "gridline" }, g);
    svgText(g, f.m.l - 8, y + 4, fmt(t), { "text-anchor": "end" });
  }
}

/* ---------- bar chart (one series) ---------- */
function barChart(host, rows, o) {
  const H = parseInt(getComputedStyle(host).getPropertyValue("--h")) || 240;
  const f = frame(host, H, { t: 22, r: 8, b: 26, l: 52 });
  const ax = niceAxis(Math.max(...rows.map(o.y))), max = ax.max;
  yAxis(f, max, o.fmtAxis || o.fmt, ax.n);
  const step = f.iw / rows.length, bw = Math.max(4, Math.min(44, step - 2 - step * .28));
  const peak = rows.reduce((a, r, i) => (o.y(r) > o.y(rows[a]) ? i : a), 0);
  const every = Math.ceil(rows.length / Math.max(1, Math.floor(f.iw / 46)));
  rows.forEach((r, i) => {
    const v = o.y(r), h = (v / max) * f.ih, x = f.m.l + i * step + (step - bw) / 2, y = f.m.t + f.ih - h;
    svgEl("path", { d: barPath(x, y, bw, h), fill: o.color, class: "mark" }, f.svg);
    const hit = svgEl("rect", { x: f.m.l + i * step, y: f.m.t, width: step, height: f.ih, class: "hit" }, f.svg);
    hover(hit, e => showTip(e, o.label(r), o.tip(r)));
    const crowd = i !== rows.length - 1 && rows.length - 1 - i < every;
    if ((i % every === 0 && !crowd) || i === rows.length - 1)
      svgText(f.svg, x + bw / 2, H - 8, o.xLabel ? o.xLabel(r) : o.label(r), { class: "axis-t", "text-anchor": "middle", fill: css("--ink-3"), "font-size": 11 });
    if (i === peak) svgText(f.svg, x + bw / 2, y - 6, o.fmt(v), { class: "vlabel", "text-anchor": "middle" });
  });
}

/* ---------- line chart (several series, crosshair tooltip) ---------- */
function lineChart(host, labels, series, o = {}) {
  const H = o.height || parseInt(getComputedStyle(host).getPropertyValue("--h")) || 240;
  const f = frame(host, H, { t: 16, r: o.right ?? 92, b: 26, l: 44 });
  const ax = o.yMax ? { max: o.yMax, n: 4 } : niceAxis(Math.max(...series.flatMap(s => s.values)));
  const max = ax.max;
  yAxis(f, max, o.fmt, ax.n);
  const n = labels.length;
  const X = i => f.m.l + (n === 1 ? f.iw / 2 : (i / (n - 1)) * f.iw);
  const Y = v => f.m.t + f.ih - (v / max) * f.ih;
  const every = Math.ceil(n / Math.max(1, Math.floor(f.iw / 48)));
  labels.forEach((l, i) => {
    const crowd = i !== n - 1 && i % every === 0 && n - 1 - i < every;
    if ((i % every === 0 && !crowd) || i === n - 1) svgText(f.svg, X(i), H - 8, l, { "text-anchor": "middle", fill: css("--ink-3"), "font-size": 11 });
  });
  for (const mk of o.markers || []) {
    const x = X(mk.i);
    svgEl("line", { x1: x, x2: x, y1: f.m.t, y2: f.m.t + f.ih, stroke: css("--ink-3"), "stroke-width": 1.5, "stroke-dasharray": mk.dash || "0" }, f.svg);
    const t = svgText(f.svg, x + 6, f.m.t + 12, mk.label, { class: "vlabel", "paint-order": "stroke", stroke: css("--surface"), "stroke-width": 4 });
    if (x > f.m.l + f.iw * .7) { t.setAttribute("x", x - 6); t.setAttribute("text-anchor", "end"); }
  }
  const ends = [];
  for (const s of series) {
    const d = s.values.map((v, i) => `${i ? "L" : "M"}${X(i)},${Y(v)}`).join("");
    svgEl("path", { d, fill: "none", stroke: s.color, "stroke-width": 2, "stroke-linejoin": "round", "stroke-linecap": "round" }, f.svg);
    if (o.dots) s.values.forEach((v, i) => svgEl("circle", { cx: X(i), cy: Y(v), r: 4, fill: s.color, stroke: css("--surface"), "stroke-width": 2 }, f.svg));
    if (o.ring != null) svgEl("circle", { cx: X(o.ring), cy: Y(s.values[o.ring]), r: 7, fill: "none", stroke: s.color, "stroke-width": 2 }, f.svg);
    ends.push({ y: Y(s.values[n - 1]), s });
  }
  // direct labels at the line ends, nudged apart
  ends.sort((a, b) => a.y - b.y);
  for (let i = 1; i < ends.length; i++) if (ends[i].y - ends[i - 1].y < 14) ends[i].y = ends[i - 1].y + 14;
  if (f.m.r > 40) for (const e of ends) svgText(f.svg, X(n - 1) + 8, e.y + 4, e.s.name, { class: "dlabel" });

  const cross = svgEl("line", { y1: f.m.t, y2: f.m.t + f.ih, class: "crosshair", visibility: "hidden" }, f.svg);
  const hit = svgEl("rect", { x: f.m.l - 10, y: f.m.t, width: f.iw + 20, height: f.ih, class: "hit" }, f.svg);
  const at = e => {
    const b = f.svg.getBoundingClientRect(), sx = f.W / b.width;
    const px = e.clientX != null && e.type !== "focus" ? (e.clientX - b.left) * sx : X(n - 1);
    return Math.max(0, Math.min(n - 1, Math.round(((px - f.m.l) / f.iw) * (n - 1))));
  };
  hover(hit, e => {
    const i = at(e);
    cross.setAttribute("x1", X(i)); cross.setAttribute("x2", X(i)); cross.setAttribute("visibility", "visible");
    showTip(e, (o.headPrefix || "") + labels[i], series.map(s => ({ color: s.color, value: o.fmtTip ? o.fmtTip(s.values[i]) : o.fmt(s.values[i]), label: s.name })));
  });
  hit.addEventListener("pointerleave", () => cross.setAttribute("visibility", "hidden"));
}

/* ---------- heatmap ---------- */
function heatmap(host, cells) {
  const days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
  const f = frame(host, 230, { t: 6, r: 4, b: 40, l: 34 });
  const cw = f.iw / 24, ch = (f.ih - 6) / 7, max = Math.max(...cells.map(c => c.txns));
  const steps = ["--seq-0", "--seq-1", "--seq-2", "--seq-3", "--seq-4", "--seq-5", "--seq-6", "--seq-7"].map(css);
  for (const c of cells) {
    const k = Math.min(7, Math.floor((c.txns / max) * 7.999));
    const r = svgEl("rect", { x: f.m.l + c.hour * cw + 1, y: f.m.t + c.weekday * ch + 1, width: cw - 2, height: ch - 2, rx: 3, fill: steps[k], class: "mark" }, f.svg);
    hover(r, e => showTip(e, `${days[c.weekday]} ${String(c.hour).padStart(2, "0")}:00–${String(c.hour + 1).padStart(2, "0")}:00`, [{ value: int(c.txns), label: "payments" }]));
  }
  days.forEach((d, i) => svgText(f.svg, f.m.l - 6, f.m.t + i * ch + ch / 2 + 4, d, { "text-anchor": "end", fill: css("--ink-3"), "font-size": 11 }));
  for (const h of [0, 6, 12, 18, 23]) svgText(f.svg, f.m.l + h * cw + cw / 2, f.m.t + 7 * ch + 14, String(h).padStart(2, "0") + "h", { "text-anchor": "middle", fill: css("--ink-3"), "font-size": 11 });
  // sequential key
  const ky = f.H - 10, kx = f.W - 8 - steps.length * 16;
  svgText(f.svg, kx - 6, ky + 1, "fewer", { "text-anchor": "end", fill: css("--ink-3"), "font-size": 10.5 });
  steps.forEach((s, i) => svgEl("rect", { x: kx + i * 16, y: ky - 8, width: 14, height: 9, rx: 2, fill: s }, f.svg));
  svgText(f.svg, kx + steps.length * 16 + 2, ky + 1, "more", { fill: css("--ink-3"), "font-size": 10.5 });
}

/* ---------- horizontal bars (HTML) ---------- */
function hbars(host, items, fmt, o = {}) {
  host.replaceChildren();
  const wrap = el("div", { class: "hbars" });
  const max = Math.max(...items.map(i => Math.max(i.value, i.ghost || 0)));
  for (const it of items) {
    const row = el("div", { class: "hbar", tabindex: "0" });
    row.appendChild(el("span", { class: "n", title: it.name }, it.name));
    const t = el("span", { class: "t" });
    const bar = el("i"); bar.style.width = (it.value / max) * 100 + "%"; bar.style.background = o.color || "";
    t.appendChild(bar);
    if (it.ghost != null) { const g = el("i", { class: "ghost" }); g.style.width = (it.ghost / max) * 100 + "%"; t.appendChild(g); }
    row.appendChild(t);
    row.appendChild(el("span", { class: "v" }, fmt(it.value)));
    if (it.tip) hover(row, e => showTip(e, it.name, it.tip));
    wrap.appendChild(row);
  }
  host.appendChild(wrap);
}

function legend(host, items) {
  const l = el("div", { class: "legend" });
  for (const it of items) {
    const s = el("span"); const i = el("i", { class: it.box ? "box" : "" });
    if (it.ghost) { i.style.border = `1.5px solid ${css("--ink-3")}`; i.style.background = "none"; } else i.style.background = it.color;
    s.append(i, document.createTextNode(it.name)); l.appendChild(s);
  }
  host.prepend(l);
}

/* ---------- tables ---------- */
function table(host, cols, rows, rowClass) {
  host.replaceChildren();
  const thead = el("thead"), tr = el("tr");
  for (const c of cols) tr.appendChild(el("th", c.num ? { class: "num" } : {}, c.h));
  thead.appendChild(tr); host.appendChild(thead);
  const tb = el("tbody");
  for (const r of rows) {
    const row = el("tr", rowClass ? { class: rowClass(r) } : {});
    for (const c of cols) {
      const td = el("td", { class: [c.num ? "num" : "", c.cls || ""].join(" ").trim() });
      const v = c.v(r);
      if (v instanceof Node) td.appendChild(v); else td.textContent = v;
      row.appendChild(td);
    }
    tb.appendChild(row);
  }
  host.appendChild(tb);
}
function barCell(v, max, text, color) {
  const d = el("div", { class: "bar-cell" }); const i = el("i");
  if (color) i.style.background = color;
  i.style.width = Math.max(2, (v / max) * 70) + "px";
  d.append(el("span", {}, text), i); return d;
}

/* ---------- SQL highlighting (on text nodes only) ---------- */
const KW = /\b(SELECT|FROM|WHERE|AND|OR|NOT|JOIN|LEFT|USING|ON|WITH|AS|GROUP|BY|ORDER|OVER|PARTITION|RANGE|ROWS|BETWEEN|PRECEDING|FOLLOWING|CURRENT|ROW|WINDOW|CASE|WHEN|THEN|ELSE|END|COUNT|SUM|AVG|MAX|MIN|LAG|ROW_NUMBER|CAST|INTEGER|IS|NULL|IN|DISTINCT|DESC|ASC)\b/g;
function highlight(code, sql) {
  code.replaceChildren();
  for (const line of sql.trimEnd().split("\n")) {
    const ci = line.indexOf("--");
    const body = ci >= 0 ? line.slice(0, ci) : line, comment = ci >= 0 ? line.slice(ci) : "";
    const re = /('[^']*')|(:[a-z_]+)|\b([A-Z_]{2,})\b/g;
    let last = 0, m;
    while ((m = re.exec(body))) {
      if (m.index > last) code.appendChild(document.createTextNode(body.slice(last, m.index)));
      const cls = m[1] ? "st" : m[2] ? "pm" : (KW.lastIndex = 0, KW.test(m[3]) ? "kw" : null);
      if (cls) code.appendChild(el("span", { class: cls }, m[0])); else code.appendChild(document.createTextNode(m[0]));
      last = re.lastIndex;
    }
    code.appendChild(document.createTextNode(body.slice(last)));
    if (comment) code.appendChild(el("span", { class: "cm" }, comment));
    code.appendChild(document.createTextNode("\n"));
  }
}

/* ======================================================= render */
let D;
function render() {
  const C1 = css("--series-1"), C2 = css("--series-2"), C3 = css("--series-3");
  const k = D.kpi;

  document.querySelectorAll('[data-k="period"]').forEach(n => n.textContent = `${new Date(k.first_day).toLocaleDateString("en-GB", { month: "short", year: "numeric" })} – ${new Date(k.last_day).toLocaleDateString("en-GB", { month: "short", year: "numeric" })}`);
  document.querySelectorAll('[data-k="version"]').forEach(n => n.textContent = "v" + D.version);

  /* KPIs */
  const kp = $("#kpis"); kp.replaceChildren();
  const block = D.scorecard.find(r => r.code === "BLOCK"), review = D.scorecard.find(r => r.code === "REVIEW");
  for (const [v, l, s, cls] of [
    [int(k.approved_txns), "card payments", `${int(k.customers)} customers · ${int(k.cards)} cards`],
    [eurC(k.volume_eur), "spent on cards", `average ticket ${eur2(k.avg_ticket_eur)}`],
    [eurC(k.fraud_eur), "lost to fraud", `${int(k.fraud_txns)} payments on ${int(k.cards_hit)} cards`, "fraud"],
    [(10000 * k.fraud_eur / k.volume_eur).toFixed(0) + " bp", "fraud rate", "of card volume"],
    [pct(block.value_recall), "fraud value blocked", `at ${pct(block.precision)} precision`],
    [pct(review.value_recall), "with the review queue", `${int(review.false_positives)} genuine payments checked`],
  ]) {
    const d = el("div", { class: "kpi " + (cls || "") });
    d.append(el("div", { class: "v" }, v), el("div", { class: "l" }, l), el("div", { class: "s" }, s));
    kp.appendChild(d);
  }

  /* findings */
  const fi = $("#findings"); fi.replaceChildren();
  for (const f of D.findings) { const c = el("article", { class: "finding" }); c.append(el("h3", {}, f.title), el("p", {}, f.text)); fi.appendChild(c); }

  /* spending */
  barChart($("#c-monthly"), D.monthly, {
    y: r => r.volume_eur, color: C1, fmt: eurC, label: r => r.label,
    tip: r => [{ color: C1, value: eur(r.volume_eur), label: "volume" }, { value: int(r.txns), label: "payments" }, { value: eur2(r.avg_ticket_eur), label: "average ticket" }, { value: int(r.active_cards), label: "active cards" }],
  });
  const totalTx = D.categories.reduce((a, c) => a + c.txns, 0);
  hbars($("#c-categories"), D.categories.slice(0, 10).map(c => ({
    name: c.category, value: c.pct_of_volume / 100,
    tip: [{ color: C1, value: pct(c.pct_of_volume / 100, 1), label: "of value" }, { value: pct(c.txns / totalTx, 1), label: "of payments" }, { value: eur2(c.avg_ticket_eur), label: "average ticket" }],
  })), v => pct(v, 1), { color: C1 });
  const ch = $("#c-channels");
  lineChart(ch, D.channels.map(r => r.label), [
    { name: "Contactless", color: C1, values: D.channels.map(r => r.contactless_pct / 100) },
    { name: "Online", color: C2, values: D.channels.map(r => r.online_pct / 100) },
  ], { fmt: v => pct(v), fmtTip: v => pct(v, 1), yMax: 1, right: 84 });
  legend(ch, [{ name: "Contactless (of card-present)", color: C1 }, { name: "Online (of all payments)", color: C2 }]);
  heatmap($("#c-heatmap"), D.heatmap);
  hbars($("#c-segments"), D.segments.map(s => ({ name: s.segment, value: s.avg_monthly_spend_eur })), eur, { color: C1 });
  hbars($("#c-districts"), D.districts.slice(0, 6).map(d => ({ name: d.district, value: d.customers, tip: [{ value: int(d.customers), label: "customers" }, { value: eur(d.avg_yearly_spend_eur), label: "average yearly spend" }] })), int, { color: C1 });

  /* fraud */
  barChart($("#c-fraud-monthly"), D.fraud_monthly, {
    y: r => r.fraud_eur, color: C2, fmt: eurC, label: r => r.label,
    tip: r => [{ color: C2, value: eur(r.fraud_eur), label: "fraud" }, { value: r.fraud_bps.toFixed(0) + " bp", label: "of volume" }, { value: int(r.fraud_txns), label: "fraud payments" }, { value: int(r.cards_hit), label: "cards hit" }],
  });
  const fcTot = D.fraud_by_channel.reduce((a, c) => a + c.fraud_eur, 0), txTot = D.fraud_by_channel.reduce((a, c) => a + c.txns, 0);
  const fc = $("#c-fraud-channel");
  hbars(fc, [...D.fraud_by_channel].sort((a, b) => b.fraud_eur - a.fraud_eur).map(c => ({
    name: c.channel, value: c.fraud_eur / fcTot, ghost: c.txns / txTot,
    tip: [{ color: C2, value: pct(c.fraud_eur / fcTot), label: "of fraud losses" }, { value: pct(c.txns / txTot), label: "of payments" }, { value: eur(c.fraud_eur), label: "lost" }],
  })), v => pct(v), { color: C2 });
  legend(fc, [{ name: "Share of fraud losses", color: C2, box: true }, { name: "Share of payments", ghost: true, box: true }]);
  const tr = D.time_to_report;
  const days = Array.from({ length: Math.max(...tr.map(r => r.days_to_report)) }, (_, i) => tr.find(r => r.days_to_report === i + 1) || { days_to_report: i + 1, fraud_txns: 0, fraud_eur: 0 });
  barChart($("#c-report"), days, {
    y: r => r.fraud_txns, color: C2, fmt: int, label: r => `${r.days_to_report} day${r.days_to_report > 1 ? "s" : ""} later`, xLabel: r => r.days_to_report + "d",
    tip: r => [{ color: C2, value: int(r.fraud_txns), label: "fraud payments" }, { value: eur(r.fraud_eur), label: "value" }],
  });
  const hmax = Math.max(...D.hotspots.map(h => h.fraud_eur));
  table($("#t-hotspots"), [
    { h: "Channel", v: r => r.channel }, { h: "Category", v: r => r.category }, { h: "Where", v: r => r.geography },
    { h: "Payments", num: 1, v: r => int(r.txns) }, { h: "Fraud payments", num: 1, v: r => int(r.fraud_txns) },
    { h: "Fraud rate", num: 1, v: r => (r.fraud_bps / 100).toFixed(1) + "%" },
    { h: "Lost", num: 1, v: r => barCell(r.fraud_eur, hmax, eur(r.fraud_eur), C2) },
  ], D.hotspots);

  /* rules */
  const meta = Object.fromEntries(D.rules.map(r => [r.code, r]));
  table($("#t-scorecard"), [
    { h: "", v: r => r.code.length === 2 ? r.code : "" }, { h: "Rule", v: r => r.rule }, { h: "Aimed at", v: r => r.catches },
    { h: "Points", num: 1, v: r => r.weight ?? "" }, { h: "Alerts", num: 1, v: r => int(r.alerts) },
    { h: "Precision", num: 1, v: r => pct(r.precision, 1) }, { h: "Recall", num: 1, v: r => pct(r.recall, 1) },
    { h: "Value caught", num: 1, v: r => barCell(r.value_recall, 1, pct(r.value_recall)) },
    { h: "Lift", num: 1, v: r => int(r.lift) + "×" },
  ], D.scorecard, r => r.code.length > 2 ? "total" : "");

  const tabs = $("#sql-tabs"); tabs.replaceChildren();
  const show = code => {
    tabs.querySelectorAll("button").forEach(b => b.setAttribute("aria-selected", b.dataset.code === code));
    highlight($("#sql-view code"), `-- ${meta[code].file}\n` + meta[code].sql);
  };
  for (const r of D.rules) {
    const b = el("button", { type: "button", role: "tab", "data-code": r.code, title: r.name }, `${r.code} · ${r.name}`);
    b.addEventListener("click", () => show(r.code)); tabs.appendChild(b);
  }
  show(D.rules[0].code);

  /* threshold explorer */
  const curve = D.curve, slider = $("#thr");
  slider.max = curve.length - 1;
  if (!slider.dataset.init) { slider.value = curve.findIndex(c => c.threshold === D.thresholds.block); slider.dataset.init = 1; }
  const drawCurve = () => {
    const c = curve[slider.value];
    $("#thr-v").textContent = c.threshold;
    const mk = $("#thr-kpis"); mk.replaceChildren();
    for (const [v, l] of [[pct(c.precision), "precision"], [pct(c.value_recall), "fraud value caught"], [int(c.alerts), "alerts in the year"], [int(c.false_positives), "genuine payments stopped"]]) {
      const d = el("div"); d.append(el("b", {}, v), el("span", {}, l)); mk.appendChild(d);
    }
    const host = $("#c-curve");
    lineChart(host, curve.map(c => String(c.threshold)), [
      { name: "Precision", color: C1, values: curve.map(c => c.precision) },
      { name: "Value caught", color: C2, values: curve.map(c => c.value_recall) },
      { name: "Recall", color: C3, values: curve.map(c => c.recall) },
    ], { fmt: v => pct(v), yMax: 1, right: 92, headPrefix: "Score ≥ ", dots: true,
         markers: [{ i: +slider.value, label: "your pick" }] });
    legend(host, [{ name: "Precision", color: C1 }, { name: "Value caught", color: C2 }, { name: "Recall", color: C3 }]);
  };
  slider.oninput = drawCurve; drawCurve();

  /* tuning small multiples */
  const tm = $("#c-tuning"); tm.replaceChildren();
  const byRule = {};
  for (const t of D.tuning) (byRule[t.code] ||= []).push(t);
  const paramText = { min_txns: "minimum charges in 10 minutes", max_hours: "maximum hours between countries", multiple: "times the card's usual amount" };
  for (const [code, rows] of Object.entries(byRule)) {
    const box = el("div"); box.append(el("h4", {}, `${code} · ${meta[code].name}`), el("p", {}, paramText[rows[0].param] || rows[0].param));
    const host = el("div", { class: "chart" }); host.style.setProperty("--h", "190px"); box.appendChild(host); tm.appendChild(box);
    requestAnimationFrame(() => {
      lineChart(host, rows.map(r => String(r.value)), [
        { name: "Precision", color: C1, values: rows.map(r => r.precision) },
        { name: "Recall", color: C3, values: rows.map(r => r.recall) },
      ], { fmt: v => pct(v), yMax: 1, right: 66, height: 190, dots: true, ring: rows.findIndex(r => r.is_default), headPrefix: rows[0].param + " = " });
    });
  }

  /* queue */
  $("#queue-sub").textContent = `${int(D.queue_size.block)} payments blocked (score ≥ ${D.thresholds.block}) and ${int(D.queue_size.review)} sent for review (score ${D.thresholds.review}–${D.thresholds.block - 1}) over the year.`;
  table($("#t-queue"), [
    { h: "When", cls: "nowrap", v: r => r.ts.slice(0, 16) }, { h: "Amount", num: 1, v: r => eur2(r.amount_eur) },
    { h: "Where", v: r => `${r.category} · ${r.channel} · ${r.country}` },
    { h: "Score", num: 1, v: r => r.risk_score },
    { h: "Evidence", cls: "ev", v: r => r.evidence },
    { h: "Action", v: r => el("span", { class: "pill " + (r.action === "Block" ? "block" : "") }, r.action) },
    { h: "Outcome", v: r => el("span", { class: "pill " + r.outcome.toLowerCase() }, r.outcome) },
  ], D.queue);
}

/* ---------- theme, nav, boot ---------- */
const root = document.documentElement;
try { const t = localStorage.getItem("ledger-theme"); if (t) root.dataset.theme = t; } catch (e) { /* storage blocked */ }
$("#theme").addEventListener("click", () => {
  const dark = root.dataset.theme ? root.dataset.theme === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
  root.dataset.theme = dark ? "light" : "dark";
  try { localStorage.setItem("ledger-theme", root.dataset.theme); } catch (e) { /* ignore */ }
  render();
});
matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => D && render());

const links = [...document.querySelectorAll(".toc a")];
const spy = new IntersectionObserver(es => es.forEach(e => {
  if (e.isIntersecting) links.forEach(a => a.classList.toggle("on", a.getAttribute("href") === "#" + e.target.id));
}), { rootMargin: "-40% 0px -55% 0px" });
document.querySelectorAll("main section[id]").forEach(s => spy.observe(s));

let lastW = 0, timer;
new ResizeObserver(() => {
  const w = document.body.clientWidth;
  if (!D || Math.abs(w - lastW) < 8) return;
  lastW = w; clearTimeout(timer); timer = setTimeout(render, 120);
}).observe(document.body);

fetch("data.json").then(r => r.json()).then(d => { D = d; lastW = document.body.clientWidth; render(); })
  .catch(err => { $("#kpis").textContent = "Could not load data.json. Run `python -m ledger` first. " + err; });
