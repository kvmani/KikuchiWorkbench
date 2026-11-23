// Build the KikuchiWorkbench progress-review deck from artifacts in $KWB_ARTIFACTS_DIR (default ~/kwb_review_artifacts).
// Usage: NODE_PATH=<dir with pptxgenjs> node tools/build_review_deck.js
// KikuchiWorkbench progress review — Mani's slide style (black ribbons, Arial, text left, bordered graphic right)
const pptxgen = require("pptxgenjs");
const path = require("path");
// Optional: set KWB_APPLY_THEME to the path of an apply_theme.js helper to write theme colours.
const applyTheme = process.env.KWB_APPLY_THEME ? require(process.env.KWB_APPLY_THEME).applyTheme : null;

// Artifacts (screenshots, maps, deck) live OUTSIDE the repository: no binary files in Git.
const ART = process.env.KWB_ARTIFACTS_DIR || path.join(require("os").homedir(), "kwb_review_artifacts");
const IMG = (p) => path.join(ART, p.replace(/^docs\//, ""));
const OUT = path.join(ART, "review", "KikuchiWorkbench_progress_review.pptx");

const THEME = {
  name: "Mani Black and White",
  headFontFace: "Arial",
  bodyFontFace: "Arial",
  colors: {
    dk1: "000000", lt1: "FFFFFF", dk2: "000000", lt2: "F2F2F2",
    accent1: "000000", accent2: "595959", accent3: "8C8C8C", accent4: "BFBFBF",
    accent5: "D9D9D9", accent6: "404040", hlink: "000000", folHlink: "595959",
  },
};

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE"; // 13.333 x 7.5 in
pres.theme = { headFontFace: "Arial", bodyFontFace: "Arial" };
pres.title = "KikuchiWorkbench progress review";
const C = pres.SchemeColor;

const W = 13.333, H = 7.5;
const TOP_H = 0.85, BOT_H = 0.7;
const LX = 0.5, LW = 4.55;              // left text column (~36%)
const GX = 5.35, GW = W - GX - 0.45;    // right graphic frame
const GY = TOP_H + 0.35, GH = H - BOT_H - 0.35 - GY;

pres.defineSlideMaster({
  title: "MANI_RIBBONS",
  background: { color: "FFFFFF" },
  objects: [
    { rect: { x: 0, y: 0, w: W, h: TOP_H, fill: { color: "000000" }, line: { color: "000000" } } },
    { rect: { x: 0, y: H - BOT_H, w: W, h: BOT_H, fill: { color: "000000" }, line: { color: "000000" } } },
    { placeholder: { options: { name: "title", type: "title", x: 0.4, y: 0, w: W - 0.8, h: TOP_H,
        fontFace: "Arial", fontSize: 28, bold: true, color: C.background1, align: "center", valign: "middle", margin: 0 },
        text: "" } },
    { placeholder: { options: { name: "bottomline", type: "body", x: 0.4, y: H - BOT_H, w: W - 0.8, h: BOT_H,
        fontFace: "Arial", fontSize: 18, color: C.background1, align: "center", valign: "middle", margin: 0 },
        text: "" } },
  ],
});

function frame(slide, name) {
  slide.addShape(pres.shapes.RECTANGLE, { x: GX, y: GY, w: GW, h: GH, fill: { color: "FFFFFF" },
    line: { color: "000000", width: 1 }, objectName: name || "graphic frame" });
}

function base(title, bottom, statements) {
  const s = pres.addSlide({ masterName: "MANI_RIBBONS" });
  s.addText(title, { placeholder: "title" });
  s.addText(bottom, { placeholder: "bottomline" });
  const runs = [];
  statements.forEach((t, i) => {
    const last = i === statements.length - 1;
    if (typeof t === "string") {
      runs.push({ text: t, options: { breakLine: !last, paraSpaceAfter: 18 } });
    } else {
      runs.push({ text: t.b, options: { bold: true, breakLine: false } });
      runs.push({ text: " " + t.t, options: { breakLine: !last, paraSpaceAfter: 18 } });
    }
  });
  s.addText(runs, { x: LX, y: GY, w: LW, h: GH, fontFace: "Arial", fontSize: 17, color: C.text1,
    valign: "middle", margin: 0, isTextBox: true, objectName: "statements" });
  return s;
}

function box(s, x, y, w, h, text, opt = {}) {
  s.addShape(pres.shapes.RECTANGLE, { x, y, w, h, fill: { color: opt.fill || "FFFFFF" },
    line: { color: "000000", width: opt.lw || 1 } });
  s.addText(text, { x, y, w, h, fontFace: "Arial", fontSize: opt.fs || 13, bold: !!opt.bold,
    color: opt.color || "000000", align: "center", valign: "middle", margin: 3, isTextBox: true });
}
function arrow(s, x1, y1, x2, y2) {
  s.addShape(pres.shapes.LINE, { x: Math.min(x1, x2), y: Math.min(y1, y2), w: Math.abs(x2 - x1) || 0.001,
    h: Math.abs(y2 - y1) || 0.001, flipH: x2 < x1, flipV: y2 < y1,
    line: { color: "000000", width: 1.25, endArrowType: "triangle" } });
}
function img(s, file, x, y, w, h) { s.addImage({ path: IMG(file), x, y, w, h }); }
function caption(s, text, x, y, w) {
  s.addText(text, { x, y, w, h: 0.3, fontFace: "Arial", fontSize: 11, color: "404040", align: "center",
    margin: 0, isTextBox: true });
}

// ---------------------------------------------------------------- 1 Title
{
  const s = base("KikuchiWorkbench: progress review",
    "First real-data results: raw Oxford scan to phase and orientation maps",
    [{ b: "What:", t: "desktop workbench and headless runner for master-pattern EBSD dictionary indexing." },
     { b: "Status:", t: "early development, not yet a release candidate." },
     { b: "Date:", t: "23 November 2026." }]);
  frame(s);
  img(s, "docs/review/alsi_phase_ipf.png", GX + 0.25, GY + 0.75, GW - 0.5, (GW - 0.5) * 840 / 2000);
  caption(s, "Al–10Si, public Oxford scan, 3000-point region indexed with the workbench", GX + 0.25, GY + GH - 0.6, GW - 0.5);
}

// ---------------------------------------------------------------- 2 Goal
{
  const s = base("What is the goal?", "A guided, reproducible path from raw scan to phase decision",
    ["Take a raw Oxford or EDAX/TSL scan and candidate crystal structures to phase and orientation maps.",
     "Simulate dynamical master patterns with EMsoft from a CIF, natively on Windows 11.",
     "Show when two similar cubic phases can, or cannot, be told apart."]);
  frame(s);
  const steps = [["1", "Open a scan", "Oxford / EDAX-TSL"], ["2", "Add phases", "CIF or EMsoft master"],
    ["3", "Masters", "EMsoft MC + dynamical"], ["4", "Geometry", "PC calibration"],
    ["5", "Build & match", "dictionary indexing"], ["6", "Inspect & export", "maps, CSV, manifest"]];
  const bw = 1.95, bh = 1.35, gx = 0.45, x0 = GX + (GW - (3 * 1.95 + 2 * 0.45)) / 2, y0 = GY + 0.55;
  steps.forEach((st, i) => {
    const r = Math.floor(i / 3), c = r === 0 ? i % 3 : 2 - (i % 3);
    const x = x0 + c * (bw + gx), y = y0 + r * (bh + 1.05);
    s.addShape(pres.shapes.RECTANGLE, { x, y, w: bw, h: bh, fill: { color: i === 5 ? "000000" : "FFFFFF" }, line: { color: "000000", width: 1.25 } });
    s.addText([{ text: st[0] + "  " + st[1], options: { bold: true, fontSize: 15, breakLine: true } },
      { text: st[2], options: { fontSize: 12 } }],
      { x, y, w: bw, h: bh, fontFace: "Arial", color: i === 5 ? "FFFFFF" : "000000", align: "center", valign: "middle", margin: 4, isTextBox: true });
  });
  const yA = y0 + bh / 2;
  arrow(s, x0 + bw, yA, x0 + bw + gx, yA);
  arrow(s, x0 + 2 * bw + gx, yA, x0 + 2 * bw + 2 * gx, yA);
  arrow(s, x0 + 2.5 * bw + 2 * gx, y0 + bh, x0 + 2.5 * bw + 2 * gx, y0 + bh + 1.05);
  const yB = y0 + bh + 1.05 + bh / 2;
  arrow(s, x0 + 2 * bw + 2 * gx, yB, x0 + 2 * bw + gx, yB);
  arrow(s, x0 + bw + gx, yB, x0 + bw, yB);
  caption(s, "Six-step guided workflow from the project scope", GX, GY + GH - 0.55, GW);
}

// ---------------------------------------------------------------- 3 Science question
{
  const s = base("Can full patterns separate similar cubic phases?",
    "Only band widths and intensities carry the phase signal",
    ["Same space group means the same band positions.",
     "A 2.6% lattice difference changes band widths by about 2.6%.",
     "Projection-centre error, noise and model mismatch can hide that difference."]);
  frame(s);
  const rows = [["", "Ni", "Cu"], ["Structure", "FCC, Fm-3m", "FCC, Fm-3m"], ["Lattice parameter", "3.524 Å", "3.615 Å"],
    ["Band positions", "identical", "identical"], ["Band widths", "narrower", "≈ 2.6% wider"], ["Intensities", "Z = 28", "Z = 29"]];
  const opt = { fontFace: "Arial", fontSize: 16, color: "000000", valign: "middle", align: "center", border: { type: "solid", pt: 1, color: "000000" } };
  const data = rows.map((r, i) => r.map((c, j) => ({ text: c, options: i === 0 ? { ...opt, bold: true, fill: { color: "000000" }, color: "FFFFFF" } :
    j === 0 ? { ...opt, bold: true, align: "left", fill: { color: "F2F2F2" } } : { ...opt, fill: { color: (i === 3 || i === 4) ? "D9D9D9" : "FFFFFF" } } })));
  s.addTable(data, { x: GX + 0.6, y: GY + 0.8, w: GW - 1.2, colW: [2.6, (GW - 1.2 - 2.6) / 2, (GW - 1.2 - 2.6) / 2], rowH: 0.62 });
  caption(s, "Benchmark pair from the scope: simulated Ni and Cu end members", GX, GY + GH - 0.6, GW);
}

// ---------------------------------------------------------------- 4 Architecture
{
  const s = base("How is the software built?", "The GUI and the command line run the same tested core",
    ["One Python core serves both a PySide6 desktop app and the kwb command line.",
     "Long jobs run in workers with progress, cancel and logs.",
     "Every run writes a versioned manifest of inputs, settings and events."]);
  frame(s);
  const x0 = GX + 0.35, w = GW - 0.7;
  box(s, x0, GY + 0.45, w / 2 - 0.15, 0.75, "Desktop GUI (PySide6)", { bold: true, fs: 15 });
  box(s, x0 + w / 2 + 0.15, GY + 0.45, w / 2 - 0.15, 0.75, "Command line (kwb)", { bold: true, fs: 15 });
  arrow(s, x0 + w / 4, GY + 1.2, x0 + w / 4, GY + 1.6);
  arrow(s, x0 + 3 * w / 4, GY + 1.2, x0 + 3 * w / 4, GY + 1.6);
  s.addShape(pres.shapes.RECTANGLE, { x: x0, y: GY + 1.6, w, h: 2.0, fill: { color: "F2F2F2" }, line: { color: "000000", width: 1.25 } });
  s.addText("Shared core", { x: x0, y: GY + 1.62, w, h: 0.4, fontFace: "Arial", fontSize: 14, bold: true, align: "center", margin: 0, isTextBox: true });
  const mods = ["Import", "Geometry", "Masters", "Dictionary", "Matching", "Decision", "Export", "Jobs & cache"];
  const mw = (w - 0.3 - 3 * 0.15) / 4;
  mods.forEach((m, i) => box(s, x0 + 0.15 + (i % 4) * (mw + 0.15), GY + 2.1 + Math.floor(i / 4) * 0.7, mw, 0.55, m, { fs: 13 }));
  arrow(s, x0 + w / 2, GY + 3.6, x0 + w / 2, GY + 4.0);
  const ext = ["EMsoft 5", "kikuchipy", "orix", "NumPy / PyTorch"];
  const ew = (w - 3 * 0.15) / 4;
  ext.forEach((e, i) => box(s, x0 + i * (ew + 0.15), GY + 4.0, ew, 0.65, e, { fill: "000000", color: "FFFFFF", bold: true, fs: 13 }));
  caption(s, "External tools: simulation, readers and projection, orientations, compute", GX, GY + GH - 0.45, GW);
}

// ---------------------------------------------------------------- 5 Algorithm
{
  const s = base("How is each pattern indexed?", "Dictionary indexing with equal effort for every candidate phase",
    ["Experimental patterns are compared with simulated patterns from each phase's master.",
     "The best match (normalised cross-correlation) gives orientation and phase.",
     "Batches stay bounded, so large scans fit in memory."]);
  frame(s);
  const st = [["Preprocess", "static + dynamic background removal; raw data never changed"],
    ["Sample orientations", "symmetry-reduced grid, same step for all phases"],
    ["Project dictionary", "master → detector in bounded chunks, verified cache"],
    ["Match", "NCC, top-k per phase, CPU or CUDA, deterministic ties"],
    ["Refine", "local search, identical budget for every phase"],
    ["Decide", "indexed / ambiguous / unindexed / low signal"]];
  const x0 = GX + 0.45, bw = 2.45, bh = 0.62, gap = 0.18, y0 = GY + 0.3;
  st.forEach((t, i) => {
    const y = y0 + i * (bh + gap);
    box(s, x0, y, bw, bh, t[0], { bold: true, fs: 14, fill: i === 5 ? "000000" : "FFFFFF", color: i === 5 ? "FFFFFF" : "000000" });
    s.addText(t[1], { x: x0 + bw + 0.3, y, w: GW - bw - 1.2, h: bh, fontFace: "Arial", fontSize: 13, color: "000000", valign: "middle", margin: 0, isTextBox: true });
    if (i < st.length - 1) arrow(s, x0 + bw / 2, y + bh, x0 + bw / 2, y + bh + gap);
  });
}

// ---------------------------------------------------------------- 6 Decision
{
  const s = base("How is a phase decided?", "Ambiguity is reported, not hidden",
    ["Each phase keeps its own best score.",
     "The phase margin is best minus runner-up; it ranks, it is not a probability.",
     "Thresholds are chosen on development data and frozen before held-out runs."]);
  frame(s);
  // schematic bars
  const bx = GX + 0.4, by = GY + 0.7, bwid = 0.85, scale = 3.0;
  const bars = [["Phase A", 0.62, "000000"], ["Phase B", 0.48, "8C8C8C"]];
  bars.forEach((b, i) => {
    const h = b[1] * scale; const x = bx + i * (bwid + 0.35);
    s.addShape(pres.shapes.RECTANGLE, { x, y: by + scale - h, w: bwid, h, fill: { color: b[2] }, line: { color: "000000" } });
    s.addText(b[0], { x: x - 0.2, y: by + scale + 0.05, w: bwid + 0.4, h: 0.35, fontFace: "Arial", fontSize: 13, align: "center", margin: 0, isTextBox: true });
  });
  s.addShape(pres.shapes.LINE, { x: bx, y: by + scale - 0.62 * scale, w: 2 * bwid + 0.6, h: 0, line: { color: "000000", dashType: "dash", width: 1 } });
  s.addShape(pres.shapes.LINE, { x: bx + bwid + 0.35 + bwid + 0.12, y: by + scale - 0.62 * scale, w: 0, h: (0.62 - 0.48) * scale, line: { color: "000000", width: 1.5, beginArrowType: "triangle", endArrowType: "triangle" } });
  s.addText("margin", { x: bx + 2 * bwid + 0.5, y: by + scale - 0.6 * scale, w: 0.9, h: 0.4, fontFace: "Arial", fontSize: 13, margin: 0, isTextBox: true });
  // rule table
  const rx = GX + 3.35, rw = GW - 3.35 - 0.3;
  const rules = [["Label", "Rule"], ["indexed", "margin above threshold"], ["ambiguous", "margin at or below threshold, or exact tie"],
    ["unindexed", "best score below minimum"], ["low signal", "pattern contrast too low"], ["missing", "no pattern recorded"]];
  const o = { fontFace: "Arial", fontSize: 13, color: "000000", valign: "middle", border: { type: "solid", pt: 1, color: "000000" } };
  s.addTable(rules.map((r, i) => r.map((c, j) => ({ text: c, options: i === 0 ? { ...o, bold: true, color: "FFFFFF", fill: { color: "000000" } } : { ...o, bold: j === 0 } }))),
    { x: rx, y: GY + 0.5, w: rw, colW: [1.35, rw - 1.35], rowH: 0.6 });
  caption(s, "Phase identification, orientation fit and signal stay separate in maps and exports", GX, GY + GH - 0.55, GW);
}

// ---------------------------------------------------------------- 7 Validation vs EMsoft
{
  const s = base("Do our geometry conventions match EMsoft?", "The workbench reproduces EMsoft's own pattern (NCC 0.99996)",
    ["Reference: a pattern EMsoft 4.2 projected itself, with an off-centre projection centre and 10° detector tilt.",
     "Our import, centre conversion and rotations reproduce it.",
     "Each deliberate convention error drops the match to about zero."]);
  frame(s);
  const labels = ["Documented convention", "Wrong xpc sign", "Vertical mirror", "Horizontal mirror", "φ1 + 90° (HKL vs TSL)", "φ1 ↔ φ2 swapped"];
  const vals = [0.99996, 0.0012, -0.0107, -0.0367, 0.0767, 0.0296];
  s.addChart(pres.charts.BAR, [{ name: "NCC with EMsoft pattern", labels, values: vals }], {
    x: GX + 0.25, y: GY + 0.25, w: GW - 0.5, h: GH - 0.5, barDir: "bar", catAxisOrientation: "maxMin",
    chartColors: ["404040"], showValue: true, dataLabelPosition: "outEnd", dataLabelFormatCode: "0.000",
    dataLabelFontSize: 12, dataLabelFontFace: "Arial", dataLabelColor: "000000",
    catAxisLabelFontFace: "Arial", catAxisLabelFontSize: 13, catAxisLabelColor: "000000",
    valAxisLabelFontFace: "Arial", valAxisLabelFontSize: 11, valAxisLabelColor: "404040",
    catAxisLabelPos: "low", valAxisMinVal: -0.2, valAxisMaxVal: 1.2, valGridLine: { color: "D9D9D9", size: 0.5 }, catGridLine: { style: "none" },
    showLegend: false, showTitle: true, title: "Normalised cross-correlation with EMsoft's pattern", titleFontFace: "Arial", titleFontSize: 14, titleColor: "000000",
  });
}

// ---------------------------------------------------------------- 8 GUI
{
  const s = base("What does the user see?", "Every decision can be checked pixel by pixel",
    ["Six guided steps on the left; maps, candidates and patterns on the right.",
     "Click a pixel: measured pattern beside the best simulation of each phase.",
     "Jobs run in the background with progress, cancel and a log."]);
  frame(s);
  const w = GW - 0.3, h = w * 595 / 1245;
  img(s, "docs/review/crop_inspect_si.png", GX + 0.15, GY + (GH - h) / 2 - 0.2, w, h);
  caption(s, "Si pixel: measured pattern, best Al and best Si simulations; Si wins by 0.08 NCC", GX, GY + GH - 0.55, GW);
}

// ---------------------------------------------------------------- 9 Calibration
{
  const s = base("How is the detector geometry fixed?", "One calibrated geometry is shared by all phases",
    ["The .ebsp file stores no projection centre; we start from the authors' estimate.",
     "Twelve high-signal Al points refine orientation and centre together.",
     "Result (0.500, 0.139, 1.238); simulated and measured bands line up."]);
  frame(s);
  const w = GW - 0.3, h = w * 575 / 1245;
  img(s, "docs/review/crop_geometry_compare.png", GX + 0.15, GY + (GH - h) / 2 - 0.2, w, h);
  caption(s, "GUI step 4 after calibration: experimental, simulated and residual", GX, GY + GH - 0.55, GW);
}

// ---------------------------------------------------------------- 10 Al-Si results
{
  const s = base("Al–10Si: does it work on a real scan?", "Si particles resolved in the Al matrix; ambiguity only at boundaries",
    [{ b: "Data:", t: "public Oxford .ebsp, 75,551 patterns; EMsoft Al and Si masters." },
     { b: "Region:", t: "3000 points: 2987 indexed, 13 ambiguous, 0 unindexed." },
     { b: "Time:", t: "about 2–4 min in the GUI on 4 CPU cores." },
     { b: "To check:", t: "a narrow band of scattered Al orientations; no reference map yet." }]);
  frame(s);
  const w = GW - 0.4, h = w * 840 / 2000;
  img(s, "docs/review/alsi_phase_ipf.png", GX + 0.2, GY + 0.35, w, h);
  img(s, "docs/review/ipf_key_m3m.png", GX + GW - 2.0, GY + 0.45 + h, 1.5, 1.36);
  s.addText("Al/Si phase margins reach about 0.2 NCC — 100 times the Ni/Cu margins.", { x: GX + 0.3, y: GY + 0.6 + h, w: GW - 2.6, h: 1.0,
    fontFace: "Arial", fontSize: 14, color: "000000", valign: "middle", margin: 0, isTextBox: true });
}

// ---------------------------------------------------------------- 11 Ni/Cu benchmark
{
  const s = base("Can Ni and Cu be told apart?", "Same-structure phases need near-perfect simulations to separate",
    ["Synthetic test with kinematical masters; margins are only about 0.001 NCC.",
     "Refinement helps when simulation matches the data; mismatch drops accuracy towards chance.",
     "A false perfect separation was traced to a reflector cutoff and removed."]);
  frame(s);
  const labels = ["Matched simulation, grid only", "Matched simulation, refined", "Matched coarse, refined", "Mismatched, refined", "Chance"];
  s.addChart(pres.charts.BAR, [{ name: "Forced-choice accuracy", labels, values: [70, 93, 88, 63, 50] }], {
    x: GX + 0.25, y: GY + 0.25, w: GW - 0.5, h: GH - 0.5, barDir: "bar", catAxisOrientation: "maxMin",
    chartColors: ["404040"], showValue: true, dataLabelPosition: "outEnd", dataLabelFormatCode: "0\"%\"",
    dataLabelFontSize: 12, dataLabelFontFace: "Arial", dataLabelColor: "000000",
    catAxisLabelFontFace: "Arial", catAxisLabelFontSize: 13, catAxisLabelColor: "000000",
    valAxisLabelFontFace: "Arial", valAxisLabelFontSize: 11, valAxisLabelColor: "404040",
    valAxisMinVal: 0, valAxisMaxVal: 100, valGridLine: { color: "D9D9D9", size: 0.5 }, catGridLine: { style: "none" },
    showLegend: false, showTitle: true, title: "Pixels where the true phase scores higher (Ni vs Cu, %)", titleFontFace: "Arial", titleFontSize: 14, titleColor: "000000",
  });
}

// ---------------------------------------------------------------- 12 Where are we
{
  const s = base("Where are we?", "Core, GUI and first real-data run are done; hardware gates remain",
    [{ b: "Tests:", t: "110 automated tests pass on Linux and Windows CI." },
     { b: "Real data:", t: "Oxford Al–Si run end to end." },
     { b: "Blocked:", t: "native EMsoft on Windows, CUDA, EDAX/TSL exports." }]);
  frame(s);
  const rows = [["Work package", "Status"],
    ["Conventions, importers, CIF, masters", "Done"], ["Indexing core, refinement, calibration", "Done"],
    ["GUI (guided, workers, inspection)", "Done"], ["Oxford real-data run (Al–Si)", "Done"],
    ["Ni/Cu synthetic benchmark", "Interim (kinematical)"], ["EMsoft adapter", "Mock-tested only"],
    ["Native Windows EMsoft run", "Blocked: lab PC"], ["EDAX/TSL real export", "Blocked: data"],
    ["CPU/GPU parity", "Blocked: CUDA GPU"]];
  const o = { fontFace: "Arial", fontSize: 13, color: "000000", valign: "middle", border: { type: "solid", pt: 1, color: "000000" } };
  const shade = (st) => st.startsWith("Done") ? "FFFFFF" : st.startsWith("Blocked") ? "BFBFBF" : "E6E6E6";
  s.addTable(rows.map((r, i) => r.map((c, j) => ({ text: c, options: i === 0 ? { ...o, bold: true, color: "FFFFFF", fill: { color: "000000" } } :
    { ...o, bold: j === 1 && !r[1].startsWith("Done"), fill: { color: shade(r[1]) } } }))),
    { x: GX + 0.4, y: GY + 0.35, w: GW - 0.8, colW: [4.3, GW - 0.8 - 4.3], rowH: 0.44 });
  caption(s, "White: done   Light grey: partial   Dark grey: blocked on lab hardware or data", GX, GY + GH - 0.5, GW);
}

// ---------------------------------------------------------------- 13 Next
{
  const s = base("What next?", "Lab hardware and data unlock the release gates",
    ["Each step has a ready script and checklist in docs/lab_handoff.md.",
     "Steps 1–3 need the lab workstation; 4–5 follow from their results."]);
  frame(s);
  const st = [["1", "Native EMsoft on Windows 11", "CIF → Monte Carlo → master; compare with reference projection"],
    ["2", "Real EDAX/TSL and lab Oxford exports", "square and hexagonal grids, vendor calibration"],
    ["3", "CUDA parity on a 4 GB GPU", "scores, speed, memory, fallback"],
    ["4", "Dynamical Ni/Cu benchmark", "EMsoft masters; calibrate phase margins"],
    ["5", "Release candidate", "offline Windows installer, quick start, reports"]];
  const x0 = GX + 0.45, y0 = GY + 0.35, rh = 0.88;
  s.addShape(pres.shapes.LINE, { x: x0 + 0.3, y: y0 + 0.3, w: 0, h: (st.length - 1) * rh, line: { color: "000000", width: 1.5 } });
  st.forEach((t, i) => {
    const y = y0 + i * rh;
    s.addShape(pres.shapes.OVAL, { x: x0, y, w: 0.6, h: 0.6, fill: { color: i < 3 ? "000000" : "FFFFFF" }, line: { color: "000000", width: 1.5 } });
    s.addText(t[0], { x: x0, y, w: 0.6, h: 0.6, fontFace: "Arial", fontSize: 16, bold: true, color: i < 3 ? "FFFFFF" : "000000", align: "center", valign: "middle", margin: 0, isTextBox: true });
    s.addText([{ text: t[1], options: { bold: true, fontSize: 15, breakLine: true } }, { text: t[2], options: { fontSize: 13, color: "404040" } }],
      { x: x0 + 0.85, y: y - 0.08, w: GW - 1.6, h: 0.78, fontFace: "Arial", color: "000000", valign: "middle", margin: 0, isTextBox: true });
  });
}

(async () => {
  await pres.writeFile({ fileName: OUT });
  if (applyTheme) await applyTheme(OUT, THEME);
  console.log("wrote", OUT);
})();
