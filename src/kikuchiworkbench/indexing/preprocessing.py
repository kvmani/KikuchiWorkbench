"""Reproducible pattern preprocessing.

A pipeline is a list of step dicts, recorded verbatim in the manifest and in
cache keys. Raw patterns are never modified: each step works on float32 copies.

Steps applied to **experimental** patterns only:

* ``{"op": "static_background", "mode": "subtract"|"divide", "source": "file"|"scan_mean"}``
* ``{"op": "dynamic_background", "sigma": px | "sigma_frac": fraction of width,
  "mode": "subtract"|"divide"}`` (Gaussian blur; default sigma = width / 8)

Steps applied to **both** experimental and simulated patterns (so they stay
comparable):

* ``{"op": "bin", "factor": int}`` (pattern binning; detector binning updated)
* ``{"op": "mask", "shape": "circle", "radius_frac": float}``

Normalisation (zero mean, unit L2 norm over unmasked pixels) is always done by
the matcher, not by the pipeline.
"""

from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass, field

import numpy as np
from scipy import ndimage

EXPERIMENTAL_ONLY = {"static_background", "dynamic_background"}
SHARED = {"bin", "mask"}
KNOWN = EXPERIMENTAL_ONLY | SHARED

DEFAULT_PIPELINE = [
    {"op": "static_background", "mode": "subtract", "source": "scan_mean"},
    {"op": "dynamic_background", "sigma_frac": 0.125, "mode": "subtract"},
]


def validate_pipeline(steps: list[dict]) -> list[dict]:
    out = []
    for s in steps:
        if "op" not in s or s["op"] not in KNOWN:
            raise ValueError(f"Unknown preprocessing step {s!r}; known: {sorted(KNOWN)}")
        if s["op"] == "bin" and int(s.get("factor", 1)) < 1:
            raise ValueError("bin factor must be >= 1")
        if s["op"] == "mask" and not 0 < float(s.get("radius_frac", 0.5)) <= 1.0:
            raise ValueError("mask radius_frac must be in (0, 1]")
        out.append(dict(s))
    return out


