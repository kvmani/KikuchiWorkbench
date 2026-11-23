"""Indexing presets and a pre-launch resource/time check.

A preset is a partial configuration (sampling, preprocessing, matching, refinement, calibration). Explicit
values in a config file or GUI always override the preset; the applied preset name is recorded in the manifest.
Time estimates use throughput constants measured on a 4-core CPU container (see LEDGER Entries 12/15) and
are rough guides, not guarantees.
"""

from __future__ import annotations

import copy
import os
from dataclasses import dataclass

from .indexing.preprocessing import DEFAULT_PIPELINE

PRESETS: dict[str, dict] = {
    "quick": {
        "description": "Quick look: coarse 5° grid, 2× binning, no refinement. Minutes for a first map.",
        "sampling": {"resolution_deg": 5.0},
        "preprocessing": [*copy.deepcopy(DEFAULT_PIPELINE), {"op": "bin", "factor": 2}],
        "matching": {"top_k": 3, "cache_dictionary": True},
        "refinement": {},
        "calibration": {},
    },
    "standard": {
        "description": "Standard: 3° grid, full resolution, dictionary cache, no refinement.",
        "sampling": {"resolution_deg": 3.0},
        "preprocessing": copy.deepcopy(DEFAULT_PIPELINE),
        "matching": {"top_k": 5, "cache_dictionary": True},
        "refinement": {},
        "calibration": {},
    },
    "phase_study": {
        "description": ("Phase study: 2.5° grid, 2× binning, shared PC calibration (16 points) and equal-budget "
                        "refinement for every phase. Use when competing phases are similar."),
        "sampling": {"resolution_deg": 2.5},
        "preprocessing": [*copy.deepcopy(DEFAULT_PIPELINE), {"op": "bin", "factor": 2}],
        "matching": {"top_k": 5, "cache_dictionary": True},
        "refinement": {"enabled": True, "maxeval": 300},
        "calibration": {"enabled": True, "phase": 0, "n_points": 16, "resolution_deg": 4.0},
    },
}

SECTIONS = ("sampling", "preprocessing", "matching", "refinement", "calibration")

# Measured throughput (4-core CPU): see LEDGER. Units: pixel-patterns per second.
PROJECTION_PX_PER_S = 2.0e7      # dictionary projection (kikuchipy, numba)
MATCHING_FLOP_PER_S = 3.0e10     # float32 BLAS dot products
REFINE_PATTERNS_PER_S_3K = 50.0  # pattern-phase refinements per second at ~3400 px (Al–Si run)


def preset_names() -> list[str]:
    return list(PRESETS)


def apply_preset(config: dict, name: str | None) -> dict:
    """Return a new config dict: preset values first, explicit config values on top."""
    if not name:
        return copy.deepcopy(config)
    if name not in PRESETS:
        raise ValueError(f"Unknown preset {name!r}; available: {preset_names()}")
    p = PRESETS[name]
    out = copy.deepcopy(config)
    for sec in SECTIONS:
        if sec == "preprocessing":
            if "preprocessing" not in config:
                out["preprocessing"] = copy.deepcopy(p["preprocessing"])
            continue
        merged = copy.deepcopy(p.get(sec, {}))
        merged.update(config.get(sec, {}) or {})
        out[sec] = merged
    out["preset"] = name
    return out


def available_ram_bytes() -> int | None:
    try:
        import psutil

        return int(psutil.virtual_memory().available)
    except Exception:
        pass
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) * 1024
    except OSError:
        pass
    if os.name == "nt":  # pragma: no cover - Windows without psutil
        try:
            import ctypes

            class MS(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("sullAvailExtendedVirtual", ctypes.c_ulonglong)]

            m = MS()
            m.dwLength = ctypes.sizeof(MS)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
            return int(m.ullAvailPhys)
        except Exception:
            return None
    return None


@dataclass
class LaunchCheck:
    n_patterns: int
    pattern_pixels: int
    n_orientations: dict
    peak_ram_bytes: int
    available_ram_bytes: int | None
    est_projection_s: float
    est_matching_s: float
    est_refinement_s: float
    warnings: list

    @property
    def est_total_s(self) -> float:
        return self.est_projection_s + self.est_matching_s + self.est_refinement_s

    def to_dict(self) -> dict:
        d = dict(self.__dict__)
        d["est_total_s"] = self.est_total_s
        return d

    def summary(self) -> str:
        mins = self.est_total_s / 60
        ram = self.peak_ram_bytes / 1e9
        avail = f" of {self.available_ram_bytes / 1e9:.1f} GB available" if self.available_ram_bytes else ""
        return (f"{self.n_patterns} patterns, {sum(self.n_orientations.values())} orientations, "
                f"≈{ram:.2f} GB RAM{avail}, ≈{mins:.1f} min (rough)")


def launch_check(n_patterns: int, pattern_pixels: int, point_groups: dict, resolution_deg: float,
                 refine: bool = False, dictionary_chunk: int = 2000, pattern_chunk: int = 2048,
                 top_k: int = 5, cached: bool = False) -> LaunchCheck:
    """Estimate memory and time before launching; warn when the run looks too large."""
    from .indexing.sampling import estimate_count, estimate_resources

    n_or = {name: estimate_count(pg, resolution_deg) for name, pg in point_groups.items()}
    est = estimate_resources(n_patterns, n_or, pattern_pixels, dictionary_chunk, pattern_chunk, top_k)
    total_or = sum(n_or.values())
    t_proj = 0.0 if cached else total_or * pattern_pixels / PROJECTION_PX_PER_S
    t_match = 2.0 * n_patterns * total_or * pattern_pixels / MATCHING_FLOP_PER_S
    t_ref = (n_patterns * len(n_or) / REFINE_PATTERNS_PER_S_3K * max(pattern_pixels, 1) / 3400.0) if refine else 0.0
    avail = available_ram_bytes()
    warns = []
    if avail is not None and est.peak_ram_bytes > 0.7 * avail:
        warns.append(f"Estimated peak RAM {est.peak_ram_bytes / 1e9:.1f} GB exceeds 70% of available "
                     f"{avail / 1e9:.1f} GB: lower the chunk sizes, bin patterns or use a coarser grid.")
    if t_proj + t_match + t_ref > 3600:
        warns.append("Estimated run time exceeds one hour: consider the 'quick' preset or an ROI first.")
    if total_or > 500_000:
        warns.append(f"{total_or} orientations: dictionary cache would need "
                     f"{est.dictionary_disk_bytes / 1e9:.1f} GB on disk.")
    return LaunchCheck(n_patterns, pattern_pixels, n_or, est.peak_ram_bytes, avail, t_proj, t_match, t_ref, warns)
