"""Controlled cubic phase-discrimination benchmark (synthetic, kinematical).

Protocol (scope: "Controlled cubic discrimination"):

1. Masters from CIFs: Ni (a = 3.524 Å) and Cu (a = 3.615 Å), FCC Fm-3m, plus a
   same-chemistry lattice sweep (Ni with a scaled by 1 + δ) to isolate band-width
   sensitivity. Two generation routes: *targets* are simulated from finer
   masters (smaller d_min, larger grid) than the *dictionary* masters, giving a
   realistic model mismatch. Both routes are kinematical (no EMsoft here).
2. Development and held-out scans use different seeds; all orientations are
   random (off the dictionary grid).
3. Thresholds (ambiguity margin) are selected on the development baseline and
   written to ``thresholds.json`` *before* any held-out run; held-out runs only
   read the frozen file.
4. Stress conditions: Poisson noise, PC error, binning, angular step,
   identical competing masters, mixed (overlapping) patterns, lattice sweep.

Outputs: ``report.md``, ``results.json``, ``coverage_vs_error_<cond>.csv``.
"""

from __future__ import annotations

import datetime as _dt
import json
import time
from dataclasses import replace
from pathlib import Path

import numpy as np

from .crystal.cif import make_cubic_model
from .indexing.decision import LABEL_AMBIGUOUS, LABEL_INDEXED, DecisionPolicy, decide
from .masters.importer import load_master
from .masters.kinematical import simulate_kinematical_master
from .pipeline import IndexingConfig, PhaseSpec, run_indexing
from .provenance import hardware_info, software_versions
from .synthetic import SyntheticSpec, make_synthetic_scan, misorientation_deg, random_rotations

A_NI = 3.524
A_CU = 3.615
# Reflector sets are defined by hkl families (identical for all compared phases), not by a d-spacing
# cutoff: a fixed d_min admits different families for slightly different lattice parameters.
ROUTES = {
    "dictionary": {"max_hkl_sq": 20, "half_size": 150},
    "target": {"max_hkl_sq": 40, "half_size": 200},
}
ERROR_TARGET = 0.01  # max phase error among indexed pixels on the dev set


def build_masters(out_dir: Path, deltas=(0.005, 0.01, 0.02)) -> dict:
    """Return {(label, route): path}. Labels: Ni, Cu, Ni+<δ>."""
    out_dir.mkdir(parents=True, exist_ok=True)
    specs = {"Ni": ("Ni", A_NI), "Cu": ("Cu", A_CU)}
    for d in deltas:
        specs[f"Ni+{d * 100:g}%"] = ("Ni", A_NI * (1 + d))
    paths = {}
    for label, (el, a) in specs.items():
        model = make_cubic_model(label.replace("+", "p").replace("%", "pct").replace(".", "_"), el, a)
        for route, kw in ROUTES.items():
            p = out_dir / f"{model.name}_{route}.h5"
            if not p.exists():
                simulate_kinematical_master(model, p, voltage_kV=20.0, **kw)
            paths[(label, route)] = str(p)
    return paths


def _scan(masters, n_side: int, seed: int, counts: float, layout: str = "random"):
    spec = SyntheticSpec(nrows=n_side, ncols=n_side, seed=seed, counts=counts, phase_layout=layout)
    return make_synthetic_scan(masters, spec)


def _mixed_scan(masters, n_side: int, seed: int, counts: float, w: float = 0.5):
    """Patterns that are w*phase0(orientation A) + (1-w)*phase1(orientation B)."""
    spec = SyntheticSpec(nrows=n_side, ncols=n_side, seed=seed, counts=0, background_fraction=0.0,
                         dtype="uint16")
    n = n_side * n_side
    a, _ = make_synthetic_scan([masters[0]], replace(spec, phase_layout="single"),
                               rotations=random_rotations(n, seed))
    b, _ = make_synthetic_scan([masters[1]], replace(spec, phase_layout="single"),
                               rotations=random_rotations(n, seed + 1000))
    mix = w * np.asarray(a.patterns, float) + (1 - w) * np.asarray(b.patterns, float)
    mix = mix / mix.max(axis=(1, 2), keepdims=True)
    rng = np.random.default_rng(seed + 7)
    yy, xx = np.mgrid[: mix.shape[1], : mix.shape[2]]
    bg = np.exp(-(((yy - 27) / 42) ** 2 + ((xx - 31) / 48) ** 2))
    pats = rng.poisson(counts * (mix + 0.6 * bg / bg.mean())).astype(np.uint16)
    return replace(a, patterns=pats), {"phase_id": np.full(n, -2), "quaternion": None}