@dataclass
class Preprocessor:
    steps: list[dict]
    pattern_shape: tuple[int, int]  # raw (binned-by-camera) shape
    static_background: np.ndarray | None = None
    notes: list[str] = field(default_factory=list)

    def __post_init__(self):
        self.steps = validate_pipeline(self.steps)

    # ------------------------------------------------------------ geometry

    @property
    def bin_factor(self) -> int:
        f = 1
        for s in self.steps:
            if s["op"] == "bin":
                f *= int(s["factor"])
        return f

    @property
    def output_shape(self) -> tuple[int, int]:
        f = self.bin_factor
        return (self.pattern_shape[0] // f, self.pattern_shape[1] // f)

    def mask(self) -> np.ndarray:
        """Boolean mask (True = pixel used) in the output shape."""
        h, w = self.output_shape
        m = np.ones((h, w), dtype=bool)
        for s in self.steps:
            if s["op"] == "mask":
                r = float(s.get("radius_frac", 0.5)) * min(h, w)
                yy, xx = np.mgrid[:h, :w]
                m &= (yy - (h - 1) / 2) ** 2 + (xx - (w - 1) / 2) ** 2 <= r**2
        return m

    def adapt_detector(self, detector):
        """Return a detector matching the output pattern shape (binning applied)."""
        f = self.bin_factor
        if f == 1:
            return detector
        from kikuchipy.detectors import EBSDDetector

        h, w = self.output_shape
        return EBSDDetector(
            shape=(h, w), pc=detector.pc, binning=detector.binning * f, px_size=detector.px_size,
            tilt=detector.tilt, azimuthal=detector.azimuthal, twist=detector.twist,
            sample_tilt=detector.sample_tilt,
        )

    # ------------------------------------------------------------ setup

    def fit(self, scan, max_patterns: int = 2000, seed: int = 0) -> Preprocessor:
        """Compute scan-dependent quantities (e.g. scan-mean static background)."""
        for s in self.steps:
            if s["op"] == "static_background":
                src = s.get("source", "scan_mean")
                if src == "file" and scan.static_background is not None:
                    self.static_background = np.asarray(scan.static_background, dtype=np.float32)
                    self.notes.append("static background from file")
                else:
                    if src == "file":
                        self.notes.append("file static background missing; using scan mean")
                    n = scan.n_points
                    idx = np.arange(n)
                    if n > max_patterns:
                        idx = np.sort(np.random.default_rng(seed).choice(n, max_patterns, replace=False))
                    acc = np.zeros(scan.pattern_shape, dtype=np.float64)
                    for i0 in range(0, idx.size, 256):
                        sel = idx[i0:i0 + 256]
                        acc += scan.get_patterns(int(sel[0]), int(sel[-1]) + 1)[sel - sel[0]].sum(axis=0)
                    self.static_background = (acc / idx.size).astype(np.float32)
                    self.notes.append(f"static background = mean of {idx.size} patterns (seed {seed})")
        return self

    # ------------------------------------------------------------ apply

    def _bin(self, x: np.ndarray, f: int) -> np.ndarray:
        n, h, w = x.shape
        h2, w2 = h // f, w // f
        return x[:, : h2 * f, : w2 * f].reshape(n, h2, f, w2, f).mean(axis=(2, 4))

    def apply_experimental(self, patterns: np.ndarray) -> np.ndarray:
        x = np.array(patterns, dtype=np.float32, copy=True)
        for s in self.steps:
            op = s["op"]
            if op == "static_background":
                if self.static_background is None:
                    raise RuntimeError("Preprocessor.fit() must be called before applying static background")
                bg = self.static_background
                if s.get("mode", "subtract") == "divide":
                    x /= np.where(bg > 0, bg, 1.0)
                else:
                    x -= bg
            elif op == "dynamic_background":
                sig = float(s["sigma"]) if "sigma" in s else float(s.get("sigma_frac", 0.125)) * x.shape[-1]
                blur = ndimage.gaussian_filter(x, sigma=(0, sig, sig), mode="nearest")
                if s.get("mode", "divide") == "divide":
                    blur -= blur.min(axis=(1, 2), keepdims=True) - 1e-3 * (np.ptp(blur, axis=(1, 2), keepdims=True) + 1e-6)
                    x /= blur
                else:
                    x -= blur
            elif op == "bin":
                x = self._bin(x, int(s["factor"]))
        return x

    def apply_simulated(self, patterns: np.ndarray) -> np.ndarray:
        x = np.asarray(patterns, dtype=np.float32)
        for s in self.steps:
            if s["op"] == "bin":
                x = self._bin(x, int(s["factor"]))
        return x

    # ------------------------------------------------------------ record

    def describe(self) -> dict:
        return {
            "steps": copy.deepcopy(self.steps),
            "pattern_shape_in": list(self.pattern_shape),
            "pattern_shape_out": list(self.output_shape),
            "mask_pixels": int(self.mask().sum()),
            "notes": list(self.notes),
            "static_background_sha256": (
                hashlib.sha256(self.static_background.tobytes()).hexdigest()
                if self.static_background is not None else None
            ),
        }

    def key(self) -> str:
        """Key for the parts that affect simulated patterns (dictionary caching)."""
        shared = [s for s in self.steps if s["op"] in SHARED]
        return hashlib.sha256(json.dumps(shared, sort_keys=True).encode()).hexdigest()[:16]


def signal_metric(patterns: np.ndarray, mask: np.ndarray | None = None) -> np.ndarray:
    """Signal-to-noise proxy of preprocessed patterns.

    Ratio of the standard deviation of the smoothed pattern (Kikuchi band
    structure, sigma = 1.5 px) to that of the residual (pixel noise). Pure noise
    gives values well below 1. It flags low-signal pixels only and is reported
    separately from orientation fit and phase separation.
    """
    x = np.asarray(patterns, dtype=np.float32)
    smooth = ndimage.gaussian_filter(x, sigma=(0, 1.5, 1.5), mode="nearest")
    resid = x - smooth
    if mask is not None:
        m = mask.ravel()
        smooth = smooth.reshape(x.shape[0], -1)[:, m]
        resid = resid.reshape(x.shape[0], -1)[:, m]
    else:
        smooth = smooth.reshape(x.shape[0], -1)
        resid = resid.reshape(x.shape[0], -1)
    return smooth.std(axis=1) / (resid.std(axis=1) + 1e-12)
