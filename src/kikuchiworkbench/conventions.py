"""Reference-frame and projection-centre (PC) conventions.

Internal convention (used everywhere inside the workbench) is the
Bruker/kikuchipy convention, see ``docs/conventions.md``:

* ``pcx`` - horizontal PC position as a fraction of detector width, from the
  left edge of the detector as seen from the sample (pixel column 0).
* ``pcy`` - vertical PC position as a fraction of detector height, from the
  top edge (pixel row 0).
* ``pcz`` - specimen-to-scintillator distance as a fraction of detector height.

Detector pixel axes: row index increases downwards, column index increases to
the right, as stored in ``patterns[..., row, col]``.

Conversions below are written out explicitly (rather than only delegated) so
that the formulas are reviewable; ``tests/test_conventions.py`` cross-checks
them against kikuchipy to catch upstream changes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np

PCConvention = Literal["bruker", "tsl", "oxford", "emsoft", "emsoft4"]

INTERNAL_PC_CONVENTION: PCConvention = "bruker"

#: Orientation convention: orix Rotation/Orientation objects are passive
#: rotations taking sample coordinates to crystal coordinates (Bunge ZXZ
#: Euler angles in radians internally, degrees in user-facing exports).
ROTATION_CONVENTION = {
    "euler": "Bunge ZXZ (phi1, Phi, phi2)",
    "direction": "passive: sample frame -> crystal frame (orix/MTEX convention)",
    "sample_frame": "kikuchipy/EDAX-style: X right (RD), Y down (TD), Z into sample (ND)",
    "export_units": "degrees",
}


@dataclass(frozen=True)
class DetectorShape:
    """Detector shape in *binned* pixels with the binning factor."""

    nrows: int
    ncols: int
    binning: int = 1

    @property
    def aspect_ratio(self) -> float:
        return self.ncols / self.nrows


def _as_pc(pc) -> np.ndarray:
    arr = np.asarray(pc, dtype=float)
    if arr.shape[-1] != 3:
        raise ValueError(f"PC must have last dimension 3, got shape {arr.shape}")
    return arr.copy()


def to_bruker(
    pc, convention: PCConvention, shape: DetectorShape, px_size: float = 1.0
) -> np.ndarray:
    """Convert a PC from ``convention`` to the internal Bruker convention.

    ``px_size`` is the *unbinned* detector pixel size in microns and is only
    used for the EMsoft convention, where ``L`` is in microns.
    """
    pc = _as_pc(pc)
    conv = convention.lower()
    out = pc.copy()
    if conv == "bruker":
        return out
    if conv == "tsl" or conv == "edax":
        # EDAX/TSL: origin at bottom-left, PCz relative to the smaller detector side.
        out[..., 1] = 1.0 - pc[..., 1]
        out[..., 2] = pc[..., 2] * min(shape.nrows, shape.ncols) / shape.nrows
        return out
    if conv == "oxford":
        # Oxford: all coordinates relative to detector width, origin bottom-left.
        out[..., 1] = 1.0 - pc[..., 1] * shape.aspect_ratio
        out[..., 2] = pc[..., 2] * shape.aspect_ratio
        return out
    if conv in ("emsoft", "emsoft5", "emsoft4"):
        # EMsoft: (xpc, ypc) in unbinned pixels from detector centre, L in microns.
        # EMsoft < 5 uses the opposite sign of xpc.
        xpc = -pc[..., 0] if conv == "emsoft4" else pc[..., 0]
        nx = shape.ncols * shape.binning
        ny = shape.nrows * shape.binning
        out[..., 0] = 0.5 - xpc / nx
        out[..., 1] = 0.5 - pc[..., 1] / ny
        out[..., 2] = pc[..., 2] / (ny * px_size)
        return out
    raise ValueError(f"Unknown PC convention {convention!r}")


def from_bruker(
    pc, convention: PCConvention, shape: DetectorShape, px_size: float = 1.0
) -> np.ndarray:
    """Convert an internal (Bruker) PC to ``convention``."""
    pc = _as_pc(pc)
    conv = convention.lower()
    out = pc.copy()
    if conv == "bruker":
        return out
    if conv == "tsl" or conv == "edax":
        out[..., 1] = 1.0 - pc[..., 1]
        out[..., 2] = pc[..., 2] * shape.nrows / min(shape.nrows, shape.ncols)
        return out
    if conv == "oxford":
        out[..., 1] = (1.0 - pc[..., 1]) / shape.aspect_ratio
        out[..., 2] = pc[..., 2] / shape.aspect_ratio
        return out
    if conv in ("emsoft", "emsoft5", "emsoft4"):
        nx = shape.ncols * shape.binning
        ny = shape.nrows * shape.binning
        out[..., 0] = (0.5 - pc[..., 0]) * nx
        if conv == "emsoft4":
            out[..., 0] = -out[..., 0]
        out[..., 1] = (0.5 - pc[..., 1]) * ny
        out[..., 2] = pc[..., 2] * ny * px_size
        return out
    raise ValueError(f"Unknown PC convention {convention!r}")


def convert_pc(
    pc,
    src: PCConvention,
    dst: PCConvention,
    shape: DetectorShape,
    px_size: float = 1.0,
) -> np.ndarray:
    """Convert a PC between any two supported conventions."""
    return from_bruker(to_bruker(pc, src, shape, px_size), dst, shape, px_size)


def pc_pixel_position(pc_bruker, shape: DetectorShape) -> tuple[float, float]:
    """Return the PC position as (row, col) in binned pixel coordinates.

    Pixel centres are at integer coordinates; the detector spans
    ``[-0.5, ncols - 0.5]`` horizontally.
    """
    pc = _as_pc(pc_bruker)
    col = pc[..., 0] * shape.ncols - 0.5
    row = pc[..., 1] * shape.nrows - 0.5
    return float(np.mean(row)), float(np.mean(col))


def describe() -> dict:
    """Machine-readable summary of conventions for run manifests."""
    return {
        "pc_internal": "bruker (kikuchipy)",
        "pc_definition": {
            "pcx": "fraction of detector width from left edge (column 0)",
            "pcy": "fraction of detector height from top edge (row 0)",
            "pcz": "detector distance as fraction of detector height",
        },
        "detector_pixels": "patterns[..., row, col]; row increases down, col increases right",
        "rotation": dict(ROTATION_CONVENTION),
        "units": {"angles_export": "degrees", "length": "micrometre", "voltage": "kV"},
    }
