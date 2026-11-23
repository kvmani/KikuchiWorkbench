"""Exports: PNG maps, CSV table, HDF5 results and the run manifest."""

from __future__ import annotations

import csv
import os
from pathlib import Path

import h5py
import numpy as np

from .indexing.decision import (
    LABEL_AMBIGUOUS,
    LABEL_INDEXED,
    LABEL_LOW_SIGNAL,
    LABEL_MISSING,
    LABEL_NAMES,
    LABEL_UNINDEXED,
)

PHASE_COLORS = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd", "#8c564b"]
LABEL_COLORS = {
    LABEL_AMBIGUOUS: "#bdbdbd",
    LABEL_UNINDEXED: "#000000",
    LABEL_LOW_SIGNAL: "#6a3d9a",
    LABEL_MISSING: "#ffffff",
}


def _hex_to_rgb(h: str) -> np.ndarray:
    h = h.lstrip("#")
    return np.array([int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)])


def phase_rgb(result) -> np.ndarray:
    n = result.n_points
    rgb = np.zeros((n, 3))
    lab = result.decision.label
    for k, col in LABEL_COLORS.items():
        rgb[lab == k] = _hex_to_rgb(col)
    for p in range(len(result.phase_names)):
        rgb[(lab == LABEL_INDEXED) & (result.decision.phase == p)] = _hex_to_rgb(PHASE_COLORS[p % 6])
    return rgb


def ipf_rgb(result, direction=(0, 0, 1)) -> np.ndarray:
    """IPF colours of the best orientation of the best phase (all labels shown dimmed if not indexed)."""
    from orix.plot import IPFColorKeyTSL
    from orix.quaternion import Orientation
    from orix.vector import Vector3d

    n = result.n_points
    rgb = np.zeros((n, 3))
    best_any = result.decision.best_phase_any
    for p, ph in enumerate(result.phases):
        sel = best_any == p
        if not sel.any():
            continue
        q = result.best_quaternion[p][sel]
        o = Orientation(q, symmetry=ph.point_group)
        key = IPFColorKeyTSL(ph.point_group, direction=Vector3d(direction))
        rgb[sel] = key.orientation2color(o)
    not_ok = result.decision.label != LABEL_INDEXED
    rgb[not_ok] *= 0.35
    rgb[result.decision.label == LABEL_MISSING] = 1.0
    return rgb


def _save_map(path: Path, img: np.ndarray, title: str, cmap=None, vmin=None, vmax=None,
              legend: list[tuple[str, str]] | None = None, colorbar: str | None = None) -> Path:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch

    fig, ax = plt.subplots(figsize=(6, 5), dpi=120)
    im = ax.imshow(img, cmap=cmap, vmin=vmin, vmax=vmax, interpolation="nearest")
    ax.set_title(title)
    ax.set_xlabel("column")
    ax.set_ylabel("row")
    if colorbar:
        fig.colorbar(im, ax=ax, label=colorbar)
    if legend:
        ax.legend(handles=[Patch(color=c, label=lbl) for lbl, c in legend], loc="upper left",
                  bbox_to_anchor=(1.01, 1.0), fontsize=8)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)
    return path


def export_maps(result, scan, out_dir: str | os.PathLike) -> dict[str, str]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    files: dict[str, str] = {}
    note = " (hexagonal grid on offset rows)" if scan.grid.grid_type == "hexagonal" else ""
    leg = [(n, PHASE_COLORS[i % 6]) for i, n in enumerate(result.phase_names)]
    leg += [(LABEL_NAMES[k], c) for k, c in LABEL_COLORS.items()]
    img = scan.to_map(phase_rgb(result), fill=1.0)
    files["phase_map"] = str(_save_map(out / "phase_map.png", img, "Phase" + note, legend=leg))
    img = scan.to_map(ipf_rgb(result), fill=1.0)
    files["ipf_z_map"] = str(_save_map(out / "ipf_z_map.png", img, "IPF-Z of best orientation" + note))
    files["score_map"] = str(_save_map(out / "score_map.png", scan.to_map(result.decision.best_score),
                                       "Best NCC score (orientation fit)", cmap="gray", colorbar="NCC"))
    if len(result.phases) > 1:
        files["margin_map"] = str(_save_map(out / "margin_map.png", scan.to_map(result.decision.margin),
                                            "Phase score margin (best - runner-up)", cmap="viridis",
                                            vmin=0, colorbar="NCC margin"))
    files["signal_map"] = str(_save_map(out / "signal_map.png", scan.to_map(result.signal),
                                        "Signal metric (low signal check)", cmap="magma",
                                        colorbar="smoothed/residual std"))
    return files


def export_csv(result, scan, path: str | os.PathLike) -> str:
    rr, cc = scan.map_indices()
    d = result.decision
    names = result.phase_names
    euler = result.best_euler_deg()
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        header = ["index", "row", "col", "x_um", "y_um", "label", "phase", "phase_name", "phi1_deg",
                  "Phi_deg", "phi2_deg", "best_score", "runner_up_phase", "runner_up_score",
                  "phase_margin", "phase_tie", "signal", "low_signal", "best_phase_any"]
        header += [f"score_{n}" for n in names]
        w.writerow(header)
        for i in range(result.n_points):
            p_any = int(d.best_phase_any[i])
            e = euler[p_any][i]
            row = [i, int(rr[i]), int(cc[i]), f"{scan.x[i]:.4f}", f"{scan.y[i]:.4f}",
                   LABEL_NAMES[int(d.label[i])], int(d.phase[i]),
                   names[int(d.phase[i])] if d.phase[i] >= 0 else "",
                   f"{e[0]:.4f}", f"{e[1]:.4f}", f"{e[2]:.4f}", f"{d.best_score[i]:.6f}",
                   int(d.runner_up_phase[i]),
                   "" if np.isnan(d.runner_up_score[i]) else f"{d.runner_up_score[i]:.6f}",
                   "" if np.isnan(d.margin[i]) else f"{d.margin[i]:.6f}", int(d.tie[i]),
                   f"{result.signal[i]:.4f}", int(d.low_signal[i]), names[p_any]]
            row += [f"{result.per_phase_best[i, p]:.6f}" for p in range(len(names))]
            w.writerow(row)
    return str(path)


def export_h5(result, scan, path: str | os.PathLike) -> str:
    d = result.decision
    with h5py.File(path, "w") as h:
        h.attrs["kwb_results_version"] = "1"
        h.attrs["phase_names"] = np.array(result.phase_names, dtype="S")
        g = h.create_group("decision")
        for k in ("label", "phase", "best_score", "runner_up_phase", "runner_up_score", "margin",
                  "tie", "low_signal", "best_phase_any"):
            g[k] = np.asarray(getattr(d, k))
        h["per_phase_best"] = result.per_phase_best
        if getattr(result, "dictionary_best", None) is not None:
            h["per_phase_best_dictionary"] = result.dictionary_best  # before refinement
        h["signal"] = result.signal
        h["x"], h["y"] = scan.x, scan.y
        rr, cc = scan.map_indices()
        h["row"], h["col"] = rr, cc
        for p, name in enumerate(result.phase_names):
            pg = h.create_group(f"phases/{p}")
            pg.attrs["name"] = name
            pg["topk_score"] = result.topk_scores[p]
            pg["topk_index"] = result.topk_index[p]
            pg["topk_quaternion"] = result.topk_quaternion[p]
            pg["n_dictionary"] = result.n_dictionary[p]
    return str(path)
