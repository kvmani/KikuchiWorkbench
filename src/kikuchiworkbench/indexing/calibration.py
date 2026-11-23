"""Shared projection-centre calibration.

A small set of well-spread, high-signal points is indexed with one reference
phase, then orientation and PC are refined jointly (kikuchipy). The median PC
is applied to the scan and used for **all** competing phases, so phase scores
are compared under the same calibrated geometry. The per-point spread is
recorded as a diagnostic of PC variation across the scan.
"""

from __future__ import annotations

import contextlib
import io
import warnings
from dataclasses import replace

import numpy as np

from .preprocessing import signal_metric


def choose_calibration_points(scan, preprocessor, n_points: int = 16, seed: int = 0) -> np.ndarray:
    """Pick up to ``n_points`` high-signal points spread over the map (one per grid cell)."""
    n = scan.n_points
    rr, cc = scan.map_indices()
    k = int(np.ceil(np.sqrt(n_points)))
    cell = (np.minimum(rr * k // max(1, scan.grid.nrows), k - 1) * k
            + np.minimum(cc * k // max(1, scan.grid.ncols), k - 1))
    chosen = []
    for c in np.unique(cell):
        idx = np.nonzero((cell == c) & scan.valid)[0]
        if idx.size == 0:
            continue
        sample = idx if idx.size <= 64 else np.random.default_rng(seed + int(c)).choice(idx, 64, replace=False)
        pats = np.concatenate([scan.get_patterns(int(i), int(i) + 1) for i in sample])
        sig = signal_metric(preprocessor.apply_experimental(pats), preprocessor.mask())
        chosen.append(int(sample[int(np.argmax(sig))]))
    return np.array(sorted(chosen)[:n_points], dtype=np.int64)


def calibrate_pc(scan, master, preprocessor, n_points: int = 16, resolution_deg: float = 4.0,
                 pc_trust: float = 0.05, angle_trust_deg: float | None = None, maxeval: int = 1500,
                 seed: int = 0, iterations: int = 3) -> dict:
    """Return {'pc_bruker', 'pc_spread', 'points', 'per_point_pc', 'scores', 'detector', ...}."""
    import kikuchipy as kp
    from kikuchipy.detectors import EBSDDetector
    from orix.crystal_map import CrystalMap, PhaseList
    from orix.quaternion import Rotation

    from ..pipeline import IndexingConfig, PhaseSpec, run_indexing, subset_scan

    pts = choose_calibration_points(scan, preprocessor, n_points, seed)
    sub = subset_scan(scan, pts)
    cfg = IndexingConfig(scan={"path": "<calibration>"}, phases=[PhaseSpec(master=master.info.path)],
                         sampling={"resolution_deg": resolution_deg}, preprocessing=list(preprocessor.steps),
                         matching={"backend": "cpu"}, allow_placeholder_geometry=True)
    r = run_indexing(cfg, scan=sub, masters=[master], export=False)
    pre = r.context["preprocessor"]
    det0 = r.context["detector"]
    pats = pre.apply_experimental(sub.get_patterns(0, sub.n_points))
    sig = kp.signals.EBSD(np.ascontiguousarray(pats, dtype=np.float32))
    xm = CrystalMap(rotations=Rotation(r.best_quaternion[0]), phase_list=PhaseList(master.phase.deepcopy()),
                    x=np.arange(pts.size, dtype=float))
    at = float(angle_trust_deg if angle_trust_deg is not None else resolution_deg + 1)
    det_b = pre.adapt_detector(det0)
    history = [[float(v) for v in np.asarray(det_b.pc_average).ravel()]]
    for _ in range(iterations):
        with warnings.catch_warnings(), contextlib.redirect_stdout(io.StringIO()):
            warnings.simplefilter("ignore")
            # stage 1: orientation only (removes the grid error before touching the PC)
            xm = sig.refine_orientation(
                xm, det_b, master.signal, energy=master.energy_keV or 20, signal_mask=~pre.mask(),
                method="minimize", method_kwargs={"method": "Nelder-Mead"}, trust_region=[at, at, at],
                rtol=1e-5, maxeval=maxeval)
            # stage 2: joint orientation + PC
            xr, dr = sig.refine_orientation_projection_center(
                xm, det_b, master.signal, energy=master.energy_keV or 20,
                signal_mask=~pre.mask(), method="minimize", method_kwargs={"method": "Nelder-Mead"},
                trust_region=[2.0, 2.0, 2.0, pc_trust, pc_trust, pc_trust], rtol=1e-5, maxeval=maxeval)
        per = np.asarray(dr.pc, dtype=float).reshape(-1, 3)
        scores = np.asarray(xr.prop["scores"], dtype=float)
        good = scores >= np.median(scores) - 0.1
        pc = np.median(per[good], axis=0)
        history.append([float(v) for v in pc])
        det_b = EBSDDetector(shape=det_b.shape, pc=pc, binning=det_b.binning, px_size=det_b.px_size,
                             tilt=det_b.tilt, azimuthal=det_b.azimuthal, twist=det_b.twist,
                             sample_tilt=det_b.sample_tilt)
        xm = xr
        at = 2.0
    d = scan.detector
    new_det = EBSDDetector(shape=d.shape, pc=pc, binning=d.binning, px_size=d.px_size, tilt=d.tilt,
                           azimuthal=d.azimuthal, twist=d.twist, sample_tilt=d.sample_tilt)
    return {
        "reference_phase": master.info.phase_name,
        "points": pts.tolist(),
        "pc_bruker_start": [float(v) for v in np.asarray(det0.pc_average).ravel()],
        "pc_bruker": [float(v) for v in pc],
        "pc_spread_std": [float(v) for v in per[good].std(axis=0)],
        "per_point_pc": per.tolist(),
        "scores": scores.tolist(),
        "n_used": int(good.sum()),
        "pc_history": history,
        "detector": new_det,
        "settings": {"resolution_deg": resolution_deg, "pc_trust": pc_trust, "angle_trust_deg": at,
                     "maxeval": maxeval, "iterations": iterations, "method": "Nelder-Mead (kikuchipy joint orientation+PC)"},
    }


def apply_calibration(scan, cal: dict):
    s = replace(scan, detector=cal["detector"], geometry_source="calibrated")
    s.metadata = {**scan.metadata, "pc_calibration": {k: v for k, v in cal.items() if k != "detector"}}
    return s
