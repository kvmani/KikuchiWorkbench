"""Detect scan file formats from file structure and version.

Extensions are used only to choose which structural check to run; the file
content decides the format. Pattern-free inputs are rejected with
instructions for exporting patterns.
"""

from __future__ import annotations

import os
import struct
from dataclasses import dataclass, field
from pathlib import Path

import h5py
import numpy as np

from ..errors import PatternFreeInputError, UnsupportedFormatError

HDF5_SIGNATURE = b"\x89HDF\r\n\x1a\n"

FIXTURE_FORMAT_NAME = "kwb-fixture"

PATTERN_FREE_ADVICE = {
    ".ang": (
        "An .ang file holds EDAX/TSL orientations only. Export the scan from OIM/APEX as "
        "H5EBSD (.h5/.oh5) with patterns, or export the patterns as .up1/.up2 and supply the "
        "map dimensions and detector geometry."
    ),
    ".ctf": (
        "A .ctf file holds Oxford orientations only. Export the project from AZtec as H5OINA "
        "with 'Unprocessed Patterns' (or processed patterns) enabled, or as .ebsp."
    ),
    ".osc": "An .osc file holds EDAX/TSL orientations only. Export patterns as H5EBSD or .up1/.up2.",
    ".cpr": "A .cpr/.crc pair holds Oxford orientations only. Export H5OINA with patterns.",
    ".crc": "A .cpr/.crc pair holds Oxford orientations only. Export H5OINA with patterns.",
}


@dataclass
class FormatInfo:
    file_format: str  # e.g. 'oxford_h5oina', 'oxford_ebsp', 'edax_h5ebsd', 'edax_up1', ...
    vendor: str
    version: str | None = None
    scan_groups: list[str] = field(default_factory=list)
    pattern_datasets: dict[str, list[str]] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "file_format": self.file_format,
            "vendor": self.vendor,
            "version": self.version,
            "scan_groups": list(self.scan_groups),
            "pattern_datasets": {k: list(v) for k, v in self.pattern_datasets.items()},
            "notes": list(self.notes),
        }


def _read_str(obj) -> str:
    v = obj[()]
    if isinstance(v, np.ndarray):
        v = v.ravel()[0] if v.size else b""
    if isinstance(v, bytes):
        v = v.decode(errors="replace")
    return str(v).strip()


def _top_value(h: h5py.File, *names: str) -> str | None:
    # EDAX OIM writes top-level keys with a leading space (" Manufacturer").
    lower = {k.strip().lower(): k for k in h.keys()}
    for n in names:
        if n.lower() in lower:
            obj = h[lower[n.lower()]]
            if isinstance(obj, h5py.Dataset):
                return _read_str(obj)
    for n in names:
        for k, v in h.attrs.items():
            if k.strip().lower() == n.lower():
                return v.decode() if isinstance(v, bytes) else str(v)
    return None


def is_hdf5(path: str | os.PathLike) -> bool:
    with open(path, "rb") as f:
        return f.read(8) == HDF5_SIGNATURE


def _detect_hdf5(path: Path) -> FormatInfo:
    with h5py.File(path, "r") as h:
        if h.attrs.get("kwb_format") in (FIXTURE_FORMAT_NAME, FIXTURE_FORMAT_NAME.encode()):
            ver = h.attrs.get("kwb_format_version", "1")
            return FormatInfo("kwb_fixture", "kikuchiworkbench", str(ver), ["/"], {"/": ["patterns"]})
        if "EMheader" in h and "EMData" in h:
            em = h["EMData"]
            if "EBSDmaster" in em or ("MCOpenCL" in em and "EBSD" not in em):
                raise UnsupportedFormatError(
                    f"{path.name} is an EMsoft master-pattern or Monte Carlo file, not a scan.",
                    "Load it as a candidate phase master (step 2), not as a scan.",
                )
            if "EBSD" in em and "EBSDPatterns" in em["EBSD"]:
                return FormatInfo("emsoft_ebsd", "EMsoft", None, ["EMData/EBSD"],
                                  {"EMData/EBSD": ["EBSDPatterns"]})
            raise PatternFreeInputError(
                f"{path.name} is an EMsoft file without EBSD patterns.",
                "Run EMEBSD with pattern output enabled, or load an EMsoft master as a phase.",
            )
        manufacturer = _top_value(h, "Manufacturer")
        version = _top_value(h, "Version", "Format Version")
        if manufacturer is None:
            raise UnsupportedFormatError(
                f"{path.name} is an HDF5 file without a recognised 'Manufacturer' entry.",
                "Supported HDF5 scans are Oxford H5OINA, EDAX/TSL H5EBSD (.h5/.oh5), EMsoft "
                "simulated EBSD and the KikuchiWorkbench fixture format.",
            )
        man = manufacturer.lower()
        scan_groups = [k for k, v in h.items() if isinstance(v, h5py.Group) and "EBSD" in v]
        if man.startswith("oxford"):
            fmt, vendor, dsets = "oxford_h5oina", "Oxford Instruments", ["Unprocessed Patterns", "Processed Patterns"]
        elif man.startswith("edax"):
            fmt, vendor, dsets = "edax_h5ebsd", "EDAX/TSL", ["Pattern"]
        elif man == "kikuchipy":
            fmt, vendor, dsets = "kikuchipy_h5ebsd", "kikuchipy", ["patterns"]
        elif man.startswith("bruker"):
            fmt, vendor, dsets = "bruker_h5ebsd", "Bruker Nano", ["RawPatterns"]
        else:
            raise UnsupportedFormatError(
                f"{path.name}: manufacturer {manufacturer!r} is not supported.",
                "First release supports Oxford Instruments and EDAX/TSL exports.",
            )
        if not scan_groups:
            raise PatternFreeInputError(
                f"{path.name} ({vendor}) contains no scan group with EBSD data.",
                "Re-export the scan with EBSD data and patterns included.",
            )
        found: dict[str, list[str]] = {}
        for g in scan_groups:
            data = h[g]["EBSD"].get("Data")
            if data is None:
                continue
            present = [d for d in dsets if d in data and isinstance(data[d], h5py.Dataset)]
            if present:
                found[g] = present
        if not found:
            raise PatternFreeInputError(
                f"{path.name} ({vendor}) has orientation data but no pattern datasets "
                f"(looked for {dsets}).",
                {
                    "oxford_h5oina": "In AZtec, export H5OINA with 'Unprocessed Patterns' "
                    "(preferred) or 'Processed Patterns' enabled.",
                    "edax_h5ebsd": "In OIM Analysis/APEX, export H5EBSD with patterns "
                    "included, or export patterns as .up1/.up2.",
                }.get(fmt, "Re-export the scan with patterns included."),
            )
        info = FormatInfo(fmt, vendor, version, scan_groups, found)
        if fmt == "oxford_h5oina":
            for g, present in found.items():
                if "Unprocessed Patterns" not in present:
                    info.notes.append(
                        f"Scan group {g}: only processed patterns are present; raw patterns "
                        "preferred for reproducible preprocessing."
                    )
        return info


