"""Run reports: Markdown + self-contained HTML written into a job's output folder.

The report is built only from files the run wrote (manifest.json, results.csv, map PNGs), so it can be
regenerated at any time with ``kwb report JOB_DIR``. Reports and their images stay in the job folder; they are
never meant to be committed to Git.
"""

from __future__ import annotations

import base64
import csv
import html
import json
import os
from collections import Counter
from pathlib import Path

MAPS = [("phase_map.png", "Phase"), ("ipf_z_map.png", "Orientation (IPF-Z)"), ("score_map.png", "Best NCC"),
        ("margin_map.png", "Phase margin"), ("signal_map.png", "Signal"),
        ("vendor_disorientation_map.png", "Disorientation to vendor")]


def _outputs_dir(path: str | os.PathLike) -> Path:
    p = Path(path)
    if (p / "outputs" / "manifest.json").exists():
        return p / "outputs"
    if (p / "manifest.json").exists():
        return p
    raise FileNotFoundError(f"No manifest.json in {p} or {p / 'outputs'}")


def _fmt_s(v) -> str:
    try:
        return f"{float(v):.1f} s"
    except (TypeError, ValueError):
        return str(v)


def _num(v) -> str:
    try:
        return f"{float(v):.4g}"
    except (TypeError, ValueError):
        return str(v)


