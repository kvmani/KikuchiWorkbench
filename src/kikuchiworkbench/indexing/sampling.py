"""Symmetry-reduced orientation sampling (orix) and resource estimates."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SamplingSpec:
    resolution_deg: float
    method: str = "cubochoric"

    def to_dict(self) -> dict:
        return {"resolution_deg": self.resolution_deg, "method": self.method}


def sample_orientations(phase, spec: SamplingSpec):
    """Sample the fundamental zone of the phase's proper point group (orix)."""
    from orix.sampling import get_sample_fundamental

    return get_sample_fundamental(
        resolution=spec.resolution_deg, point_group=phase.point_group, method=spec.method
    )


# Empirical constant for orix 0.15 cubochoric sampling: N_FZ ~ C / (res^3 * |G|),
# measured for m-3m at 2, 3, 4 deg (within 5%) and 6/mmm at 4 deg.
_CUBOCHORIC_C = 1.93e7


def estimate_count(point_group, resolution_deg: float) -> int:
    """Approximate number of fundamental-zone orientations without generating them."""
    order = point_group.proper_subgroup.size
    return int(max(1, _CUBOCHORIC_C / (resolution_deg**3 * order)))


@dataclass
class ResourceEstimate:
    n_patterns: int
    n_orientations: dict
    pattern_pixels: int
    dictionary_chunk: int
    pattern_chunk: int
    peak_ram_bytes: int
    dictionary_disk_bytes: int

    def to_dict(self) -> dict:
        d = self.__dict__.copy()
        d["peak_ram_GB"] = round(self.peak_ram_bytes / 1e9, 3)
        d["dictionary_disk_GB_if_cached"] = round(self.dictionary_disk_bytes / 1e9, 3)
        return d


def estimate_resources(n_patterns: int, n_orientations: dict, pattern_pixels: int,
                       dictionary_chunk: int, pattern_chunk: int, top_k: int = 5,
                       master_bytes: int = 0) -> ResourceEstimate:
    f4 = 4
    n_phases = max(1, len(n_orientations))
    peak = (
        dictionary_chunk * pattern_pixels * f4 * 2  # projected chunk + normalised copy
        + pattern_chunk * pattern_pixels * f4 * 2  # experimental chunk + normalised copy
        + pattern_chunk * dictionary_chunk * f4  # score block
        + n_patterns * n_phases * top_k * (f4 + 8)  # running top-k
        + master_bytes
    )
    disk = sum(n_orientations.values()) * pattern_pixels * f4
    return ResourceEstimate(n_patterns, dict(n_orientations), pattern_pixels, dictionary_chunk,
                            pattern_chunk, int(peak), int(disk))