def _shift_pc(scan, d):
    from kikuchipy.detectors import EBSDDetector

    det = scan.detector
    pc = np.asarray(det.pc_average, float).ravel() + np.array([d, 0.0, d])
    nd = EBSDDetector(shape=det.shape, pc=pc, binning=det.binning, px_size=det.px_size,
                      tilt=det.tilt, sample_tilt=det.sample_tilt)
    return replace(scan, detector=nd)


def evaluate(result, truth: dict, policy: DecisionPolicy | None = None) -> dict:
    d = result.decision if policy is None else decide(result.per_phase_best, policy, result.signal)
    ph = np.asarray(truth["phase_id"]).astype(int)
    n_ph = len(result.phase_names)
    n = ph.size
    cols = list(result.phase_names) + ["ambiguous", "unindexed/other"]
    if (ph < 0).all():  # mixed patterns: no single correct phase
        counts = {c: 0 for c in cols}
        for lab, p in zip(d.label, d.phase, strict=True):
            key = result.phase_names[p] if lab == LABEL_INDEXED else (
                "ambiguous" if lab == LABEL_AMBIGUOUS else "unindexed/other")
            counts[key] += 1
        return {"n": int(n), "mixed_label_counts": counts,
                "fraction_flagged": float(np.mean(d.label != LABEL_INDEXED))}
    conf = np.zeros((n_ph, n_ph + 2), dtype=int)
    for t, lab, p in zip(ph, d.label, d.phase, strict=True):
        if lab == LABEL_INDEXED:
            conf[t, p] += 1
        elif lab == LABEL_AMBIGUOUS:
            conf[t, n_ph] += 1
        else:
            conf[t, n_ph + 1] += 1
    indexed = d.label == LABEL_INDEXED
    correct = indexed & (d.phase == ph)
    mis = np.full(n, np.nan)
    q = np.asarray(truth["quaternion"])
    for p, phase in enumerate(result.phases):
        sel = correct & (ph == p)
        if sel.any():
            mis[sel] = misorientation_deg(result.best_quaternion[p][sel], q[sel], phase.point_group)
    true_margin = result.per_phase_best[np.arange(n), ph] - np.max(
        np.where(np.arange(n_ph)[None] == ph[:, None], -np.inf, result.per_phase_best), axis=1) \
        if n_ph > 1 else np.full(n, np.nan)
    return {
        "n": int(n),
        "confusion": {"rows_true": list(result.phase_names), "cols_pred": cols, "matrix": conf.tolist()},
        "recall": {result.phase_names[p]: float(conf[p, p] / max(1, (ph == p).sum())) for p in range(n_ph)},
        "coverage": float(indexed.mean()),
        "error_among_indexed": float((indexed & ~correct).sum() / max(1, indexed.sum())),
        "ambiguous_fraction": float(np.mean(d.label == LABEL_AMBIGUOUS)),
        "unindexed_fraction": float(np.mean((d.label != LABEL_INDEXED) & (d.label != LABEL_AMBIGUOUS))),
        "misorientation_deg": {"median": _nanstat(np.nanmedian, mis), "p95": _nanstat(lambda a: np.nanpercentile(a, 95), mis)},
        "signed_true_phase_margin": {"median": _nanstat(np.nanmedian, true_margin),
                                     "p05": _nanstat(lambda a: np.nanpercentile(a, 5), true_margin),
                                     "fraction_negative": float(np.mean(true_margin < 0)) if n_ph > 1 else None},
        "median_best_ncc": float(np.median(d.best_score)),
    }


