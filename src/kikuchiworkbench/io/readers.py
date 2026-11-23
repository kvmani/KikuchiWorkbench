"""Scan readers: every supported format is returned as :class:`ScanData`.

kikuchipy readers are used where they support the variant; EDAX/TSL H5EBSD
and hexagonal UP files are read here because kikuchipy rejects or flattens
hexagonal grids. All geometry is converted to the internal Bruker PC
convention (see ``docs/conventions.md``).
"""

from __future__ import annotations

import json
import os
import struct
import warnings
from pathlib import Path

import h5py
import numpy as np

from ..errors import MissingMetadataError, UnsupportedFormatError
from .detect import FIXTURE_FORMAT_NAME, FormatInfo, detect_format
from .scan import (
    GEOMETRY_FROM_FILE,
    GEOMETRY_FROM_USER,
    GEOMETRY_MISSING,
    GRID_HEXAGONAL,
    GRID_POINTS,
    GRID_SQUARE,
    GridInfo,
    ScanData,
    grid_coordinates,
)


def _detector(**kw):
    from kikuchipy.detectors import EBSDDetector

    return EBSDDetector(**kw)


def _h5_scalar(obj, default=None):
    if obj is None:
        return default
    v = obj[()] if isinstance(obj, h5py.Dataset) else obj
    if isinstance(v, np.ndarray):
        if v.size == 1:
            v = v.ravel()[0]
        else:
            return v
    if isinstance(v, bytes):
        v = v.decode(errors="replace").strip()
    if isinstance(v, np.generic):
        v = v.item()
    return v


def _pc_is_plausible(pc_bruker: np.ndarray) -> bool:
    pc = np.asarray(pc_bruker, dtype=float).reshape(-1, 3)
    return bool(
        np.all(np.isfinite(pc))
        and np.all(pc[:, 2] > 0.05)
        and np.all(np.abs(pc[:, :2] - 0.5) < 1.5)
    )


def _apply_user_geometry(scan: ScanData, geometry: dict | None) -> ScanData:
    """Override detector geometry with user-supplied values (recorded)."""
    if not geometry:
        if not _pc_is_plausible(scan.detector.pc):
            scan.geometry_source = GEOMETRY_MISSING
            scan.warnings.append(
                "Projection centre is missing or implausible in the file. Supply a calibrated "
                "PC (pc + pc_convention) before indexing; results with a placeholder PC are "
                "not meaningful."
            )
        return scan
    det = scan.detector
    kw = {
        "shape": det.shape,
        "px_size": geometry.get("px_size", det.px_size),
        "binning": geometry.get("binning", det.binning),
        "tilt": geometry.get("tilt", det.tilt),
        "azimuthal": geometry.get("azimuthal", det.azimuthal),
        "twist": geometry.get("twist", det.twist),
        "sample_tilt": geometry.get("sample_tilt", det.sample_tilt),
    }
    if "pc" in geometry:
        kw["pc"] = geometry["pc"]
        kw["convention"] = geometry.get("pc_convention", "bruker")
    else:
        kw["pc"] = det.pc
        kw["convention"] = "bruker"
    scan.detector = _detector(**kw)
    scan.geometry_source = GEOMETRY_FROM_USER
    scan.metadata["user_geometry"] = {
        k: (np.asarray(v).tolist() if isinstance(v, (list, tuple, np.ndarray)) else v)
        for k, v in geometry.items()
    }
    return scan


