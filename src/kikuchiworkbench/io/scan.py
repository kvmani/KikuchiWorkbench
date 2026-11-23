"""Scan data model shared by all importers.

Patterns are stored flattened as ``(n_points, rows, cols)`` in acquisition
(scan) order and are never modified: numpy arrays are flagged read-only and
lazy arrays (dask, h5py, memmap) are only ever sliced into new arrays.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

GRID_SQUARE = "square"
GRID_HEXAGONAL = "hexagonal"
GRID_POINTS = "points"  # unordered list of points (e.g. simulated sets)

GEOMETRY_FROM_FILE = "file"
GEOMETRY_FROM_USER = "user"
GEOMETRY_MISSING = "missing (default placeholder)"


@dataclass
class GridInfo:
    """Scan grid description.

    For hexagonal grids (EDAX/TSL convention) ``ncols`` is the number of
    columns in odd (first, third, ...) rows; even rows have ``ncols - 1``
    points shifted by half a step. ``step_y`` is ``step_x * sqrt(3) / 2``.
    """

    grid_type: str
    nrows: int
    ncols: int
    step_x: float = 1.0
    step_y: float = 1.0
    unit: str = "um"
    scan_order: str = "row-major, left-to-right, top-to-bottom"

    @property
    def n_points(self) -> int:
        if self.grid_type == GRID_HEXAGONAL:
            n_odd = (self.nrows + 1) // 2
            n_even = self.nrows // 2
            return n_odd * self.ncols + n_even * (self.ncols - 1)
        return self.nrows * self.ncols

    def to_dict(self) -> dict:
        return {
            "grid_type": self.grid_type,
            "nrows": self.nrows,
            "ncols": self.ncols,
            "step_x": self.step_x,
            "step_y": self.step_y,
            "unit": self.unit,
            "scan_order": self.scan_order,
            "n_points": self.n_points,
        }


def grid_indices(grid: GridInfo) -> tuple[np.ndarray, np.ndarray]:
    """Return (row, col) map indices for each point in scan order.

    For hexagonal grids even rows (0-based odd) occupy columns ``0..ncols-2``
    and are drawn half a step to the right by :func:`grid_coordinates`.
    """
    if grid.grid_type == GRID_HEXAGONAL:
        rows, cols = [], []
        for r in range(grid.nrows):
            n = grid.ncols if r % 2 == 0 else grid.ncols - 1
            rows.extend([r] * n)
            cols.extend(range(n))
        return np.asarray(rows, dtype=np.int64), np.asarray(cols, dtype=np.int64)
    rr, cc = np.divmod(np.arange(grid.nrows * grid.ncols, dtype=np.int64), grid.ncols)
    return rr, cc


def grid_coordinates(grid: GridInfo) -> tuple[np.ndarray, np.ndarray]:
    """Return nominal (x, y) stage coordinates for each point in scan order."""
    rr, cc = grid_indices(grid)
    x = cc * grid.step_x
    if grid.grid_type == GRID_HEXAGONAL:
        x = x + (rr % 2) * grid.step_x / 2.0
    y = rr * grid.step_y
    return x.astype(float), y.astype(float)


@dataclass
class ScanData:
    patterns: Any  # (N, rows, cols) array-like, read-only
    grid: GridInfo
    detector: Any  # kikuchipy.detectors.EBSDDetector, internal Bruker PC convention
    x: np.ndarray
    y: np.ndarray
    valid: np.ndarray  # bool (N,), False where a pattern is missing/invalid
    vendor: str
    file_format: str
    geometry_source: str = GEOMETRY_FROM_FILE
    metadata: dict = field(default_factory=dict)
    warnings: list = field(default_factory=list)
    vendor_euler_deg: np.ndarray | None = None  # optional comparison only
    vendor_phase: np.ndarray | None = None
    static_background: np.ndarray | None = None
    source_path: str | None = None
    dataset_path: str | None = None  # dataset actually read (e.g. raw vs processed)

    def __post_init__(self):
        if isinstance(self.patterns, np.ndarray):
            self.patterns.flags.writeable = False
        n = self.n_points
        for name in ("x", "y", "valid"):
            arr = getattr(self, name)
            if len(arr) != n:
                raise ValueError(f"{name} has length {len(arr)}, expected {n}")

    @property
    def n_points(self) -> int:
        return int(self.patterns.shape[0])

    @property
    def pattern_shape(self) -> tuple[int, int]:
        return tuple(int(s) for s in self.patterns.shape[1:])  # type: ignore[return-value]

    @property
    def dtype(self):
        return np.dtype(self.patterns.dtype)

    def get_patterns(self, start: int, stop: int, dtype=np.float32) -> np.ndarray:
        """Return a new (copied) array of patterns ``start:stop`` as ``dtype``."""
        chunk = self.patterns[start:stop]
        if hasattr(chunk, "compute"):
            chunk = chunk.compute()
        return np.array(chunk, dtype=dtype, copy=True)

    def map_indices(self) -> tuple[np.ndarray, np.ndarray]:
        return grid_indices(self.grid)

    def to_map(self, values: np.ndarray, fill=np.nan) -> np.ndarray:
        """Place per-point ``values`` (N, ...) into a (nrows, ncols, ...) map."""
        rr, cc = self.map_indices()
        values = np.asarray(values)
        fill_is_nan = isinstance(fill, float) and bool(np.isnan(fill))
        out_dtype = np.result_type(values.dtype, np.float64) if fill_is_nan else values.dtype
        out = np.full((self.grid.nrows, self.grid.ncols) + values.shape[1:], fill, dtype=out_dtype)
        out[rr, cc] = values
        return out

    def summary(self) -> dict:
        det = self.detector
        return {
            "vendor": self.vendor,
            "file_format": self.file_format,
            "source_path": self.source_path,
            "dataset_path": self.dataset_path,
            "n_points": self.n_points,
            "n_valid": int(np.count_nonzero(self.valid)),
            "pattern_shape": list(self.pattern_shape),
            "dtype": str(self.dtype),
            "grid": self.grid.to_dict(),
            "detector": {
                "pc_bruker_mean": [float(v) for v in np.asarray(det.pc_average).ravel()],
                "pc_varies": bool(det.navigation_size > 1),
                "binning": int(det.binning),
                "px_size_um": float(det.px_size),
                "sample_tilt_deg": float(det.sample_tilt),
                "detector_tilt_deg": float(det.tilt),
                "azimuthal_deg": float(det.azimuthal),
                "twist_deg": float(det.twist),
            },
            "geometry_source": self.geometry_source,
            "has_static_background": self.static_background is not None,
            "has_vendor_orientations": self.vendor_euler_deg is not None,
            "warnings": list(self.warnings),
            "metadata": self.metadata,
        }