def _detect_up(path: Path) -> FormatInfo:
    size = path.stat().st_size
    with open(path, "rb") as f:
        head = f.read(42)
    if len(head) < 16:
        raise UnsupportedFormatError(f"{path.name} is too small to be an EDAX UP file.")
    version, sx, sy, offset = struct.unpack("<4I", head[:16])
    nbytes = 1 if path.suffix.lower() == ".up1" else 2
    if version == 2 or version > 10:
        raise UnsupportedFormatError(
            f"{path.name}: EDAX UP file version {version} is not supported (1 or >= 3).",
            "Re-export patterns from OIM with a current version, or export H5EBSD.",
        )
    if not (8 <= sx <= 4096 and 8 <= sy <= 4096) or offset > size:
        raise UnsupportedFormatError(
            f"{path.name}: header values (sx={sx}, sy={sy}, offset={offset}) are implausible."
        )
    n_float = (size - offset) / (sx * sy * nbytes)
    notes = []
    if abs(n_float - round(n_float)) > 1e-9:
        notes.append("File size is not a whole number of patterns (truncated file?).")
    info = FormatInfo(f"edax_{path.suffix.lower()[1:]}", "EDAX/TSL", str(version), notes=notes)
    if version >= 3:
        nx, ny = struct.unpack("<2I", head[17:25])
        is_hex = bool(head[25])
        info.notes.append(f"header grid nx={nx} ny={ny} hexagonal={is_hex}")
    else:
        info.notes.append("version 1 header has no map dimensions; supply nav_shape.")
    return info


def _detect_ebsp(path: Path) -> FormatInfo:
    with open(path, "rb") as f:
        first = struct.unpack("<q", f.read(8))[0]
    version = -first if first < 0 else 0
    if version > 10:
        raise UnsupportedFormatError(f"{path.name}: unrecognised .ebsp version {version}.")
    return FormatInfo(
        "oxford_ebsp",
        "Oxford Instruments",
        str(version),
        notes=["Binary .ebsp stores no detector calibration; supply geometry or a companion H5OINA."],
    )


def detect_format(path: str | os.PathLike) -> FormatInfo:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(p)
    ext = p.suffix.lower()
    if ext in PATTERN_FREE_ADVICE:
        raise PatternFreeInputError(
            f"{p.name} contains orientations but no Kikuchi patterns; full-pattern matching "
            "needs the recorded patterns.",
            PATTERN_FREE_ADVICE[ext],
        )
    if is_hdf5(p):
        return _detect_hdf5(p)
    if ext in (".up1", ".up2"):
        return _detect_up(p)
    if ext == ".ebsp":
        return _detect_ebsp(p)
    from .plugins import find_reader

    plugin = find_reader(p)
    if plugin is not None:
        return FormatInfo(plugin.name, plugin.vendor, None, notes=[f"read by plug-in: {plugin.description}"])
    raise UnsupportedFormatError(
        f"{p.name}: unrecognised file type.",
        "Supported scans: Oxford .h5oina/.ebsp, EDAX/TSL .h5/.oh5/.up1/.up2, EMsoft EBSD HDF5, "
        "KikuchiWorkbench fixtures, plus reader plug-ins (`kwb readers`).",
    )