def collect(path: str | os.PathLike) -> dict:
    out = _outputs_dir(path)
    man = json.loads((out / "manifest.json").read_text())
    rows = []
    if (out / "results.csv").exists():
        with open(out / "results.csv", newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
    labels = Counter(r["label"] for r in rows)
    phases = Counter(r["phase_name"] for r in rows if r["label"] == "indexed")
    n_idx = sum(phases.values())
    scores = sorted(float(r["best_score"]) for r in rows) if rows else []
    job_dir = out.parent if out.name == "outputs" else out
    status = {}
    if (job_dir / "status.json").exists():
        status = json.loads((job_dir / "status.json").read_text())
    return {
        "out": out, "job_dir": job_dir, "manifest": man, "status": status, "n": len(rows),
        "labels": dict(labels), "phase_fraction": {k: v / n_idx for k, v in phases.items()} if n_idx else {},
        "median_score": scores[len(scores) // 2] if scores else None,
        "maps": [(f, t) for f, t in MAPS if (out / f).exists()],
        "valid": (job_dir / "COMPLETE").exists() and not (job_dir / "INVALID").exists(),
    }


def _sections(d: dict) -> list[tuple[str, list[str]]]:
    m = d["manifest"]
    p = m.get("parameters", {})
    cfg = p.get("config", {})
    scan = m.get("inputs", {}).get("scan", {})
    ss = scan.get("summary", {})
    secs: list[tuple[str, list[str]]] = []
    secs.append(("Run", [
        f"Run id `{m.get('run_id')}`, created {m.get('created_utc')}, status **{m.get('status')}**"
        + ("" if d["valid"] else " — **job folder is not marked COMPLETE; do not use these results**"),
        f"Job folder: `{d['job_dir']}`",
        f"Workbench {m.get('workbench_version')}, manifest schema {m.get('schema_version')}",
    ]))
    g = ss.get("grid", {})
    lines = [f"Scan: `{scan.get('path', ss.get('source_path'))}` ({ss.get('file_format')}, {ss.get('vendor')})",
             f"Grid: {g.get('grid_type')} {g.get('nrows')} × {g.get('ncols')}, step {_num(g.get('step_x'))} {g.get('unit')}; "
             f"patterns {ss.get('pattern_shape')} {ss.get('dtype')}",
             f"Geometry source: {ss.get('geometry_source')}"]
    if scan.get("sha256"):
        lines.append(f"Scan sha256: `{scan['sha256']}`")
    for k, v in m.get("inputs", {}).items():
        if k.startswith("master_"):
            lines.append(f"Phase **{v.get('phase_name')}**: `{v.get('path')}` (space group {v.get('space_group')}, "
                         f"energy {v.get('energy_mode')} {v.get('energy_keV') or ''} keV, sha256 `{str(v.get('sha256'))[:16]}…`)")
    secs.append(("Inputs", lines))
    det = p.get("detector_used", {})
    lines = [f"Preset: {cfg.get('preset') or 'none'}; ROI: {cfg.get('roi') or 'full scan'}",
             f"Sampling: {p.get('sampling', {}).get('resolution_deg')}° cubochoric; orientations "
             f"{p.get('sampling', {}).get('n_orientations')}",
             f"Detector (Bruker PC): {det.get('pc')}, shape {det.get('shape')}, binning {det.get('binning')}, "
             f"tilt {det.get('tilt')}°, sample tilt {det.get('sample_tilt')}°",
             f"Preprocessing: {[s.get('op') for s in p.get('preprocessing', {}).get('steps', [])]}",
             f"Matching: backend {p.get('matching', {}).get('backend_used')}, top-k {p.get('matching', {}).get('top_k')}",
             f"Thresholds: {m.get('thresholds')}"]
    if "refinement" in p:
        lines.append(f"Refinement (equal budget): {p['refinement'].get('budget')}")
    if "pc_calibration" in p:
        c = p["pc_calibration"]
        lines.append(f"PC calibration on {c.get('n_used')} points with {c.get('reference_phase')}: "
                     f"{c.get('pc_bruker')} (start {c.get('pc_bruker_start')}, spread {c.get('pc_spread_std')})")
    secs.append(("Settings", lines))
    lab = d["labels"]
    lines = [f"Points: {d['n']} — " + ", ".join(f"{k} {v}" for k, v in sorted(lab.items())),
             "Phase fractions of indexed points: " + (", ".join(f"{k} {v:.3f}" for k, v in d["phase_fraction"].items())
                                                       or "–"),
             f"Median best NCC: {d['median_score']:.3f}" if d["median_score"] is not None else "Median best NCC: –",
             "Timings: " + ", ".join(f"{k[:-2]} {_fmt_s(v)}" for k, v in m.get("results", {}).get("timings", {}).items()
                                     if k.endswith("_s") and not k.endswith("per_s")),
             "Phase margins are ranking diagnostics, not probabilities."]
    secs.append(("Results", lines))
    vc = m.get("results", {}).get("vendor_comparison")
    if vc:
        lines = [f"Frame correction applied: {vc.get('frame')} {vc.get('frame_euler_deg')} (medians tried: "
                 f"{ {k: round(v, 2) for k, v in (vc.get('frame_medians_tried') or {}).items()} })",
                 f"Disorientation to vendor (indexed points): median {vc.get('median_disorientation_deg')}°, "
                 f"90th percentile {vc.get('p90_disorientation_deg')}°, within 2° {vc.get('fraction_within_2deg')}, "
                 f"within 5° {vc.get('fraction_within_5deg')}"]
        if vc.get("phase_table_vendor_rows_ours_cols"):
            lines.append(f"Phase table (vendor rows → workbench columns): {vc['phase_table_vendor_rows_ours_cols']}")
        if vc.get("phase_agreement_fraction") is not None:
            lines.append(f"Phase agreement: {vc['phase_agreement_fraction']:.3f}")
        lines.append("Vendor results are a comparison, not ground truth.")
        secs.append(("Comparison with vendor indexing", lines))
    ev = [f"[{e['kind']}] {e['message']}" for e in m.get("events", [])]
    secs.append(("Events and warnings", ev or ["none"]))
    sw = m.get("software", {})
    hw = m.get("hardware", {})
    secs.append(("Provenance", [", ".join(f"{k} {v}" for k, v in sw.items() if v),
                                f"{hw.get('platform')}, {hw.get('cpu_count')} CPUs, BLAS {hw.get('blas')}"]))
    return secs


def write_report(path: str | os.PathLike) -> dict[str, str]:
    d = collect(path)
    out = d["out"]
    title = f"KikuchiWorkbench run report — {d['manifest'].get('run_id')}"
    secs = _sections(d)
    md = [f"# {title}", ""]
    for name, lines in secs:
        md += [f"## {name}", ""] + [f"- {ln}" for ln in lines] + [""]
    if d["maps"]:
        md += ["## Maps", ""] + [f"![{t}]({f})" for f, t in d["maps"]] + [""]
    (out / "report.md").write_text("\n".join(md), encoding="utf-8")

    def inline(s: str) -> str:
        s = html.escape(s)
        out_s, code, bold = "", False, False
        i = 0
        while i < len(s):
            if s.startswith("**", i):
                out_s += "</b>" if bold else "<b>"
                bold = not bold
                i += 2
                continue
            if s[i] == "`":
                out_s += "</code>" if code else "<code>"
                code = not code
                i += 1
                continue
            out_s += s[i]
            i += 1
        return out_s

    parts = [f"<!doctype html><html><head><meta charset='utf-8'><title>{html.escape(title)}</title>",
             "<style>body{font-family:Arial,sans-serif;max-width:1100px;margin:24px auto;padding:0 16px;color:#111}"
             "h1{font-size:22px;border-bottom:2px solid #000;padding-bottom:6px}h2{font-size:17px;margin-top:22px}"
             "li{margin:3px 0}code{background:#f2f2f2;padding:1px 3px}.maps{display:flex;flex-wrap:wrap;gap:12px}"
             "figure{margin:0;border:1px solid #000;padding:6px}figcaption{font-size:12px;text-align:center}"
             "img{max-width:480px}</style></head><body>", f"<h1>{html.escape(title)}</h1>"]
    for name, lines in secs:
        parts.append(f"<h2>{html.escape(name)}</h2><ul>" + "".join(f"<li>{inline(ln)}</li>" for ln in lines) + "</ul>")
    if d["maps"]:
        parts.append("<h2>Maps</h2><div class='maps'>")
        for f, t in d["maps"]:
            b64 = base64.b64encode((out / f).read_bytes()).decode()
            parts.append(f"<figure><img alt='{html.escape(t)}' src='data:image/png;base64,{b64}'>"
                         f"<figcaption>{html.escape(t)}</figcaption></figure>")
        parts.append("</div>")
    parts.append("</body></html>")
    (out / "report.html").write_text("".join(parts), encoding="utf-8")
    return {"markdown": str(out / "report.md"), "html": str(out / "report.html")}
