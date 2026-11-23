"""Local orientation refinement with an identical search budget for every phase.

Each phase's best dictionary orientation(s) are refined against the same
preprocessed experimental patterns with kikuchipy's NCC refinement (fixed PC).
The budget (method, trust region, tolerance, maximum evaluations, number of
starting candidates) is the same for all phases so that refined scores remain
comparable for the phase decision.
"""

from __future__ import annotations

import time
import warnings
from dataclasses import asdict, dataclass, field

import numpy as np


@dataclass
class RefinementBudget:
    method: str = "minimize"
    method_kwargs: dict = field(default_factory=lambda: {"method": "Nelder-Mead"})
    trust_region_deg: float | None = None  # +/- per Euler angle; default = sampling resolution
    rtol: float = 1e-4
    maxeval: int = 300
    n_starts: int = 1  # number of top dictionary candidates refined per phase

    def to_dict(self) -> dict:
        return asdict(self)


def refine_phase(patterns: np.ndarray, detector, loaded_master, start_quaternions: np.ndarray,
                 mask: np.ndarray, budget: RefinementBudget, trust_region_deg: float,
                 energy_keV: float | None) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Refine (n, 4) start orientations. Returns (quaternions, ncc, n_evals)."""
    import kikuchipy as kp
    from orix.crystal_map import CrystalMap, PhaseList
    from orix.quaternion import Rotation

    n = patterns.shape[0]
    q0 = np.asarray(start_quaternions, dtype=float)
    valid = np.all(np.isfinite(q0), axis=1)
    out_q = np.full((n, 4), np.nan)
    out_s = np.full(n, -np.inf, dtype=np.float32)
    out_e = np.zeros(n, dtype=np.int32)
    if not valid.any():
        return out_q, out_s, out_e
    idx = np.nonzero(valid)[0]
    sig = kp.signals.EBSD(np.ascontiguousarray(patterns[idx], dtype=np.float32))
    xmap = CrystalMap(rotations=Rotation(q0[idx]), phase_list=PhaseList(loaded_master.phase.deepcopy()),
                      x=np.arange(idx.size, dtype=float))
    tr = float(trust_region_deg)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        import contextlib
        import io

        with contextlib.redirect_stdout(io.StringIO()):
            ref = sig.refine_orientation(
                xmap, detector, loaded_master.signal, energy=energy_keV or 20,
                signal_mask=~mask, method=budget.method, method_kwargs=dict(budget.method_kwargs),
                trust_region=[tr, tr, tr], rtol=budget.rtol, maxeval=budget.maxeval)
    out_q[idx] = ref.rotations.data
    out_s[idx] = np.asarray(ref.prop["scores"], dtype=np.float32)
    if "num_evals" in ref.prop:
        out_e[idx] = np.asarray(ref.prop["num_evals"], dtype=np.int32)
    return out_q, out_s, out_e


def refine_all(result_topk_quaternion: list[np.ndarray], patterns: np.ndarray, detector, masters,
               mask: np.ndarray, budget: RefinementBudget, resolution_deg: float, cancel=None,
               progress=None) -> dict:
    """Refine every phase with the same budget. Returns per-phase arrays and a record."""
    tr = budget.trust_region_deg if budget.trust_region_deg is not None else resolution_deg
    n = patterns.shape[0]
    best_q, best_s, evals, timing = [], [], [], {}
    n_ph = len(masters)
    for p, m in enumerate(masters):
        t0 = time.perf_counter()
        q_p = np.full((n, 4), np.nan)
        s_p = np.full(n, -np.inf, dtype=np.float32)
        e_p = np.zeros(n, dtype=np.int64)
        for r in range(budget.n_starts):
            if cancel is not None:
                cancel.raise_if_cancelled()
            starts = result_topk_quaternion[p][:, min(r, result_topk_quaternion[p].shape[1] - 1)]
            q, s, e = refine_phase(patterns, detector, m, starts, mask, budget, tr, m.energy_keV)
            better = s > s_p
            q_p[better] = q[better]
            s_p[better] = s[better]
            e_p += e
            if progress is not None:
                progress((p * budget.n_starts + r + 1) / (n_ph * budget.n_starts),
                         f"refined phase {p + 1}/{n_ph}, start {r + 1}/{budget.n_starts}")
        best_q.append(q_p)
        best_s.append(s_p)
        evals.append(e_p)
        timing[m.info.phase_name] = time.perf_counter() - t0
    record = {
        "budget": {**budget.to_dict(), "trust_region_deg": tr},
        "mean_evaluations_per_pattern": {masters[p].info.phase_name: float(evals[p].mean() / budget.n_starts)
                                         for p in range(n_ph)},
        "time_s": timing,
        "equal_budget": True,
        "geometry": "fixed detector PC shared by all phases",
    }
    return {"quaternion": best_q, "score": best_s, "evals": evals, "record": record}
