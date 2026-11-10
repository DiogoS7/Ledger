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

/* ======================================================= plain-language helpers */
const ICONS = {
  card: '<rect x="3" y="5" width="18" height="14" rx="3"/><path d="M3 10h18M7 15h4"/>',
  coins: '<circle cx="9" cy="9" r="5"/><path d="M14.5 5.5a5 5 0 1 1-1 9.9M9 7v4M7.5 9h3"/>',
  alert: '<path d="M12 3l9 16H3z"/><path d="M12 10v4M12 17h.01"/>',
  percent: '<path d="M19 5L5 19"/><circle cx="7" cy="7" r="2.5"/><circle cx="17" cy="17" r="2.5"/>',
  shield: '<path d="M12 3l7 3v6c0 4.5-3 7.5-7 9-4-1.5-7-4.5-7-9V6z"/><path d="M9 12l2 2 4-4"/>',
  eye: '<path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
  laptop: '<rect x="4" y="5" width="16" height="11" rx="2"/><path d="M2 19h20"/>',
  globe: '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c3 3.5 3 14.5 0 18M12 3c-3 3.5-3 14.5 0 18"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  tap: '<path d="M9 11V5a2 2 0 0 1 4 0v6M13 10a2 2 0 0 1 4 0v3a7 7 0 0 1-7 7 6 6 0 0 1-5-3l-2-4a1.6 1.6 0 0 1 2.7-1.6L9 14"/>',
  test: '<path d="M4 7h4M4 12h7M4 17h4"/><path d="M15 6l5 5-5 5"/>',
  copy: '<rect x="8" y="8" width="13" height="10" rx="2"/><path d="M5 15H4a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1h11a1 1 0 0 1 1 1v1"/>',
  moon: '<path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/>',
};
function icon(name) {
  const d = el("span", { class: "ic", "aria-hidden": "true" });
  const s = document.createElementNS(NS, "svg"); s.setAttribute("viewBox", "0 0 24 24");
  s.innerHTML = ICONS[name] || ICONS.card;   // static markup from this file, not data
  d.appendChild(s); return d;
}
const COUNTRY = { PT: "Portugal", ES: "Spain", FR: "France", GB: "the UK", IT: "Italy", DE: "Germany", NL: "the Netherlands", BR: "Brazil", US: "the US", MA: "Morocco", CN: "China", LT: "Lithuania", CY: "Cyprus" };
const HOW = { "Chip & PIN": "Card put in a machine", Contactless: "Card tapped", Online: "Online", ATM: "Cash machine" };
const CAT = { "ATM cash": "Cash withdrawals", "Gift cards & vouchers": "Gift cards", "Crypto exchange": "Crypto", "Streaming & subscriptions": "Subscriptions", "Utilities & telecom": "Bills", "Online marketplace": "Online shops", "Travel & airlines": "Flights & travel" };
const cat = c => CAT[c] || c;
const oneIn = p => p >= 0.095 ? `${Math.round(p * 10)} in 10` : `${Math.max(1, Math.round(p * 100))} in 100`;
const rate = n => n >= 365 ? `about ${Math.round(n / 365)} a day` : n >= 52 ? `about ${Math.round(n / 52)} a week` : n >= 12 ? `about ${Math.round(n / 12)} a month` : "less than one a month";
const when = ts => new Date(ts.replace(" ", "T")).toLocaleString("en-GB", { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });

const ATTACKS = [
  { icon: "test", title: "Card testing", sub: "A thief checks that stolen card details work.", codes: ["R1", "R2"],
    steps: ["A string of tiny online charges, often under €3, minutes apart", "Some are declined, some go through", "Once one works, a big online purchase follows"] },
  { icon: "copy", title: "Copied card", sub: "A copy of the card is used abroad.", codes: ["R3"],
    steps: ["The real customer is still shopping in Portugal", "A copy of their card takes cash or buys jewellery in another country", "All on the same day, sometimes within an hour"] },
  { icon: "moon", title: "Hijacked account", sub: "Someone gets into the card details online.", codes: ["R4", "R5", "R6"],
    steps: ["In the middle of the night, while the customer sleeps", "Several big purchases at risky shops: electronics, gift cards, crypto", "Usually from websites abroad"] },
];

