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


DICTIONARY_KIND = "dictionaries"


def dictionary_cache_fields(master_desc: dict, detector, sampling: dict, preprocessor, n: int) -> dict:
    """Cache key: master (checksum, energy selection), detector, sampling grid, shared preprocessing."""
    import kikuchipy

    return {
        "master": {k: master_desc.get(k) for k in ("sha256", "energy_mode", "energy_keV", "energy_weights")},
        "detector": detector_key_fields(detector),
        "sampling": sampling,
        "n_orientations": int(n),
        "preprocessing_shared_key": preprocessor.key(),
        "mask_pixels": int(preprocessor.mask().sum()),
        "projection": {"engine": "kikuchipy", "version": kikuchipy.__version__, "normalised": True,
                       "dtype": "float32"},
    }


def get_or_build_dictionary(cache, projector: DictionaryProjector, rotations, fields: dict,
                            chunk_size: int, progress=None, cancel=None) -> tuple[np.ndarray, bool]:
    """Return a read-only memmap of the normalised dictionary (n, p) and whether it was a cache hit.

    Built dictionaries are verified (shape, finite, unit norm) before promotion;
    a cancelled or failed build leaves nothing in the cache.
    """
    hit = cache.get(DICTIONARY_KIND, fields)
    if hit is not None:
        return np.load(hit / "dictionary.npy", mmap_mode="r"), True
    n = rotations.size
    p = int(projector.preprocessor.mask().sum())
    with cache.stage() as st:
        arr = np.lib.format.open_memmap(st / "dictionary.npy", mode="w+", dtype=np.float32, shape=(n, p))
        for c0 in range(0, n, chunk_size):
            if cancel is not None:
                cancel.raise_if_cancelled()
            arr[c0:c0 + chunk_size] = projector.project(rotations[c0:c0 + chunk_size])
            if progress is not None:
                progress(min(n, c0 + chunk_size) / n)
        arr.flush()
        del arr
        np.save(st / "quaternions.npy", rotations.data)

        def verify(d):
            a = np.load(d / "dictionary.npy", mmap_mode="r")
            if a.shape != (n, p):
                raise RuntimeError(f"dictionary shape {a.shape} != {(n, p)}")
            norms = []
            for c0 in range(0, n, 8192):
                blk = np.asarray(a[c0:c0 + 8192])
                if not np.all(np.isfinite(blk)):
                    raise RuntimeError("non-finite dictionary values")
                norms.append(np.linalg.norm(blk, axis=1))
            nn = np.concatenate(norms)
            bad = int(np.count_nonzero(np.abs(nn - 1) > 1e-3))
            return {"shape": [n, p], "non_unit_norm_rows": bad}

        entry = cache.promote(st, DICTIONARY_KIND, fields, verify)
    return np.load(entry / "dictionary.npy", mmap_mode="r"), False