def _from_signal(sig, info: FormatInfo, path: Path, dataset_path: str | None) -> ScanData:
    """Build ScanData from a kikuchipy EBSD signal with a 2D or 1D navigation."""
    nav = sig.axes_manager.navigation_shape[::-1]
    data = sig.data
    sy, sx = sig.axes_manager.signal_shape[::-1]
    if len(nav) == 2:
        ny, nx = nav
        patterns = data.reshape((ny * nx, sy, sx))
        axes = sig.axes_manager.navigation_axes
        dx = float(axes[0].scale)
        dy = float(axes[1].scale)
        grid = GridInfo(GRID_SQUARE, ny, nx, dx, dy, unit=str(axes[0].units or "um"))
    elif len(nav) == 1:
        n = nav[0]
        patterns = data.reshape((n, sy, sx))
        grid = GridInfo(GRID_SQUARE, 1, n)
    elif len(nav) == 0:
        patterns = data.reshape((1, sy, sx))
        grid = GridInfo(GRID_SQUARE, 1, 1)
    else:
        raise UnsupportedFormatError(f"Unexpected navigation shape {nav}")
    x, y = grid_coordinates(grid)
    det = sig.detector
    if det.navigation_size > 1:
        pc = det.pc.reshape(-1, 3)
        if pc.shape[0] != patterns.shape[0]:
            pc = det.pc_average
        det = _detector(
            shape=det.shape, px_size=det.px_size, binning=det.binning, tilt=det.tilt,
            azimuthal=det.azimuthal, twist=det.twist, sample_tilt=det.sample_tilt, pc=pc,
        )
    if isinstance(patterns, np.ndarray):
        patterns = np.asarray(patterns)
    static_bg = None
    if getattr(sig, "static_background", None) is not None:
        static_bg = np.asarray(sig.static_background)
    vendor_euler = None
    xmap = getattr(sig, "xmap", None)
    if xmap is not None and xmap.size == patterns.shape[0] and xmap.phases.size and any(
        p.point_group is not None for _, p in xmap.phases
    ):
        vendor_euler = np.rad2deg(xmap.rotations.to_euler())
    return ScanData(
        patterns=patterns,
        grid=grid,
        detector=det,
        x=x,
        y=y,
        valid=np.ones(patterns.shape[0], dtype=bool),
        vendor=info.vendor,
        file_format=info.file_format,
        metadata={"format": info.to_dict()},
        warnings=list(info.notes),
        vendor_euler_deg=vendor_euler,
        static_background=static_bg,
        source_path=str(path),
        dataset_path=dataset_path,
    )


# ----------------------------------------------------------------- Oxford


def _read_h5oina(path: Path, info: FormatInfo, scan_group: str | None, prefer_raw: bool, lazy: bool):
    import kikuchipy as kp

    group = scan_group or next(iter(info.pattern_datasets))
    present = info.pattern_datasets.get(group)
    if present is None:
        raise UnsupportedFormatError(
            f"Scan group {group!r} has no patterns; available: {list(info.pattern_datasets)}"
        )
    use_raw = prefer_raw and "Unprocessed Patterns" in present
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        sig = kp.load(path, scan_group_names=group, processed=not use_raw, lazy=lazy)
    dset = f"{group}/EBSD/Data/{'Unprocessed' if use_raw else 'Processed'} Patterns"
    scan = _from_signal(sig, info, path, dset)
    if not use_raw:
        scan.warnings.append("Using processed patterns (raw/unprocessed patterns not present).")
    with h5py.File(path, "r") as h:
        hdr = h[f"{group}/EBSD/Header"]
        scan.metadata["beam_voltage_kV"] = _h5_scalar(hdr.get("Beam Voltage"))
        scan.metadata["camera_mode"] = _h5_scalar(hdr.get("Camera Binning Mode", hdr.get("Camera Mode")))
    return scan


def read_h5oina_companion(path: str | os.PathLike, scan_group: str = "1") -> dict:
    """Read detector geometry and grid from a (possibly pattern-free) H5OINA.

    Used to supply geometry to a binary ``.ebsp`` export of the same scan.
    """
    with h5py.File(path, "r") as h:
        hdr = h[f"{scan_group}/EBSD/Header"]
        data = h[f"{scan_group}/EBSD/Data"]
        pc = np.column_stack(
            [
                np.asarray(data["Pattern Center X"][()], dtype=float).ravel(),
                np.asarray(data["Pattern Center Y"][()], dtype=float).ravel(),
                np.asarray(data["Detector Distance"][()], dtype=float).ravel(),
            ]
        )
        geom = {
            "pc": pc.mean(axis=0) if pc.shape[0] > 1 else pc[0],
            "pc_convention": "oxford",
            "sample_tilt": float(np.rad2deg(_h5_scalar(hdr.get("Tilt Angle"), np.deg2rad(70)))),
            "nav_shape": (int(_h5_scalar(hdr["Y Cells"])), int(_h5_scalar(hdr["X Cells"]))),
            "step": (float(_h5_scalar(hdr.get("Y Step"), 1.0)), float(_h5_scalar(hdr.get("X Step"), 1.0))),
        }
    return geom