/* ======================================================= render */
let D, techDone = false;
function render() {
  const C1 = css("--series-1"), C2 = css("--series-2");
  const k = D.kpi, sc = Object.fromEntries(D.scorecard.map(r => [r.code, r]));
  const meta = Object.fromEntries(D.rules.map(r => [r.code, r]));
  const block = sc.BLOCK, review = sc.REVIEW;

  document.querySelectorAll('[data-k="version"]').forEach(n => n.textContent = "v" + D.version);
  document.querySelectorAll('[data-k="review"]').forEach(n => n.textContent = D.thresholds.review);
  document.querySelectorAll('[data-k="block"]').forEach(n => n.textContent = D.thresholds.block);
  document.querySelectorAll('[data-k="block1"]').forEach(n => n.textContent = D.thresholds.block - 1);

  /* headline numbers */
  const kp = $("#kpis"); kp.replaceChildren();
  for (const [ic, v, l, s, cls] of [
    ["card", int(k.approved_txns), "card payments", `by ${int(k.customers)} customers in one year`],
    ["coins", eurC(k.volume_eur), "spent", `about ${eur(k.avg_ticket_eur)} per payment`],
    ["alert", eurC(k.fraud_eur), "stolen by fraudsters", `from ${int(k.cards_hit)} customers' cards`, "fraud"],
    ["percent", "€" + (1000 * k.fraud_eur / k.volume_eur).toFixed(0), "lost in every €1,000", "spent on cards", "fraud"],
    ["shield", pct(block.value_recall), "of stolen money stopped", "automatically, by six simple checks", "good"],
    ["eye", pct(review.value_recall), "with a quick human check", "on the less obvious cases", "good"],
  ]) {
    const d = el("div", { class: "kpi " + (cls || "") });
    d.append(icon(ic), el("div", { class: "v" }, v), el("div", { class: "l" }, l), el("div", { class: "s" }, s));
    kp.appendChild(d);
  }

  const fi = $("#findings"); fi.replaceChildren();
  for (const f of D.findings) { const c = el("article", { class: "finding" }); c.append(icon(f.icon), el("h3", {}, f.title), el("p", {}, f.text)); fi.appendChild(c); }

  /* 1 · spending */
  barChart($("#c-monthly"), D.monthly, {
    y: r => r.volume_eur, color: C1, fmt: eurC, label: r => r.label,
    tip: r => [{ color: C1, value: eur(r.volume_eur), label: "spent" }, { value: int(r.txns), label: "payments" }, { value: eur2(r.avg_ticket_eur), label: "per payment on average" }],
  });
  hbars($("#c-categories"), D.categories.slice(0, 8).map(c => ({
    name: cat(c.category), value: c.pct_of_volume,
    tip: [{ color: C1, value: "€" + c.pct_of_volume.toFixed(0), label: "of every €100" }, { value: eur2(c.avg_ticket_eur), label: "per payment on average" }],
  })), v => "€" + v.toFixed(0), { color: C1 });
  const ch = $("#c-channels");
  lineChart(ch, D.channels.map(r => r.label), [
    { name: "Tapped", color: C1, values: D.channels.map(r => r.contactless_pct / 100) },
    { name: "Online", color: C2, values: D.channels.map(r => r.online_pct / 100) },
  ], { fmt: v => pct(v), yMax: 1, right: 64 });
  legend(ch, [{ name: "Shop payments made by tapping", color: C1 }, { name: "All payments made online", color: C2 }]);
  heatmap($("#c-heatmap"), D.heatmap);
  hbars($("#c-segments"), D.segments.map(s => ({ name: { Premium: "Premium customers", Business: "Business owners", Everyday: "Everyday customers", Student: "Students" }[s.segment] || s.segment, value: s.avg_monthly_spend_eur })), eur, { color: C1 });

  /* 2 · fraud */
  const at = $("#attacks"); at.replaceChildren();
  for (const a of ATTACKS) {
    const c = el("article", { class: "attack" });
    const ol = el("ol"); a.steps.forEach(s => ol.appendChild(el("li", {}, s)));
    const share = el("div", { class: "share" });
    share.append(document.createTextNode("Spotted by: "), el("b", {}, a.codes.map(x => meta[x].name).join(", ")));
    c.append(icon(a.icon), el("h3", {}, a.title), el("p", { class: "sub" }, a.sub), ol, share);
    at.appendChild(c);
  }
  barChart($("#c-fraud-monthly"), D.fraud_monthly, {
    y: r => r.fraud_eur, color: C2, fmt: eurC, label: r => r.label,
    tip: r => [{ color: C2, value: eur(r.fraud_eur), label: "stolen" }, { value: int(r.cards_hit), label: "cards hit" }, { value: "€" + (r.fraud_bps / 10).toFixed(1), label: "per €1,000 spent" }],
  });
  const fcTot = D.fraud_by_channel.reduce((a, c) => a + c.fraud_eur, 0), txTot = D.fraud_by_channel.reduce((a, c) => a + c.txns, 0);
  const fc = $("#c-fraud-channel");
  hbars(fc, [...D.fraud_by_channel].sort((a, b) => b.fraud_eur - a.fraud_eur).map(c => ({
    name: HOW[c.channel] || c.channel, value: c.fraud_eur / fcTot, ghost: c.txns / txTot,
    tip: [{ color: C2, value: pct(c.fraud_eur / fcTot), label: "of the stolen money" }, { value: pct(c.txns / txTot), label: "of all payments" }],
  })), v => pct(v), { color: C2 });
  legend(fc, [{ name: "Stolen money", color: C2, box: true }, { name: "All payments", ghost: true, box: true }]);
  const tr = D.time_to_report;
  const all = tr.flatMap(r => Array(r.fraud_txns).fill(r.days_to_report)).sort((a, b) => a - b);
  $("#report-sub").textContent = `Half of the victims took ${all[Math.floor(all.length / 2)]} days or more to report it.`;
  const days = Array.from({ length: Math.max(...tr.map(r => r.days_to_report)) }, (_, i) => tr.find(r => r.days_to_report === i + 1) || { days_to_report: i + 1, fraud_txns: 0, fraud_eur: 0 });
  barChart($("#c-report"), days, {
    y: r => r.fraud_txns, color: C2, fmt: int, label: r => `Reported after ${r.days_to_report} day${r.days_to_report > 1 ? "s" : ""}`, xLabel: r => String(r.days_to_report),
    tip: r => [{ color: C2, value: int(r.fraud_txns), label: "stolen payments" }],
  });
  const rk = $("#risky"); rk.replaceChildren();
  for (const h of D.hotspots.slice(0, 6)) {
    const c = el("div", { class: "risk" });
    c.append(el("div", { class: "what" }, h.channel === "ATM" ? "Cash withdrawals" : `${cat(h.category)}, ${(HOW[h.channel] || h.channel).toLowerCase()}`),
      el("div", { class: "how" }, h.geography === "Foreign" ? "abroad" : "in Portugal"),
      el("div", { class: "lost" }, eur(h.fraud_eur) + " stolen"),
      el("div", { class: "rate" }, h.txns / h.fraud_txns < 1.5 ? "nearly every one of these payments was fraud" : `1 in ${Math.round(h.txns / h.fraud_txns)} of these payments was fraud`));
    rk.appendChild(c);
  }

  /* 3 · checks */
  const cl = $("#checks-list"); cl.replaceChildren();
  for (const r of D.rules) {
    const s = sc[r.code];
    const c = el("article", { class: "check" });
    const top = el("div", { class: "top" }); top.append(el("span", { class: "tag" }, r.catches), el("span", { class: "pts" }, `+${r.weight} points`));
    const st = el("div", { class: "stats" });
    const a = el("div"); a.append(el("b", {}, oneIn(s.precision)), el("span", {}, "alerts are real fraud"));
    const b = el("div"); b.append(el("b", {}, eurC(s.fraud_eur_caught)), el("span", {}, "of stolen money spotted"));
    st.append(a, b);
    c.append(top, el("h3", {}, r.name), el("p", { class: "rule" }, r.plain), st);
    cl.appendChild(c);
  }
  const top = D.examples[0];
  $("#score-note").textContent = top ? `A payment that trips several checks adds up fast. The ${eur(top.amount_eur)} gift-card purchase in the examples below tripped ${top.reasons.length} checks and scored ${top.score} points. One check on its own is often not enough: the "${meta.R4.name}" check spots the most stolen money, but only ${oneIn(sc.R4.precision)} of its alerts are real fraud.` : "";

  /* 4 · try it (strict = lower threshold = right side) */
  const curve = [...D.curve].reverse(), slider = $("#thr");
  slider.max = curve.length - 1;
  if (!slider.dataset.init) { slider.value = curve.findIndex(c => c.threshold === D.thresholds.block); slider.dataset.init = 1; }
  const drawTry = () => {
    const c = curve[slider.value];
    $("#thr-v").textContent = c.threshold;
    const out = $("#thr-out"); out.replaceChildren();
    const o1 = el("div", { class: "outcome o-money" });
    o1.append(el("div", { class: "big" }, pct(c.value_recall)), el("p", {}, `of the stolen money is stopped (${eurC(c.fraud_eur_caught)} of ${eurC(k.fraud_eur)})`));
    const o2 = el("div", { class: "outcome o-right" });
    const right = Math.round(c.precision * 10);
    const dots = el("div", { class: "dots", "aria-hidden": "true" });
    for (let i = 0; i < 10; i++) dots.appendChild(el("i", i < right ? {} : { class: "off" }));
    o2.append(el("div", { class: "big" }, `${right} in 10`), el("p", {}, "stopped payments are really fraud"), dots);
    const o3 = el("div", { class: "outcome" });
    o3.append(el("div", { class: "big" }, int(c.false_positives)), el("p", {}, `honest payments stopped in a year (${rate(c.false_positives)})`));
    out.append(o1, o2, o3);
    const host = $("#c-curve");
    lineChart(host, curve.map(c => String(c.threshold)), [
      { name: "Money stopped", color: C2, values: curve.map(c => c.value_recall) },
      { name: "Really fraud", color: C1, values: curve.map(c => c.precision) },
    ], { fmt: v => pct(v), yMax: 1, right: 100, headPrefix: "Stop at ", fmtTip: v => pct(v), markers: [{ i: +slider.value, label: "you are here" }] });
    legend(host, [{ name: "Share of stolen money stopped", color: C2 }, { name: "Share of stopped payments that are really fraud", color: C1 }]);
  };
  slider.oninput = drawTry; drawTry();

  /* 5 · examples */
  const ex = $("#examples-list"); ex.replaceChildren();
  for (const e of D.examples) {
    const c = el("article", { class: "ex" });
    const ul = el("ul"); e.reasons.forEach(r => ul.appendChild(el("li", {}, r.charAt(0).toUpperCase() + r.slice(1))));
    const v = el("div", { class: "verdict" });
    v.append(el("span", { class: "chip " + (e.action === "Block" ? "stop" : "look") }, e.action === "Block" ? `Stopped · ${e.score} points` : `Checked by a person · ${e.score} points`),
      el("span", { class: "chip " + (e.is_fraud ? "fraud" : "honest") }, e.is_fraud ? "✓ It was fraud" : "✗ False alarm: it was the customer"));
    c.append(el("div", { class: "kind" }, e.kind), el("div", { class: "amt" }, eur2(e.amount_eur)),
      el("div", { class: "where" }, `${cat(e.category)} · ${(HOW[e.channel] || e.channel).toLowerCase()} · ${COUNTRY[e.country] || e.country} · ${when(e.ts)}`),
      ul, v);
    ex.appendChild(c);
  }

  if ($("details.behind").open) renderTech();
}

