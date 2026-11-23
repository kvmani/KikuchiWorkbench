"""Bounded-batch dictionary projection from Lambert masters (kikuchipy)."""

from __future__ import annotations

import warnings
from collections.abc import Iterator
from dataclasses import dataclass

import numpy as np

from .matching import normalize


def single_pc_detector(detector):
    """Return (detector with the mean PC, PC spread) for dictionary projection."""
    from kikuchipy.detectors import EBSDDetector

    pc = np.asarray(detector.pc, dtype=float).reshape(-1, 3)
    mean = pc.mean(axis=0)
    spread = float(np.abs(pc - mean).max()) if pc.shape[0] > 1 else 0.0
    det = EBSDDetector(
        shape=detector.shape, pc=mean, binning=detector.binning, px_size=detector.px_size,
        tilt=detector.tilt, azimuthal=detector.azimuthal, twist=detector.twist,
        sample_tilt=detector.sample_tilt,
    )
    return det, spread


def detector_key_fields(detector) -> dict:
    return {
        "shape": list(detector.shape),
        "pc": [round(float(v), 6) for v in np.asarray(detector.pc_average).ravel()],
        "binning": int(detector.binning),
        "px_size": float(detector.px_size),
        "tilt": round(float(detector.tilt), 6),
        "azimuthal": round(float(detector.azimuthal), 6),
        "twist": round(float(detector.twist), 6),
        "sample_tilt": round(float(detector.sample_tilt), 6),
    }


@dataclass
class DictionaryProjector:
    """Projects one phase's master for a fixed detector, in chunks."""

    master: object  # kikuchipy EBSDMasterPattern (Lambert, both hemispheres)
    detector: object  # single-PC EBSDDetector matching the *raw* pattern shape
    preprocessor: object  # Preprocessor (shared steps applied to simulations)

    def project(self, rotations, normalise: bool = True) -> np.ndarray:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            sim = self.master.get_patterns(
                rotations, self.detector, compute=True, show_progressbar=False,
                chunk_size=max(1, rotations.size),
            )
        x = np.asarray(sim.data, dtype=np.float32).reshape((rotations.size,) + tuple(self.detector.shape))
        x = self.preprocessor.apply_simulated(x)
        if normalise:
            return normalize(x, self.preprocessor.mask())
        return x

    def chunks(self, rotations, chunk_size: int) -> Iterator[tuple[int, np.ndarray]]:
        n = rotations.size
        for i0 in range(0, n, chunk_size):
            i1 = min(n, i0 + chunk_size)
            yield i0, self.project(rotations[i0:i1])