def _read_ebsp(path: Path, info: FormatInfo, lazy: bool, companion: str | None):
    import kikuchipy as kp

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        sig = kp.load(path, lazy=lazy)
    scan = _from_signal(sig, info, path, None)
    scan.geometry_source = GEOMETRY_MISSING
    if companion:
        scan.metadata["companion"] = str(companion)
    return scan


# ----------------------------------------------------------------- EDAX/TSL


def _read_edax_h5(path: Path, info: FormatInfo, scan_group: str | None, lazy: bool) -> ScanData:
    group = scan_group or next(iter(info.pattern_datasets))
    h = h5py.File(path, "r")
    try:
        hdr = h[f"{group}/EBSD/Header"]
        data = h[f"{group}/EBSD/Data"]
        grid_type_raw = str(_h5_scalar(hdr.get("Grid Type"), "SqrGrid"))
        nrows = int(_h5_scalar(hdr["nRows"]))
        ncols = int(_h5_scalar(hdr["nColumns"]))
        dx = float(_h5_scalar(hdr.get("Step X"), 1.0))
        dy = float(_h5_scalar(hdr.get("Step Y"), 1.0))
        sy = int(_h5_scalar(hdr["Pattern Height"]))
        sx = int(_h5_scalar(hdr["Pattern Width"]))
        if grid_type_raw.lower().startswith("hex"):
            grid = GridInfo(GRID_HEXAGONAL, nrows, ncols, dx, dx * np.sqrt(3) / 2)
        elif grid_type_raw.lower().startswith("sqr"):
            grid = GridInfo(GRID_SQUARE, nrows, ncols, dx, dy)
        else:
            raise UnsupportedFormatError(f"{path.name}: unknown grid type {grid_type_raw!r}")
        dset = data["Pattern"]
        n = grid.n_points
        if dset.shape[0] < n or tuple(dset.shape[-2:]) != (sy, sx):
            raise UnsupportedFormatError(
                f"{path.name}: Pattern dataset shape {dset.shape} does not match header "
                f"({n} points of {sy}x{sx})."
            )
        if lazy:
            import dask.array as da

            patterns = da.from_array(dset, chunks=(max(1, min(n, 256)), sy, sx))[:n]
        else:
            patterns = np.asarray(dset[:n])
        if "X Position" in data and "Y Position" in data:
            x = np.asarray(data["X Position"][:n], dtype=float)
            y = np.asarray(data["Y Position"][:n], dtype=float)
            coord_src = "file"
        else:
            x, y = grid_coordinates(grid)
            coord_src = "nominal grid"
        # EDAX "Valid" flags the vendor indexing result, not pattern presence; all
        # stored patterns are treated as present.
        valid = np.ones(n, dtype=bool)
        pcg = hdr.get("Pattern Center Calibration")
        pc_tsl = (
            float(_h5_scalar(pcg.get("x-star"), 0.0)) if pcg else 0.0,
            float(_h5_scalar(pcg.get("y-star"), 0.0)) if pcg else 0.0,
            float(_h5_scalar(pcg.get("z-star"), 0.0)) if pcg else 0.0,
        )
        azimuthal = -float(_h5_scalar(hdr.get("Camera Azimuthal Angle"), 0.0)) or 0.0
        det = _detector(
            shape=(sy, sx),
            px_size=1.0,
            tilt=float(_h5_scalar(hdr.get("Camera Elevation Angle"), 0.0)),
            azimuthal=azimuthal,
            sample_tilt=float(_h5_scalar(hdr.get("Sample Tilt"), 70.0)),
            pc=pc_tsl,
            convention="tsl",
        )
        vendor_euler = None
        if all(k in data for k in ("Phi1", "Phi", "Phi2")):
            e = np.column_stack([np.asarray(data[k][:n], dtype=float) for k in ("Phi1", "Phi", "Phi2")])
            vendor_euler = np.rad2deg(e)
        vendor_phase = np.asarray(data["Phase"][:n]) if "Phase" in data else None
        md = {
            "format": info.to_dict(),
            "grid_type_raw": grid_type_raw,
            "coordinates_source": coord_src,
            "pc_tsl_raw": list(pc_tsl),
            "working_distance": _h5_scalar(hdr.get("Working Distance")),
        }
    finally:
        if not lazy:
            h.close()
    scan = ScanData(
        patterns=patterns,
        grid=grid,
        detector=det,
        x=x,
        y=y,
        valid=valid,
        vendor=info.vendor,
        file_format=info.file_format,
        metadata=md,
        warnings=list(info.notes),
        vendor_euler_deg=vendor_euler,
        vendor_phase=vendor_phase,
        source_path=str(path),
        dataset_path=f"{group}/EBSD/Data/Pattern",
    )
    if not _pc_is_plausible(det.pc):
        scan.geometry_source = GEOMETRY_MISSING
    return scan


