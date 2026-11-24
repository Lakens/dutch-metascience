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
    dragmode: false,   // no zooming or panning by dragging; the maps set "zoom" and use MAP_CONFIG
    font: { family: 'system-ui, -apple-system, "Segoe UI", sans-serif', color: ink, size: 13 },
    margin: { l: 50, r: 20, t: 10, b: 40 },
    hoverlabel: { bgcolor: cssVar("--surface-1"), bordercolor: cssVar("--axis"), font: { color: cssVar("--text-primary") } },
    legend: { orientation: "h", y: -0.18, font: { color: ink } },
    // grid lines across the key variable only (Wilke ch. 23): horizontal lines by default; charts whose key
    // variable is on the x axis (horizontal bars, intervals, scatter plots) turn the vertical lines on
    xaxis: Object.assign({}, ax, { showgrid: false }), yaxis: Object.assign({}, ax),
  }, extra);
}
// charts: hover labels only, no zoom (no toolbar, no scroll zoom, no double-click reset)
const PLOT_CONFIG = { displaylogo: false, responsive: true, displayModeBar: false, scrollZoom: false, doubleClick: false };
// maps (paper map, Places maps): zoom and pan stay available
const MAP_CONFIG = { displaylogo: false, responsive: true, modeBarButtonsToRemove: ["lasso2d", "select2d"] };

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

// ---- phone menu: on narrow screens the page links fold away behind a "Menu" button ----
document.addEventListener("DOMContentLoaded", () => {
  const header = document.querySelector("header.site"), nav = header && header.querySelector("nav");
  if (!header || !nav) return;
  nav.id = nav.id || "site-nav";
  const btn = document.createElement("button");
  btn.type = "button"; btn.className = "menu-toggle"; btn.textContent = "Menu";
  btn.setAttribute("aria-controls", nav.id); btn.setAttribute("aria-expanded", "false");
  header.insertBefore(btn, nav);
  const setOpen = (open) => { header.classList.toggle("open", open); btn.setAttribute("aria-expanded", String(open)); btn.textContent = open ? "Close" : "Menu"; };
  btn.addEventListener("click", () => setOpen(!header.classList.contains("open")));
  nav.addEventListener("click", (e) => { if (e.target.closest("a")) setOpen(false); });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") setOpen(false); });
});

