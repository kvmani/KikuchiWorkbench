"""Phase decision with distinct unindexed, ambiguous and low-signal outcomes.

Score margins are ranking diagnostics, not probabilities. Thresholds must be
chosen on development fixtures and frozen before held-out runs; the defaults
here are provisional and are recorded as such in the manifest.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np

LABEL_INDEXED = 0
LABEL_AMBIGUOUS = 1
LABEL_UNINDEXED = 2
LABEL_LOW_SIGNAL = 3
LABEL_MISSING = 4
LABEL_NAMES = {
    LABEL_INDEXED: "indexed",
    LABEL_AMBIGUOUS: "ambiguous",
    LABEL_UNINDEXED: "unindexed",
    LABEL_LOW_SIGNAL: "low_signal",
    LABEL_MISSING: "missing",
}


@dataclass
class DecisionPolicy:
    min_score: float = 0.10  # NCC below which a pixel is unindexed
    ambiguity_margin: float = 0.005  # phase margin at or below which a pixel is ambiguous
    tie_tolerance: float = 1e-6  # margins this small are exact ties
    min_signal: float | None = None  # signal metric below which a pixel is low-signal
    provenance: str = "provisional defaults (not calibrated on development fixtures)"
    met_error_target_on_dev: bool | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class PhaseDecision:
    label: np.ndarray  # (N,) int8, LABEL_*
    phase: np.ndarray  # (N,) int16 best phase index (-1 where no phase is assigned)
    best_score: np.ndarray  # (N,)
    runner_up_phase: np.ndarray  # (N,) int16 (-1 if single phase)
    runner_up_score: np.ndarray  # (N,)
    margin: np.ndarray  # (N,) best - runner-up phase score (nan if single phase)
    tie: np.ndarray  # (N,) bool exact tie between phases
    low_signal: np.ndarray  # (N,) bool
    best_phase_any: np.ndarray  # (N,) argmax phase even when label is not indexed

    def counts(self) -> dict:
        return {LABEL_NAMES[k]: int(np.count_nonzero(self.label == k)) for k in LABEL_NAMES}


def decide(per_phase_best: np.ndarray, policy: DecisionPolicy,
           signal: np.ndarray | None = None, valid: np.ndarray | None = None) -> PhaseDecision:
    """Decide the phase of each pattern from per-phase best NCC scores (N, n_phases).

    Phase ties are broken towards the lower phase index for ``best_phase_any``
    only; tied pixels are always labelled ambiguous.
    """
    s = np.asarray(per_phase_best, dtype=np.float64)
    n, n_ph = s.shape
    order = np.argsort(-s, axis=1, kind="stable")
    best_p = order[:, 0]
    best = np.take_along_axis(s, order[:, :1], axis=1)[:, 0]
    if n_ph > 1:
        ru_p = order[:, 1]
        ru = np.take_along_axis(s, order[:, 1:2], axis=1)[:, 0]
        margin = best - ru
        tie = margin <= policy.tie_tolerance
    else:
        ru_p = np.full(n, -1)
        ru = np.full(n, np.nan)
        margin = np.full(n, np.nan)
        tie = np.zeros(n, dtype=bool)
    low = np.zeros(n, dtype=bool)
    if policy.min_signal is not None and signal is not None:
        low = np.asarray(signal) < policy.min_signal
    label = np.full(n, LABEL_INDEXED, dtype=np.int8)
    if n_ph > 1:
        label[(margin <= policy.ambiguity_margin) | tie] = LABEL_AMBIGUOUS
    label[best < policy.min_score] = LABEL_UNINDEXED
    label[low] = LABEL_LOW_SIGNAL
    if valid is not None:
        label[~np.asarray(valid, dtype=bool)] = LABEL_MISSING
    phase = np.where(label == LABEL_INDEXED, best_p, -1).astype(np.int16)
    return PhaseDecision(label, phase, best.astype(np.float32), ru_p.astype(np.int16),
                         ru.astype(np.float32), margin.astype(np.float32), tie, low,
                         best_p.astype(np.int16))