def read_up_header(path: str | os.PathLike) -> dict:
    p = Path(path)
    with open(p, "rb") as f:
        head = f.read(42)
    version, sx, sy, offset = struct.unpack("<4I", head[:16])
    out = {"version": version, "sx": sx, "sy": sy, "offset": offset, "nx": None, "ny": None,
           "is_hex": False, "dx": None, "dy": None}
    if version >= 3:
        nx, ny = struct.unpack("<2I", head[17:25])
        out.update(nx=nx, ny=ny, is_hex=bool(head[25]))
        dx, dy = struct.unpack("<2d", head[26:42])
        out.update(dx=dx, dy=dy)
    nbytes = 1 if p.suffix.lower() == ".up1" else 2
    out["n_patterns"] = (p.stat().st_size - offset) // (sx * sy * nbytes)
    out["dtype"] = "uint8" if nbytes == 1 else "uint16"
    return out


def _read_up(path: Path, info: FormatInfo, nav_shape, step, grid_type: str | None) -> ScanData:
    hdr = read_up_header(path)
    n = int(hdr["n_patterns"])
    sy, sx = hdr["sy"], hdr["sx"]
    mm = np.memmap(path, dtype=hdr["dtype"], mode="r", offset=hdr["offset"], shape=(n, sy, sx))
    is_hex = hdr["is_hex"] if grid_type is None else grid_type == GRID_HEXAGONAL
    if grid_type == GRID_POINTS:
        nav_shape = (1, n)
        is_hex = False
    if nav_shape is not None:
        nrows, ncols = (int(v) for v in nav_shape)
    elif hdr["nx"] and hdr["ny"]:
        nrows, ncols = hdr["ny"], hdr["nx"]
    else:
        raise MissingMetadataError(
            f"{path.name} (UP version {hdr['version']}) does not store map dimensions.",
            "Supply nav_shape=(rows, cols) and the step size, e.g. "
            "`kwb inspect file.up1 --nav-shape 3 3 --step 1.5`.",
        )
    if step is not None:
        dy, dx = (float(step), float(step)) if np.isscalar(step) else (float(step[0]), float(step[1]))
    else:
        dx = float(hdr["dx"] or 1.0)
        dy = float(hdr["dy"] or dx)
    if is_hex:
        grid = GridInfo(GRID_HEXAGONAL, nrows, ncols, dx, dx * np.sqrt(3) / 2)
    elif grid_type == GRID_POINTS:
        grid = GridInfo(GRID_POINTS, 1, n, dx, dy)
    else:
        grid = GridInfo(GRID_SQUARE, nrows, ncols, dx, dy)
    if grid.n_points != n:
        raise MissingMetadataError(
            f"{path.name}: {n} patterns in file but grid {nrows}x{ncols} "
            f"({grid.grid_type}) implies {grid.n_points}.",
            "Check nav_shape and the grid type (square/hexagonal) used during acquisition. "
            "Hexagonal grids assume ncols_even = ncols_odd - 1 (EDAX OIM). Use "
            "grid_type='points' to read the patterns as an unordered list.",
        )
    x, y = grid_coordinates(grid)
    det = _detector(shape=(sy, sx), pc=(0.5, 0.5, 0.5))
    scan = ScanData(
        patterns=mm,
        grid=grid,
        detector=det,
        x=x,
        y=y,
        valid=np.ones(n, dtype=bool),
        vendor=info.vendor,
        file_format=info.file_format,
        geometry_source=GEOMETRY_MISSING,
        metadata={"format": info.to_dict(), "up_header": {k: v for k, v in hdr.items()}},
        warnings=list(info.notes),
        source_path=str(path),
    )
    return scan


