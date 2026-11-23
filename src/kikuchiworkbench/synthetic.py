"""Deterministic synthetic EBSD scans with ground truth.

Patterns are projected from masters with known (off-grid, random) orientations
and phase labels, then a smooth static background, gain and Poisson noise are
added. All seeds and parameters are recorded in the fixture provenance.
"""

from __future__ import annotations

import warnings
from dataclasses import asdict, dataclass

import numpy as np

from .io.scan import GRID_SQUARE, GridInfo, ScanData, grid_coordinates


@dataclass
class SyntheticSpec:
    nrows: int = 6
    ncols: int = 6
    pattern_shape: tuple[int, int] = (60, 60)
    pc: tuple[float, float, float] = (0.4210, 0.2165, 0.5020)  # asymmetric, off-centre (Bruker)
    sample_tilt: float = 70.0
    detector_tilt: float = 0.0
    binning: int = 8
    px_size: float = 70.0
    counts: float = 400.0  # mean signal counts per pixel (Poisson noise level)
    background_fraction: float = 0.6  # static background relative to signal
    seed: int = 42
    phase_layout: str = "halves"  # 'halves' | 'random' | 'single'
    dtype: str = "uint16"

    def to_dict(self) -> dict:
        return asdict(self)


def random_rotations(n: int, seed: int):
    from orix.quaternion import Rotation

    rng = np.random.default_rng(seed)
    q = rng.normal(size=(n, 4))
    q /= np.linalg.norm(q, axis=1, keepdims=True)
    q[q[:, 0] < 0] *= -1
    return Rotation(q)


def phase_layout(spec: SyntheticSpec, n_phases: int) -> np.ndarray:
    n = spec.nrows * spec.ncols
    if n_phases == 1 or spec.phase_layout == "single":
        return np.zeros(n, dtype=np.int16)
    if spec.phase_layout == "random":
        return np.random.default_rng(spec.seed + 1).integers(0, n_phases, n).astype(np.int16)
    rr, cc = np.divmod(np.arange(n), spec.ncols)
    return np.minimum((cc * n_phases) // spec.ncols, n_phases - 1).astype(np.int16)


def _background(shape, seed):
    h, w = shape
    yy, xx = np.mgrid[:h, :w]
    cy, cx = 0.45 * h, 0.52 * w
    bg = np.exp(-(((yy - cy) / (0.7 * h)) ** 2 + ((xx - cx) / (0.8 * w)) ** 2))
    return bg / bg.mean()


def make_synthetic_scan(masters, spec: SyntheticSpec, rotations=None, phase_ids=None):
    """Return (ScanData, truth dict). ``masters`` is a list of LoadedMaster."""
    from kikuchipy.detectors import EBSDDetector

    n = spec.nrows * spec.ncols
    det = EBSDDetector(shape=spec.pattern_shape, pc=spec.pc, sample_tilt=spec.sample_tilt,
                       tilt=spec.detector_tilt, binning=spec.binning, px_size=spec.px_size)
    if phase_ids is None:
        phase_ids = phase_layout(spec, len(masters))
    if rotations is None:
        rotations = random_rotations(n, spec.seed)
    rng = np.random.default_rng(spec.seed + 2)
    clean = np.zeros((n,) + tuple(spec.pattern_shape), dtype=np.float32)
    for p, m in enumerate(masters):
        sel = np.nonzero(phase_ids == p)[0]
        if sel.size == 0:
            continue
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            sim = m.signal.get_patterns(rotations[sel], det, compute=True, show_progressbar=False)
        clean[sel] = np.asarray(sim.data, dtype=np.float32).reshape((sel.size,) + tuple(spec.pattern_shape))
    # scale each pattern to [0, 1] then add background and noise
    mn = clean.min(axis=(1, 2), keepdims=True)
    mx = clean.max(axis=(1, 2), keepdims=True)
    sig = (clean - mn) / np.maximum(mx - mn, 1e-9)
    bg = _background(spec.pattern_shape, spec.seed)
    if spec.counts > 0:
        noisy = rng.poisson(spec.counts * (sig + spec.background_fraction * bg[None])).astype(np.float64)
    else:  # noise-free: scale to a fixed range
        noisy = 1000.0 * (sig + spec.background_fraction * bg[None])
    info = np.iinfo(np.dtype(spec.dtype))
    pats = np.clip(np.round(noisy), 0, info.max).astype(spec.dtype)
    grid = GridInfo(GRID_SQUARE, spec.nrows, spec.ncols, 1.0, 1.0)
    x, y = grid_coordinates(grid)
    scan = ScanData(
        patterns=pats, grid=grid, detector=det, x=x, y=y, valid=np.ones(n, dtype=bool),
        vendor="synthetic", file_format="synthetic", geometry_source="file",
        metadata={"synthetic_spec": spec.to_dict(), "masters": [m.describe() for m in masters]},
    )
    truth = {
        "quaternion": rotations.data,
        "euler_deg": np.rad2deg(rotations.to_euler()),
        "phase_id": phase_ids,
        "phase_names": [m.info.phase_name for m in masters],
    }
    return scan, truth


def misorientation_deg(q_a: np.ndarray, q_b: np.ndarray, point_group) -> np.ndarray:
    """Symmetry-aware disorientation angle (degrees) between orientation arrays (N, 4)."""
    from orix.quaternion import Orientation

    oa = Orientation(q_a, symmetry=point_group)
    ob = Orientation(q_b, symmetry=point_group)
    return np.asarray(oa.angle_with(ob, degrees=True))