// ---- name search: suggestions while typing; case, accents and word order do not matter ----
// foldText("Daniël Lakens") -> "daniel lakens"
const _FOLD = { "ø": "o", "æ": "ae", "œ": "oe", "ß": "ss", "ł": "l", "đ": "d", "ı": "i", "þ": "th" };
function foldText(s) {
  return String(s ?? "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase()
    .replace(/[øæœßłđıþ]/g, (c) => _FOLD[c]).replace(/[^a-z0-9]+/g, " ").trim();
}
// Does text contain every word of the query (anywhere)? For simple filters.
function textMatches(query, text) {
  const q = foldText(query);
  if (!q) return true;
  const t = foldText(text);
  return q.split(" ").every((w) => t.includes(w));
}
// Score of a name for a query: every query word must occur in the name; words that start a name word count more.
function nameScore(qWords, folded) {
  const words = folded.split(" ");
  let score = 0;
  for (const w of qWords) {
    if (words.some((x) => x === w)) score += 4;
    else if (words.some((x) => x.startsWith(w))) score += 3;
    else if (folded.includes(w)) score += 1;
    else return -1;
  }
  if (folded.startsWith(qWords.join(" "))) score += 2;
  return score;
}
// Attach suggestions to an <input>. getItems() returns [{id, n, k, y0, y1, l}] (people.json records work as is);
// onPick(item) is called when a suggestion is chosen (click, tap, or Enter; Enter alone takes the first suggestion).
function nameSearch(input, getItems, onPick, max = 10) {
  input.removeAttribute("list");
  input.setAttribute("autocomplete", "off");
  input.setAttribute("role", "combobox");
  input.setAttribute("aria-autocomplete", "list");
  input.setAttribute("aria-expanded", "false");
  const wrap = document.createElement("span");
  wrap.className = "ns-wrap";
  input.parentNode.insertBefore(wrap, input);
  wrap.appendChild(input);
  const list = document.createElement("ul");
  list.className = "ns-list"; list.id = (input.id || "ns") + "-suggestions"; list.setAttribute("role", "listbox");
  wrap.appendChild(list);
  input.setAttribute("aria-controls", list.id);
  const folded = new WeakMap();
  let shown = [], active = -1;
  function close() { list.style.display = "none"; input.setAttribute("aria-expanded", "false"); shown = []; active = -1; }
  function render() {
    list.innerHTML = shown.map((p, i) => `<li role="option" id="${list.id}-${i}" data-i="${i}"${i === active ? ' aria-selected="true"' : ""}>
      <span class="ns-n">${esc(p.n)}</span>
      <span class="ns-s">${p.k != null ? `${fmt(p.k)} paper${p.k === 1 ? "" : "s"}` : ""}${p.y0 ? ` · ${p.y0}${p.y1 && p.y1 !== p.y0 ? "–" + p.y1 : ""}` : ""}</span></li>`).join("");
    list.style.display = shown.length ? "block" : "none";
    input.setAttribute("aria-expanded", String(shown.length > 0));
    if (active >= 0) input.setAttribute("aria-activedescendant", `${list.id}-${active}`);
    else input.removeAttribute("aria-activedescendant");
  }
  function update() {
    const q = foldText(input.value);
    if (!q) { close(); return; }
    const qw = q.split(" ");
    const scored = [];
    for (const p of getItems()) {
      let f = folded.get(p);
      if (f === undefined) { f = foldText(p.n); folded.set(p, f); }
      const s = nameScore(qw, f);
      if (s >= 0) scored.push([s, p]);
    }
    scored.sort((a, b) => b[0] - a[0] || (b[1].k || 0) - (a[1].k || 0) || a[1].n.localeCompare(b[1].n));
    shown = scored.slice(0, max).map((x) => x[1]); active = -1;
    if (!shown.length) { list.innerHTML = `<li class="ns-none">No one found</li>`; list.style.display = "block"; return; }
    render();
  }
  function pick(p) { if (!p) return; input.value = p.n; close(); onPick(p); }
  input.addEventListener("input", update);
  input.addEventListener("focus", () => { if (input.value) update(); });
  input.addEventListener("keydown", (e) => {
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      if (!shown.length) update();
      if (!shown.length) return;
      e.preventDefault();
      active = (active + (e.key === "ArrowDown" ? 1 : -1) + shown.length) % shown.length;
      render();
      const li = list.children[active]; if (li) li.scrollIntoView({ block: "nearest" });
    } else if (e.key === "Enter") {
      e.preventDefault();
      if (!shown.length) update();
      pick(shown[Math.max(0, active)]);
    } else if (e.key === "Escape") close();
  });
  // mousedown (not click) so that the choice is made before the input loses focus
  list.addEventListener("mousedown", (e) => {
    const li = e.target.closest("li[data-i]");
    if (li) { e.preventDefault(); pick(shown[+li.dataset.i]); }
  });
  input.addEventListener("blur", () => setTimeout(close, 150));
  return { update, close };
}