def _nanstat(fn, a):
    a = np.asarray(a, float)
    return float(fn(a)) if np.isfinite(a).any() else None


def coverage_vs_error(result, truth, margins) -> list[dict]:
    rows = []
    for m in margins:
        e = evaluate(result, truth, DecisionPolicy(min_score=0.10, ambiguity_margin=float(m)))
        rows.append({"ambiguity_margin": float(m), "coverage": e["coverage"],
                     "n_indexed": int(round(e["coverage"] * e["n"])),
                     "error_among_indexed": e["error_among_indexed"]})
    return rows


def select_threshold(rows: list[dict], error_target: float = ERROR_TARGET, min_indexed: int = 10) -> dict:
    """Smallest ambiguity margin whose dev error <= target with at least ``min_indexed`` indexed points.

    If no margin qualifies, the largest margin is frozen (conservative: most pixels ambiguous) and the
    selection is flagged ``met_target: False``.
    """
    ok = [r for r in rows if r["error_among_indexed"] <= error_target and r["n_indexed"] >= min_indexed]
    if not ok:
        best = max(rows, key=lambda r: r["ambiguity_margin"])
        return {**best, "met_target": False, "min_indexed": min_indexed}
    best = min(ok, key=lambda r: r["ambiguity_margin"])
    return {**best, "met_target": True, "min_indexed": min_indexed}


def conditions(mode: str) -> list[dict]:
    base = {"counts": 400.0, "pc_error": 0.0, "bin": 1, "res": 4.0, "route": "target", "dict_route": "dictionary",
            "phases": ["Ni", "Cu"], "kind": "two_phase"}
    c = [
        {**base, "name": "baseline"},
        {**base, "name": "pc_error_0.01", "pc_error": 0.01},
        {**base, "name": "identical_masters", "phases": ["Ni", "Ni"]},
        {**base, "name": "mixed_50_50", "kind": "mixed"},
        {**base, "name": "lattice_sweep_1%", "phases": ["Ni", "Ni+1%"]},
    ]
    if mode == "full":
        c += [
            {**base, "name": "matched_route", "route": "dictionary"},
            {**base, "name": "matched_fine_route", "route": "target", "dict_route": "target"},
            {**base, "name": "counts_50", "counts": 50.0},
            {**base, "name": "counts_2000", "counts": 2000.0},
            {**base, "name": "pc_error_0.005", "pc_error": 0.005},
            {**base, "name": "pc_error_0.02", "pc_error": 0.02},
            {**base, "name": "binning_2", "bin": 2},
            {**base, "name": "step_3deg", "res": 3.0},
            {**base, "name": "step_6deg", "res": 6.0},
            {**base, "name": "lattice_sweep_0.5%", "phases": ["Ni", "Ni+0.5%"]},
            {**base, "name": "lattice_sweep_2%", "phases": ["Ni", "Ni+2%"]},
        ]
        m = {"route": "dictionary", "dict_route": "dictionary"}
        c += [
            {**base, **m, "name": "matched_sweep_0.5%", "phases": ["Ni", "Ni+0.5%"]},
            {**base, **m, "name": "matched_sweep_1%", "phases": ["Ni", "Ni+1%"]},
            {**base, **m, "name": "matched_sweep_2%", "phases": ["Ni", "Ni+2%"]},
            {**base, **m, "name": "matched_pc_error_0.005", "pc_error": 0.005},
            {**base, **m, "name": "matched_pc_error_0.01", "pc_error": 0.01},
            {**base, **m, "name": "matched_pc_error_0.02", "pc_error": 0.02},
            {**base, **m, "name": "matched_counts_50", "counts": 50.0},
            {**base, **m, "name": "matched_binning_2", "bin": 2},
        ]
    return c


