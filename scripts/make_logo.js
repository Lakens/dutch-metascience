// Draws the final Dutch Metascience logo (two joined wind turbines with tulips as a bar chart on the left)
// and writes two scalable SVG files: the mark alone, and the mark with the name.
// Usage: node make_logo.js <output folder>
const fs = require("fs"), path = require("path");
const out = process.argv[2];
const C = { blue: "#2a78d6", orange: "#eb6834", green: "#1baf7a", yellow: "#eda100", pink: "#e87ba4", purple: "#6250d6", red: "#e34948" };
const r1 = (v) => Math.round(v * 10) / 10;
const GROUND = 100;
function tulip(x, h, color) {
  const yb = GROUND - h, t = yb - 7;
  return `<path d="M${x} ${GROUND} V${yb}" stroke="${C.green}" stroke-width="1.8" stroke-linecap="round"/>` +
    `<path d="M${x} ${GROUND - 1} C${x - 4.5} ${GROUND - 4} ${x - 5} ${GROUND - 8} ${x - 4.5} ${GROUND - 11} C${x - 2.5} ${GROUND - 8} ${x - 1} ${GROUND - 5} ${x} ${GROUND - 1} Z" fill="${C.green}"/>` +
    `<path d="M${x - 3.6} ${t + 1} L${x - 1.8} ${t + 3.2} L${x} ${t} L${x + 1.8} ${t + 3.2} L${x + 3.6} ${t + 1} C${x + 3.6} ${yb - 1} ${x + 2} ${yb} ${x} ${yb} C${x - 2} ${yb} ${x - 3.6} ${yb - 1} ${x - 3.6} ${t + 1} Z" fill="${color}"/>`;
}
function blade(hx, hy, deg, len) {
  const a = (deg * Math.PI) / 180, ux = Math.cos(a), uy = Math.sin(a), px = -uy, py = ux;
  const P = (d, o) => `${r1(hx + ux * d + px * o)} ${r1(hy + uy * d + py * o)}`;
  return `<path d="M${P(0, -1.6)} L${P(len * 0.25, -2.6)} L${P(len, 0)} L${P(len * 0.25, 2.2)} L${P(0, 1.6)} Z" class="ink"/>`;
}
const tip = (hx, hy, deg, len) => [r1(hx + Math.cos((deg * Math.PI) / 180) * len), r1(hy + Math.sin((deg * Math.PI) / 180) * len)];
const node = (p, r, col) => `<circle cx="${p[0]}" cy="${p[1]}" r="${r}" fill="${col}"/>`;