/* technical section: only drawn once it is opened (charts need a visible width) */
function renderTech() {
  const C1 = css("--series-1"), C3 = css("--series-3");
  const meta = Object.fromEntries(D.rules.map(r => [r.code, r]));
  table($("#t-scorecard"), [
    { h: "", v: r => r.code.length === 2 ? r.code : "" }, { h: "Check", v: r => r.rule }, { h: "Aimed at", v: r => r.catches },
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
    const b = el("button", { type: "button", role: "tab", "data-code": r.code }, `${r.code} · ${r.name}`);
    b.addEventListener("click", () => show(r.code)); tabs.appendChild(b);
  }
  show(D.rules[0].code);
  const tm = $("#c-tuning"); tm.replaceChildren();
  const byRule = {};
  for (const t of D.tuning) (byRule[t.code] ||= []).push(t);
  const paramText = { min_txns: "minimum charges in 10 minutes", max_hours: "maximum hours between countries", multiple: "times the card's usual amount" };
  for (const [code, rows] of Object.entries(byRule)) {
    const box = el("div"); box.append(el("h4", {}, `${code} · ${meta[code].name}`), el("p", {}, paramText[rows[0].param] || rows[0].param));
    const host = el("div", { class: "chart" }); host.style.setProperty("--h", "190px"); box.appendChild(host); tm.appendChild(box);
    lineChart(host, rows.map(r => String(r.value)), [
      { name: "Precision", color: C1, values: rows.map(r => r.precision) },
      { name: "Recall", color: C3, values: rows.map(r => r.recall) },
    ], { fmt: v => pct(v), yMax: 1, right: 66, height: 190, dots: true, ring: rows.findIndex(r => r.is_default), headPrefix: rows[0].param + " = " });
  }
}
$("details.behind").addEventListener("toggle", e => { if (e.target.open && D) renderTech(); });

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