def _run(cond, paths, cache_dir, n_side, seed, thresholds, refine=False):
    names = cond["phases"]
    dict_names = names if len(set(names)) == len(names) else [names[0], names[0] + "_copy"]
    dict_masters = [load_master(paths[(nm, cond.get("dict_route", "dictionary"))], phase_name=dn)
                    for nm, dn in zip(names, dict_names, strict=True)]
    tgt = [load_master(paths[(nm, cond["route"])], phase_name=nm) for nm in dict.fromkeys(names)]
    if cond["kind"] == "mixed":
        scan, truth = _mixed_scan(tgt, n_side, seed, cond["counts"])
    else:
        scan, truth = _scan(tgt, n_side, seed, cond["counts"],
                            layout="single" if len(tgt) == 1 else "random")
    if cond["pc_error"]:
        scan = _shift_pc(scan, cond["pc_error"])
    pre = [{"op": "static_background", "mode": "subtract", "source": "scan_mean"},
           {"op": "dynamic_background", "sigma_frac": 0.125, "mode": "subtract"}]
    if cond["bin"] > 1:
        pre.append({"op": "bin", "factor": cond["bin"]})
    cfg = IndexingConfig(
        scan={"path": "<synthetic>"}, phases=[PhaseSpec(master=m.info.path, name=m.info.phase_name)
                                              for m in dict_masters],
        sampling={"resolution_deg": cond["res"]}, preprocessing=pre,
        matching={"backend": "cpu", "cache_dictionary": True, "cache_dir": str(cache_dir),
                  "top_k": 3},
        decision=thresholds,
        refinement={"enabled": True, "maxeval": 300} if refine else {},
    )
    t0 = time.perf_counter()
    r = run_indexing(cfg, scan=scan, masters=dict_masters, export=False)
    return r, truth, time.perf_counter() - t0


def run_benchmark(out_dir: str | Path, mode: str = "quick", n_side: int | None = None,
                  cache_dir: str | Path | None = None, log=print, refine: bool = False) -> dict:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    n_side = n_side or (8 if mode == "quick" else 14)
    cache = Path(cache_dir) if cache_dir else out / "cache"
    seeds = {"dev": 1001, "heldout": 2002}
    log(f"[benchmark] building masters in {cache / 'masters'}")
    deltas = (0.01,) if mode == "quick" else (0.005, 0.01, 0.02)
    paths = build_masters(cache / "masters", deltas)
    conds = conditions(mode)

    # ---- 1) threshold selection on the development baseline
    log("[benchmark] development run (threshold selection)")
    provisional = {"min_score": 0.10, "ambiguity_margin": 0.0, "provenance": "dev selection run"}
    r_dev, t_dev, _ = _run(conds[0], paths, cache, n_side, seeds["dev"], provisional, refine)
    margins = np.round(np.arange(0.0, 0.0501, 0.001), 4)
    rows = coverage_vs_error(r_dev, t_dev, margins)
    sel = select_threshold(rows)
    frozen = {"min_score": 0.10, "ambiguity_margin": sel["ambiguity_margin"],
              "provenance": f"selected on dev baseline (seed {seeds['dev']}, n={n_side**2}); target error "
                            f"<= {ERROR_TARGET}; frozen {_dt.datetime.now(_dt.timezone.utc).isoformat(timespec='seconds')}"}
    tfile = out / "thresholds.json"
    tfile.write_text(json.dumps({"thresholds": frozen, "selection": sel, "dev_curve": rows}, indent=2))
    frozen["met_error_target_on_dev"] = sel["met_target"]
    log(f"[benchmark] frozen thresholds: {frozen['ambiguity_margin']} (met target: {sel['met_target']})")

    # ---- 2) held-out runs with frozen thresholds (read back from file)
    frozen_read = json.loads(tfile.read_text())["thresholds"]
    results = {}
    for cond in conds:
        log(f"[benchmark] held-out: {cond['name']}")
        r, truth, dt = _run(cond, paths, cache, n_side, seeds["heldout"], frozen_read, refine)
        ev = evaluate(r, truth)
        ev["wall_time_s"] = round(dt, 2)
        ev["n_dictionary"] = r.n_dictionary
        ev["condition"] = cond
        results[cond["name"]] = ev
        if cond["kind"] != "mixed" and len(set(cond["phases"])) > 1:
            cv = coverage_vs_error(r, truth, margins)
            with open(out / f"coverage_vs_error_{cond['name']}.csv", "w") as f:
                f.write("ambiguity_margin,coverage,error_among_indexed\n")
                for row in cv:
                    f.write(f"{row['ambiguity_margin']},{row['coverage']:.4f},{row['error_among_indexed']:.4f}\n")

    summary = {
        "mode": mode, "refinement": "equal-budget Nelder-Mead, trust region = grid step, maxeval 300"
        if refine else "none (dictionary grid only)", "n_points_per_scan": n_side**2, "seeds": seeds, "thresholds": frozen_read,
        "routes": ROUTES, "lattice_A": {"Ni": A_NI, "Cu": A_CU},
        "software": software_versions(), "hardware": hardware_info(),
        "masters": "kinematical (kikuchipy simulator); NOT dynamical EMsoft",
        "results": results,
    }
    (out / "results.json").write_text(json.dumps(summary, indent=2, default=str))
    (out / "report.md").write_text(render_report(summary))
    log(f"[benchmark] report: {out / 'report.md'}")
    return summary


