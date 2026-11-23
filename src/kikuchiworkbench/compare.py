"""Compare workbench results with vendor orientations and phases (e.g. AZtec / OIM indexing).

Vendor exports may express orientations in a sample frame rotated with respect to the workbench frame
(kikuchipy/EDAX convention, see docs/conventions.md). ``frame='auto'`` tests a small set of candidate
sample-frame rotations and picks the one with the lowest median disorientation; the chosen rotation is always
reported, because a wrong frame silently inflates disorientations. Vendor results are comparisons, not ground
truth.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np

# Candidate sample-frame rotations (Bunge Euler, degrees) between vendor and workbench frames.
FRAME_CANDIDATES = {
    "identity": (0, 0, 0),
    "Rz90": (90, 0, 0),
    "Rz180": (180, 0, 0),
    "Rz270": (270, 0, 0),
    "Rx180": (0, 180, 0),
    "Rx180·Rz90": (90, 180, 0),
}


def _disorientation(q_a: np.ndarray, q_b: np.ndarray, point_group) -> np.ndarray:
    from orix.quaternion import Orientation

    return np.asarray(Orientation(q_a, symmetry=point_group).angle_with(
        Orientation(q_b, symmetry=point_group), degrees=True))


def _apply_frame(q_vendor: np.ndarray, euler_deg) -> np.ndarray:
    from orix.quaternion import Rotation

    s = Rotation.from_euler(np.deg2rad(np.asarray(euler_deg, dtype=float))[None])
    return (Rotation(q_vendor) * s).data


def compare_orientations(q_ours: np.ndarray, q_vendor: np.ndarray, point_group, frame: str = "auto",
                         sample: int = 500, seed: int = 0) -> dict:
    """Per-point disorientation (deg) after the chosen frame correction, plus the frame decision."""
    ok = np.all(np.isfinite(q_ours), axis=1) & np.all(np.isfinite(q_vendor), axis=1)
    idx = np.nonzero(ok)[0]
    tried = {}
    if frame == "auto":
        sub = idx if idx.size <= sample else np.random.default_rng(seed).choice(idx, sample, replace=False)
        for name, eul in FRAME_CANDIDATES.items():
            d = _disorientation(q_ours[sub], _apply_frame(q_vendor[sub], eul), point_group)
            tried[name] = float(np.median(d)) if d.size else float("nan")
        frame = min(tried, key=lambda k: tried[k])
    if frame not in FRAME_CANDIDATES:
        raise ValueError(f"Unknown frame {frame!r}; options: auto, {', '.join(FRAME_CANDIDATES)}")
    dis = np.full(len(q_ours), np.nan)
    if idx.size:
        dis[idx] = _disorientation(q_ours[idx], _apply_frame(q_vendor[idx], FRAME_CANDIDATES[frame]), point_group)
    return {"frame": frame, "frame_euler_deg": list(FRAME_CANDIDATES[frame]), "frame_medians_tried": tried,
            "disorientation_deg": dis}


def compare_result(result, vendor_euler_deg: np.ndarray, vendor_phase: np.ndarray | None = None,
                   vendor_phase_names: dict | None = None, frame: str = "auto") -> dict:
    """Compare an IndexingResult (points in result order) with vendor Euler angles (deg) and phase ids."""
    from orix.quaternion import Rotation

    d = result.decision
    q_vendor = Rotation.from_euler(np.deg2rad(np.asarray(vendor_euler_deg, dtype=float))).data
    p_any = np.asarray(d.best_phase_any)
    q_ours = np.stack([result.best_quaternion[int(p)][i] for i, p in enumerate(p_any)])
    pg = result.phases[0].point_group
    same_laue = all(ph.point_group.laue.name == pg.laue.name for ph in result.phases)
    if not same_laue:
        # disorientation needs one symmetry; use each point's own phase symmetry
        dis = np.full(len(p_any), np.nan)
        info = None
        for p, ph in enumerate(result.phases):
            sel = p_any == p
            if sel.any():
                info = compare_orientations(q_ours[sel], q_vendor[sel], ph.point_group, frame)
                dis[sel] = info["disorientation_deg"]
                frame = info["frame"]  # reuse the frame chosen on the first phase
        cmp = {**info, "disorientation_deg": dis}
    else:
        cmp = compare_orientations(q_ours, q_vendor, pg, frame)
    dis = cmp["disorientation_deg"]
    indexed = d.label == 0
    out = {
        "frame": cmp["frame"], "frame_euler_deg": cmp["frame_euler_deg"],
        "frame_medians_tried": cmp["frame_medians_tried"],
        "n": int(len(dis)),
        "median_disorientation_deg": float(np.nanmedian(dis[indexed])) if indexed.any() else None,
        "p90_disorientation_deg": float(np.nanpercentile(dis[indexed], 90)) if indexed.any() else None,
        "fraction_within_2deg": float(np.mean(dis[indexed] <= 2.0)) if indexed.any() else None,
        "fraction_within_5deg": float(np.mean(dis[indexed] <= 5.0)) if indexed.any() else None,
        "disorientation_deg": dis,
    }
    if vendor_phase is not None:
        names = {int(k): v for k, v in (vendor_phase_names or {}).items()}  # JSON/YAML keys may be strings
        vp = np.asarray(vendor_phase).astype(int)
        labels_ours = np.array([result.phase_names[int(p)] if lab == 0 else
                                {1: "ambiguous", 2: "unindexed", 3: "low_signal", 4: "missing"}.get(int(lab), "?")
                                for p, lab in zip(d.phase, d.label, strict=True)])
        table: dict = {}
        for v, o in zip(vp, labels_ours, strict=True):
            key = names.get(int(v), f"vendor phase {int(v)}")
            table.setdefault(key, {}).setdefault(str(o), 0)
            table[key][str(o)] += 1
        out["phase_table_vendor_rows_ours_cols"] = table
        if names:
            agree = [names.get(int(v)) == o for v, o in zip(vp, labels_ours, strict=True)]
            out["phase_agreement_fraction"] = float(np.mean(agree))
    return out


def export_comparison(cmp: dict, result, scan, out_dir: str | os.PathLike) -> dict:
    """Write comparison.json and a disorientation map PNG into a job output folder (not Git)."""
    from .export import _save_map

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    data = {k: v for k, v in cmp.items() if k != "disorientation_deg"}
    (out / "comparison.json").write_text(json.dumps(data, indent=2, default=str))
    files = {"comparison_json": str(out / "comparison.json")}
    img = scan.to_map(np.clip(cmp["disorientation_deg"], 0, 10))
    files["disorientation_map"] = str(_save_map(out / "vendor_disorientation_map.png", img,
                                                f"Disorientation to vendor (frame {cmp['frame']})",
                                                cmap="magma_r", vmin=0, vmax=10, colorbar="degrees (clipped at 10)"))
    return files