function mark() {
  const A = [62, 36, 26], B = [96, 60, 17];               // hub x, hub y, blade length of the large and the small turbine
  const angA = [-90, 30, 150], angB = [-60, 60, 180];
  const tA = angA.map((d) => tip(A[0], A[1], d, A[2])), tB = angB.map((d) => tip(B[0], B[1], d, B[2]));
  const pairs = [[tA[0], tA[1]], [tA[1], tA[2]], [tA[2], tA[0]], [tB[0], tB[1]], [tB[1], tB[2]], [tB[2], tB[0]],
                 [tA[1], tB[2]], [tA[1], tB[0]], [tA[0], tB[0]]];   // each turbine's people, and the links between the two
  return [
    `<path d="M8 ${GROUND} H112" class="ink-line" stroke-width="3" stroke-linecap="round"/>`,
    `<path d="${pairs.map(([a, b]) => `M${a[0]} ${a[1]} L${b[0]} ${b[1]}`).join(" ")}" fill="none" class="ink-line" stroke-width="1.5" stroke-linecap="round" opacity="0.45"/>`,
    `<polygon points="60.6,${GROUND} 63.4,${GROUND} 62.7,38 61.3,38" class="ink"/>`,
    `<rect x="58.2" y="33.6" width="8.6" height="4.8" rx="1.8" class="ink"/>`,
    `<polygon points="94.9,${GROUND} 97.1,${GROUND} 96.5,61.5 95.5,61.5" class="ink"/>`,
    `<rect x="92.8" y="58" width="6.6" height="3.8" rx="1.5" class="ink"/>`,
    ...angA.map((d) => blade(A[0], A[1], d, A[2])), ...angB.map((d) => blade(B[0], B[1], d, B[2])),
    `<circle cx="${A[0]}" cy="${A[1]}" r="2.4" class="ink"/>`, `<circle cx="${B[0]}" cy="${B[1]}" r="2" class="ink"/>`,
    ...[C.blue, C.orange, C.green].map((c, i) => node(tA[i], 5, c)), ...[C.pink, C.yellow, C.purple].map((c, i) => node(tB[i], 4, c)),
    ...[[10, 30, C.orange], [19, 18, C.red], [28, 36, C.yellow], [37, 24, C.pink]].map(([x, h, c]) => tulip(x, h, c)),
  ].join("\n  ");
}
// a traditional sail: the stock (arm) plus a lattice frame on one side of its outer part
function sail(hx, hy, deg, len, w) {
  const a = (deg * Math.PI) / 180, ux = Math.cos(a), uy = Math.sin(a), px = -uy, py = ux;
  const P = (d, o) => [r1(hx + ux * d + px * o), r1(hy + uy * d + py * o)];
  const q = [P(len * 0.28, 0), P(len, 0), P(len, w), P(len * 0.28, w)];
  const bars = [0.46, 0.64, 0.82].map((f) => { const [a1, b1] = P(len * f, 0), [a2, b2] = P(len * f, w); return `M${a1} ${b1} L${a2} ${b2}`; }).join(" ");
  const [tx, ty] = P(len, 0);
  return `<path d="M${hx} ${hy} L${tx} ${ty}" class="ink-line" stroke-width="${len > 20 ? 3 : 2.8}" stroke-linecap="round"/>` +
    `<path d="M${q.map((p) => p.join(" ")).join(" L")} Z ${bars}" fill="none" class="ink-line" stroke-width="${len > 20 ? 1.4 : 1.25}" stroke-linejoin="round"/>`;
}
// a smock mill: tapered body, stage, cap, four lattice sails; s scales the whole mill
function smock(cx, s) {
  const hy = GROUND - 60 * s, P = (x, y) => `${r1(cx + x * s)},${r1(GROUND - y * s)}`;
  return `<polygon points="${P(-9, 0)} ${P(9, 0)} ${P(5.5, 54)} ${P(-5.5, 54)}" class="ink"/>` +
    `<path d="M${r1(cx - 13 * s)} ${r1(GROUND - 34 * s)} H${r1(cx + 13 * s)}" class="ink-line" stroke-width="${r1(2.6 * Math.sqrt(s))}" stroke-linecap="round"/>` +
    `<path d="M${r1(cx - 7.5 * s)} ${r1(GROUND - 53.5 * s)} Q${cx} ${r1(GROUND - 66 * s)} ${r1(cx + 7.5 * s)} ${r1(GROUND - 53.5 * s)} Z" class="ink"/>` +
    `<circle cx="${cx}" cy="${r1(hy)}" r="${r1(2.4 * Math.sqrt(s))}" class="ink"/>`;
}
function markMills() {
  const A = [62, 1, 26, [-135, -45, 45, 135]], B = [100, 0.62, 18, [-135, -45, 45, 135]];   // x, scale, sail length, sail angles
  const hub = (m) => [m[0], r1(GROUND - 60 * m[1])];
  const tA = A[3].map((d) => tip(...hub(A), d, A[2])), tB = B[3].map((d) => tip(...hub(B), d, B[2]));
  const pairs = [[tA[0], tA[1]], [tA[1], tA[2]], [tA[3], tA[0]], [tB[0], tB[1]], [tB[1], tB[2]], [tB[2], tB[3]], [tB[3], tB[0]],
                 [tA[2], tB[3]], [tA[2], tB[0]], [tA[1], tB[0]]];   // each mill's people, and the links between the two mills
  return [
    `<path d="M6 ${GROUND} H114" class="ink-line" stroke-width="3" stroke-linecap="round"/>`,
    `<path d="${pairs.map(([a, b]) => `M${a[0]} ${a[1]} L${b[0]} ${b[1]}`).join(" ")}" fill="none" class="ink-line" stroke-width="1.5" stroke-linecap="round" opacity="0.45"/>`,
    smock(A[0], A[1]), smock(B[0], B[1]),
    ...A[3].map((d) => sail(...hub(A), d, A[2], 5)), ...B[3].map((d) => sail(...hub(B), d, B[2], 3.8)),
    ...[C.blue, C.orange, C.green, C.pink].map((c, i) => node(tA[i], 5, c)), ...[C.yellow, C.purple, C.red, C.blue].map((c, i) => node(tB[i], 3.8, c)),
    ...[[8, 30, C.orange], [16, 18, C.red], [24, 36, C.yellow], [32, 24, C.pink]].map(([x, h, c]) => tulip(x, h, c)),
  ].join("\n  ");
}
// the dark lines follow the reader's light or dark setting (also when used as a browser-tab icon)
const STYLE = `<style>
    .ink { fill: #1b2430; } .ink-line { stroke: #1b2430; }
    @media (prefers-color-scheme: dark) { .ink { fill: #eef2f4; } .ink-line { stroke: #eef2f4; } }
  </style>`;
const TITLE = "Dutch Metascience";
const markSvg = (body) => `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 120" role="img" aria-label="${TITLE}">
  <title>${TITLE}</title>
  ${STYLE}
  ${body}
</svg>
`;
const nameSvg = (body) => `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 372 120" role="img" aria-label="${TITLE}">
  <title>${TITLE}</title>
  ${STYLE.replace("</style>", `  .name { font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; }
  </style>`)}
  <g>
  ${body}
  </g>
  <text x="132" y="57" class="ink name" font-size="38" font-weight="700" letter-spacing="-0.5">Dutch</text>
  <text x="132" y="98" class="ink name" font-size="38" font-weight="700" letter-spacing="-0.5">Metascience</text>
</svg>
`;
// turbines: dutch-metascience-logo(-mark).svg; traditional mills: dutch-metascience-logo-mills(-mark).svg
for (const [suffix, body] of [["", mark()], ["-mills", markMills()]]) {
  fs.writeFileSync(path.join(out, `dutch-metascience-logo${suffix}-mark.svg`), markSvg(body));
  fs.writeFileSync(path.join(out, `dutch-metascience-logo${suffix}.svg`), nameSvg(body));
}
// for the website header: the mills logo with a fixed ink colour for light and for dark pages, because the site has its
// own light/dark switch, which an SVG shown as an image cannot follow
const fixed = (svg, ink) => svg.replace(/<style>[\s\S]*?<\/style>/,
  `<style>.ink { fill: ${ink}; } .ink-line { stroke: ${ink}; } .name { font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; }</style>`);
fs.writeFileSync(path.join(out, "dutch-metascience-logo-mills-on-light.svg"), fixed(nameSvg(markMills()), "#1b2430"));
fs.writeFileSync(path.join(out, "dutch-metascience-logo-mills-on-dark.svg"), fixed(nameSvg(markMills()), "#f0efec"));
console.log("written");