def render_report(s: dict) -> str:
    lines = [
        "# Controlled cubic discrimination benchmark (synthetic, kinematical)",
        "",
        f"Mode `{s['mode']}`, refinement: {s['refinement']}, {s['n_points_per_scan']} points per scan, seeds {s['seeds']}. "
        f"Masters: {s['masters']}. Dictionary route {s['routes']['dictionary']}, target route "
        f"{s['routes']['target']} (model mismatch).",
        "",
        f"Frozen thresholds (from dev set): `{json.dumps(s['thresholds'])}`",
        "",
        "Phase margins are ranking diagnostics, not probabilities.",
        "",
        "| Condition | Phases | Coverage | Error among indexed | Ambiguous | Unindexed | Recall | Median misori. (°) "
        "| Median true margin | Margin < 0 | Time (s) |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for name, e in s["results"].items():
        c = e["condition"]
        if "mixed_label_counts" in e:
            lines.append(f"| {name} | {' vs '.join(c['phases'])} (50/50 overlap) | – | – | – | – | "
                         f"labels {e['mixed_label_counts']} | – | – | – | {e['wall_time_s']} |")
            continue
        rec = ", ".join(f"{k} {v:.2f}" for k, v in e["recall"].items())
        m = e["signed_true_phase_margin"]
        lines.append(
            f"| {name} | {' vs '.join(c['phases'])} | {e['coverage']:.2f} | {e['error_among_indexed']:.3f} | "
            f"{e['ambiguous_fraction']:.2f} | {e['unindexed_fraction']:.2f} | {rec} | "
            f"{_fmt(e['misorientation_deg']['median'])} | {_fmt(m['median'], 4)} | "
            f"{_fmt(m['fraction_negative'])} | {e['wall_time_s']} |")
    lines += ["", "Confusion matrices (rows = true phase; columns = predicted, ambiguous, unindexed/other):", ""]
    for name, e in s["results"].items():
        if "confusion" in e:
            lines.append(f"- **{name}**: {e['confusion']['cols_pred']} → {e['confusion']['matrix']}")
    lines += ["", "Route note: `matched_*` conditions index targets with masters from the same "
              "generation route; all other conditions use the mismatched route (targets finer than dictionary).",
              "", "Limitations: kinematical masters only; single detector geometry; random orientations; "
              "synthetic noise model (Poisson + smooth background). Not evidence for real-data discrimination."]
    return "\n".join(lines) + "\n"


def _fmt(v, nd=2):
    return "–" if v is None else f"{v:.{nd}f}"