# ----------------------------------------------------------------- EMsoft and fixtures


def _read_emsoft(path: Path, info: FormatInfo, lazy: bool) -> ScanData:
    import kikuchipy as kp

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        sig = kp.load(path, lazy=lazy)
    scan = _from_signal(sig, info, path, "EMData/EBSD/EBSDPatterns")
    scan.grid.grid_type = GRID_POINTS if scan.grid.nrows == 1 else scan.grid.grid_type
    if sig.xmap is not None:
        scan.vendor_euler_deg = np.rad2deg(sig.xmap.rotations.to_euler())
    return scan


def write_fixture(path: str | os.PathLike, scan: ScanData, truth: dict | None = None,
                  provenance: dict | None = None) -> Path:
    """Write a scan (and optional ground truth) in the project fixture format."""
    p = Path(path)
    det = scan.detector
    with h5py.File(p, "w") as h:
        h.attrs["kwb_format"] = FIXTURE_FORMAT_NAME
        h.attrs["kwb_format_version"] = "1"
        h.create_dataset("patterns", data=scan.get_patterns(0, scan.n_points, dtype=scan.dtype),
                         compression="gzip", compression_opts=4,
                         chunks=(1,) + scan.pattern_shape)
        h["x"], h["y"], h["valid"] = scan.x, scan.y, scan.valid.astype(np.uint8)
        g = h.create_group("grid")
        for k, v in scan.grid.to_dict().items():
            if k != "n_points":
                g.attrs[k] = v
        d = h.create_group("detector")
        d["pc_bruker"] = np.asarray(det.pc, dtype=float).reshape(-1, 3)
        for k in ("binning", "px_size", "sample_tilt", "tilt", "azimuthal", "twist"):
            d.attrs[k] = float(getattr(det, k))
        d.attrs["shape"] = list(det.shape)
        d.attrs["geometry_source"] = scan.geometry_source
        if truth:
            t = h.create_group("truth")
            for k, v in truth.items():
                if isinstance(v, (list, tuple)) and v and isinstance(v[0], str):
                    t.attrs[k] = json.dumps(list(v))
                else:
                    t[k] = np.asarray(v)
        h.attrs["provenance"] = json.dumps(provenance or {})
        h.attrs["metadata"] = json.dumps({k: v for k, v in scan.metadata.items()
                                          if not k.startswith("_") and not isinstance(v, np.ndarray)}, default=str)
    return p


def read_fixture_truth(path: str | os.PathLike) -> dict:
    out: dict = {}
    with h5py.File(path, "r") as h:
        if "truth" not in h:
            return out
        t = h["truth"]
        for k, v in t.items():
            out[k] = v[()]
        for k, v in t.attrs.items():
            out[k] = json.loads(v)
        out["provenance"] = json.loads(h.attrs.get("provenance", "{}"))
    return out