// ---- personal view: "view the site as" one person; highlights that person, or their subfield, on every page ----
// Kept in this browser (localStorage) and in the address (?me=<person id>), so a link shows the same view.
// Nothing is sent anywhere: the site has no server.
const Me = {
  _stored() { try { return JSON.parse(localStorage.getItem("me") || "null"); } catch (e) { return null; } },
  _save(v) { try { if (v) localStorage.setItem("me", JSON.stringify(v)); else localStorage.removeItem("me"); } catch (e) {} },
  // the subfield: the clusters holding at least 15% of the person's papers (at least the largest, at most 3)
  fieldOf(p) {
    const e = Object.entries(p.cls || {}).map(([c, n]) => [+c, n]).sort((a, b) => b[1] - a[1]);
    const tot = e.reduce((s, x) => s + x[1], 0) || 1;
    return e.filter((x, i) => i === 0 || x[1] / tot >= 0.15).slice(0, 3).map((x) => x[0]);
  },
  async _make(p, mode) {
    const clusters = await load("clusters");
    const field = this.fieldOf(p);
    const name = Object.fromEntries(clusters.map((c) => [c.id, c.name]));
    return { id: p.id, n: p.n, field, fieldNames: field.map((c) => name[c]), ins: p.ins || [], kw: p.kw || [], mode: mode || "me" };
  },
  async set(p, mode) { const v = await this._make(p, mode || (this._stored() || {}).mode); this._save(v); return v; },
  clear() { this._save(null); },
  setMode(m) { const s = this._stored(); if (s) { s.mode = m; this._save(s); } },
  // resolves to the current person ({id, n, field, fieldNames, ins, kw, mode}) or null
  ready: null,
  // does this paper (papers.json record) belong to the highlight?
  isMine(paper, me) { return !!me && (paper.p || []).includes(me.id); },
  inField(paper, me) { return !!me && me.field.includes(paper.cl); },
  hit(paper, me) { return !!me && (me.mode === "field" ? this.inField(paper, me) : this.isMine(paper, me)); },
};
Me.ready = (async () => {
  const url = new URLSearchParams(location.search).get("me");
  if (url === "") { Me.clear(); return null; }
  const s = Me._stored();
  if (url && (!s || s.id !== url)) {
    const people = await load("people");
    const p = people.find((x) => x.id === url);
    if (!p) return s;
    return Me.set(p, s && s.mode);
  }
  if (s) {
    // the stored subfield names can be out of date (theme names were revised); look them up again
    const name = Object.fromEntries((await load("clusters")).map((c) => [c.id, c.name]));
    s.fieldNames = s.field.map((c) => name[c] || "");
    Me._save(s);
  }
  return s;
})().catch(() => null);

function meLinks(me) {
  // keep ?me= on links between the pages of this site, so the view survives without browser storage and can be shared
  document.querySelectorAll("a[href]").forEach((a) => {
    const h = a.getAttribute("href");
    if (!/^[a-z]+\.html(#.*)?$/.test(h)) return;
    const [page, hash] = h.split("#");
    a.setAttribute("href", `${page}?me=${encodeURIComponent(me.id)}${hash ? "#" + hash : ""}`);
  });
}
document.addEventListener("DOMContentLoaded", () => {
  Me.ready.then((me) => {
    if (!me) return;
    const header = document.querySelector("header.site");
    if (!header) return;
    const bar = document.createElement("div");
    bar.className = "me-bar";
    const field = me.fieldNames.join("; ");
    bar.innerHTML = `<span>Viewing as <a href="people.html#${encodeURIComponent(me.id)}"><b>${esc(me.n)}</b></a></span>
      <span class="seg" role="group" aria-label="What to highlight">
        <button type="button" data-v="me" aria-pressed="${me.mode !== "field"}">Highlight me</button>
        <button type="button" data-v="field" aria-pressed="${me.mode === "field"}" title="${esc(field)}">Highlight my subfield</button></span>
      <span class="me-field muted small">${me.mode === "field" ? "Subfield: " + esc(field) : ""}</span>
      <span class="me-actions"><a href="index.html#find">change person</a> · <a href="#" id="me-stop">stop</a></span>`;
    header.insertAdjacentElement("afterend", bar);
    bar.querySelectorAll(".seg button").forEach((b) => b.addEventListener("click", () => {
      if (b.dataset.v === me.mode) return;
      Me.setMode(b.dataset.v); location.reload();
    }));
    bar.querySelector("#me-stop").addEventListener("click", (e) => {
      e.preventDefault(); Me.clear();
      const u = new URL(location.href); u.searchParams.delete("me"); location.href = u.toString();
    });
    meLinks(me);
  });
});
