// Shared code for every page: data loading, theme, category colours, chart defaults.

const CATEGORIES = [
  "replication and reproducibility", "research practices and bias", "open science",
  "peer review and publishing", "research integrity and misconduct", "statistical methods",
  "scientometrics and research evaluation", "science policy and ethics",
];
const CAT_LABEL = {
  "replication and reproducibility": "Replication & reproducibility",
  "research practices and bias": "Research practices & bias",
  "open science": "Open science",
  "peer review and publishing": "Peer review & publishing",
  "research integrity and misconduct": "Research integrity & misconduct",
  "statistical methods": "Statistical methods",
  "scientometrics and research evaluation": "Scientometrics & evaluation",
  "science policy and ethics": "Science policy & ethics",
};

function cssVar(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}
function catColor(cat) {
  const i = CATEGORIES.indexOf(cat);
  return i < 0 ? cssVar("--other") : cssVar(`--series-${i + 1}`);
}
function seriesColor(i) { return i < 8 ? cssVar(`--series-${i + 1}`) : cssVar("--other"); }
function seqScale() { return [0, 1, 2, 3, 4, 5].map((i) => [i / 5, cssVar(`--seq-${i}`)]); }

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
function wrap(s, n = 60) {
  const words = String(s ?? "").split(" "); const lines = []; let line = "";
  for (const w of words) { if ((line + " " + w).trim().length > n) { lines.push(line); line = w; } else line = (line + " " + w).trim(); }
  if (line) lines.push(line);
  return lines.map(esc).join("<br>");
}
function fmt(n) { return Number(n).toLocaleString("en-US"); }
function doiLink(p) { return p.doi ? `https://doi.org/${p.doi}` : `https://openalex.org/${p.id}`; }
function orcidLink(o) { return o ? `https://orcid.org/${o}` : null; }

const _cache = {};
function load(name) {
  if (!_cache[name]) _cache[name] = fetch(`data/${name}.json`).then((r) => {
    if (!r.ok) throw new Error(`could not load ${name}.json (${r.status})`);
    return r.json();
  });
  return _cache[name];
}

// ---- theme toggle: OS setting by default, the viewer's choice wins both ways ----
function storedTheme() { try { return localStorage.getItem("theme"); } catch (e) { return null; } }
function applyTheme(t) {
  if (t) document.documentElement.setAttribute("data-theme", t);
  else document.documentElement.removeAttribute("data-theme");
}
applyTheme(storedTheme());
function isDark() {
  const t = document.documentElement.getAttribute("data-theme");
  if (t) return t === "dark";
  return window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
}
const _redraw = [];
function onThemeChange(fn) { _redraw.push(fn); }
document.addEventListener("DOMContentLoaded", () => {
  const b = document.getElementById("theme-toggle");
  if (b) {
    const label = () => { b.textContent = isDark() ? "Light mode" : "Dark mode"; };
    label();
    b.addEventListener("click", () => {
      const t = isDark() ? "light" : "dark";
      applyTheme(t); try { localStorage.setItem("theme", t); } catch (e) {}
      label(); _redraw.forEach((f) => f());
    });
  }
  if (window.matchMedia) window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => _redraw.forEach((f) => f()));
});

// ---- Plotly defaults that follow the theme ----
function baseLayout(extra = {}) {
  const ink = cssVar("--text-secondary"), grid = cssVar("--grid"), axis = cssVar("--axis");
  const ax = { gridcolor: grid, linecolor: axis, zerolinecolor: axis, tickfont: { color: cssVar("--text-muted") }, automargin: true };
  return Object.assign({
    paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)",
    font: { family: 'system-ui, -apple-system, "Segoe UI", sans-serif', color: ink, size: 13 },
    margin: { l: 50, r: 20, t: 10, b: 40 },
    hoverlabel: { bgcolor: cssVar("--surface-1"), bordercolor: cssVar("--axis"), font: { color: cssVar("--text-primary") } },
    legend: { orientation: "h", y: -0.18, font: { color: ink } },
    xaxis: Object.assign({}, ax), yaxis: Object.assign({}, ax),
  }, extra);
}
const PLOT_CONFIG = { displaylogo: false, responsive: true, modeBarButtonsToRemove: ["lasso2d", "select2d"] };

// ---- an HTML legend for the categories (click to hide a category) ----
function categoryLegend(el, active, onToggle) {
  el.innerHTML = "";
  for (const c of CATEGORIES) {
    const it = document.createElement("span");
    it.className = "item" + (active.has(c) ? "" : " off");
    it.innerHTML = `<span class="swatch" style="background:${catColor(c)}"></span>${esc(CAT_LABEL[c])}`;
    it.addEventListener("click", () => { active.has(c) ? active.delete(c) : active.add(c); onToggle(); });
    el.appendChild(it);
  }
}

// ---- a floating tooltip for the D3 charts ----
const Tip = {
  el: null,
  show(html, ev) {
    if (!this.el) { this.el = document.createElement("div"); this.el.className = "tip"; document.body.appendChild(this.el); }
    this.el.innerHTML = html; this.el.style.display = "block";
    const w = this.el.offsetWidth, h = this.el.offsetHeight;
    let x = ev.clientX + 14, y = ev.clientY + 14;
    if (x + w > window.innerWidth - 8) x = ev.clientX - w - 14;
    if (y + h > window.innerHeight - 8) y = ev.clientY - h - 14;
    this.el.style.left = x + "px"; this.el.style.top = y + "px";
  },
  hide() { if (this.el) this.el.style.display = "none"; },
};

function personName(p) { return p.n || "(no name)"; }
function failed(el, err) { el.innerHTML = `<p class="loading">Could not load the data: ${esc(err.message)}</p>`; }

// Hide SVG labels that overlap a label with higher priority (screen boxes; greedy, highest priority first).
// texts: a d3 selection of <text>; priority(d) -> number; eligible(d) -> whether the label may show at all.
function declutter(texts, priority, eligible = () => true) {
  const items = [];
  texts.each(function (d) { items.push({ el: this, d }); });
  items.sort((a, b) => priority(b.d) - priority(a.d));
  const placed = [];
  for (const it of items) {
    if (!eligible(it.d)) { it.el.setAttribute("opacity", 0); continue; }
    it.el.setAttribute("opacity", 1);
    const r = it.el.getBoundingClientRect();
    if (!r.width) continue;
    const box = [r.left - 2, r.top - 1, r.right + 2, r.bottom + 1];
    if (placed.some((b) => box[0] < b[2] && box[2] > b[0] && box[1] < b[3] && box[3] > b[1])) {
      it.el.setAttribute("opacity", 0);
    } else placed.push(box);
  }
}