def _read_fixture(path: Path, info: FormatInfo) -> ScanData:
    with h5py.File(path, "r") as h:
        patterns = h["patterns"][()]
        g = dict(h["grid"].attrs)
        grid = GridInfo(str(g["grid_type"]), int(g["nrows"]), int(g["ncols"]), float(g["step_x"]),
                        float(g["step_y"]), str(g.get("unit", "um")))
        d = h["detector"]
        pc = d["pc_bruker"][()]
        det = _detector(
            shape=tuple(int(v) for v in d.attrs["shape"]),
            pc=pc[0] if pc.shape[0] == 1 else pc,
            binning=int(d.attrs["binning"]),
            px_size=float(d.attrs["px_size"]),
            sample_tilt=float(d.attrs["sample_tilt"]),
            tilt=float(d.attrs["tilt"]),
            azimuthal=float(d.attrs["azimuthal"]),
            twist=float(d.attrs["twist"]),
        )
        scan = ScanData(
            patterns=patterns, grid=grid, detector=det, x=h["x"][()], y=h["y"][()],
            valid=h["valid"][()].astype(bool), vendor=info.vendor, file_format=info.file_format,
            geometry_source=str(d.attrs.get("geometry_source", GEOMETRY_FROM_FILE)),
            metadata={"format": info.to_dict(), "provenance": json.loads(h.attrs.get("provenance", "{}"))},
            source_path=str(path), dataset_path="patterns",
        )
    return scan


# ----------------------------------------------------------------- entry point


def load_scan(
    path: str | os.PathLike,
    *,
    scan_group: str | None = None,
    prefer_raw: bool = True,
    lazy: bool = False,
    nav_shape: tuple[int, int] | None = None,
    step: float | tuple[float, float] | None = None,
    grid_type: str | None = None,
    geometry: dict | None = None,
    companion: str | os.PathLike | None = None,
) -> ScanData:
    """Load a pattern-bearing scan from any supported format.

    Parameters
    ----------
    geometry
        Optional user-supplied detector geometry overriding the file:
        ``pc`` (3,) or (N, 3), ``pc_convention`` (bruker/tsl/oxford/emsoft),
        ``binning``, ``px_size`` (unbinned, µm), ``sample_tilt``, ``tilt``,
        ``azimuthal``, ``twist`` (degrees).
    companion
        H5OINA file providing geometry for a binary ``.ebsp`` export.
    """
    p = Path(path)
    info = detect_format(p)
    fmt = info.file_format
    if fmt == "oxford_h5oina":
        scan = _read_h5oina(p, info, scan_group, prefer_raw, lazy)
    elif fmt == "oxford_ebsp":
        scan = _read_ebsp(p, info, lazy, str(companion) if companion else None)
        if companion:
            comp = read_h5oina_companion(companion)
            geometry = {**{k: comp[k] for k in ("pc", "pc_convention", "sample_tilt")}, **(geometry or {})}
    elif fmt == "edax_h5ebsd":
        scan = _read_edax_h5(p, info, scan_group, lazy)
    elif fmt in ("edax_up1", "edax_up2"):
        scan = _read_up(p, info, nav_shape, step, grid_type)
    elif fmt == "emsoft_ebsd":
        scan = _read_emsoft(p, info, lazy)
    elif fmt == "kwb_fixture":
        scan = _read_fixture(p, info)
    elif fmt == "kikuchipy_h5ebsd":
        import kikuchipy as kp

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            sig = kp.load(p, lazy=lazy)
        scan = _from_signal(sig, info, p, None)
    else:
        raise UnsupportedFormatError(f"{p.name}: format {fmt} is detected but not yet supported.")
    if nav_shape is not None and fmt not in ("edax_up1", "edax_up2"):
        nrows, ncols = (int(v) for v in nav_shape)
        if nrows * ncols != scan.n_points:
            raise MissingMetadataError(
                f"nav_shape {nav_shape} does not match {scan.n_points} patterns in {p.name}."
            )
        dy, dx = (step, step) if step is None or np.isscalar(step) else step
        scan.grid = GridInfo(GRID_SQUARE, nrows, ncols, float(dx or scan.grid.step_x),
                             float(dy or scan.grid.step_y))
        scan.x, scan.y = grid_coordinates(scan.grid)
    return _apply_user_geometry(scan, geometry)
