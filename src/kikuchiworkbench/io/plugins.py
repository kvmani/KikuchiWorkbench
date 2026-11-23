"""Reader plug-ins: add scan formats without changing the core.

A plug-in provides a ``name``, a ``vendor``, ``detect(path) -> bool`` (structural check, cheap) and
``load(path, info, **kwargs) -> ScanData``. Plug-ins are found from

* the Python entry-point group ``kikuchiworkbench.readers`` (third-party packages), and
* :func:`register_reader` (built-ins below, tests, scripts).

Built-in plug-ins: NORDIF (``Pattern.dat`` + ``Setting.txt``) and Bruker h5ebsd, both read through kikuchipy.
Plug-ins are consulted after the built-in Oxford/EDAX/EMsoft detection, so they cannot shadow those formats.
"""

from __future__ import annotations

import importlib.metadata
import warnings
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

ENTRY_POINT_GROUP = "kikuchiworkbench.readers"


@dataclass
class ReaderPlugin:
    name: str  # used as FormatInfo.file_format
    vendor: str
    detect: Callable[[Path], bool]
    load: Callable  # (path, info, **kwargs) -> ScanData
    description: str = ""


_REGISTRY: dict[str, ReaderPlugin] = {}
_ENTRY_POINTS_LOADED = False


def register_reader(plugin: ReaderPlugin, replace: bool = False) -> None:
    if plugin.name in _REGISTRY and not replace:
        raise ValueError(f"Reader plug-in {plugin.name!r} is already registered")
    _REGISTRY[plugin.name] = plugin


def unregister_reader(name: str) -> None:
    _REGISTRY.pop(name, None)


def _load_entry_points() -> None:
    global _ENTRY_POINTS_LOADED
    if _ENTRY_POINTS_LOADED:
        return
    _ENTRY_POINTS_LOADED = True
    try:
        eps = importlib.metadata.entry_points(group=ENTRY_POINT_GROUP)
    except TypeError:  # pragma: no cover - very old importlib.metadata
        eps = importlib.metadata.entry_points().get(ENTRY_POINT_GROUP, [])
    for ep in eps:
        try:
            obj = ep.load()
            plugin = obj() if callable(obj) and not isinstance(obj, ReaderPlugin) else obj
            if isinstance(plugin, ReaderPlugin) and plugin.name not in _REGISTRY:
                register_reader(plugin)
        except Exception as e:  # a broken third-party plug-in must not break the core readers
            warnings.warn(f"Reader plug-in {ep.name!r} failed to load: {e}", stacklevel=2)


def readers() -> list[ReaderPlugin]:
    _load_entry_points()
    return list(_REGISTRY.values())


def get_reader(name: str) -> ReaderPlugin | None:
    _load_entry_points()
    return _REGISTRY.get(name)


def find_reader(path: Path) -> ReaderPlugin | None:
    for plugin in readers():
        try:
            if plugin.detect(path):
                return plugin
        except Exception:
            continue
    return None


# ---------------------------------------------------------------- built-in plug-ins


def _kp_load(path, info, **kwargs):
    import kikuchipy as kp

    from .readers import _from_signal

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        sig = kp.load(path, lazy=kwargs.get("lazy", False))
    scan = _from_signal(sig, info, Path(path), None)
    return scan


def _detect_nordif(p: Path) -> bool:
    return p.suffix.lower() == ".dat" and (p.parent / "Setting.txt").exists()


def _load_nordif(path, info, **kwargs):
    scan = _kp_load(path, info, **kwargs)
    scan.warnings.append("NORDIF reader via kikuchipy; detector calibration from Setting.txt is not used — "
                         "supply the PC (pc + pc_convention).")
    from .scan import GEOMETRY_MISSING

    scan.geometry_source = GEOMETRY_MISSING
    return scan


def _detect_bruker(p: Path) -> bool:
    from .detect import _top_value, is_hdf5

    if not is_hdf5(p):
        return False
    import h5py

    with h5py.File(p, "r") as h:
        man = _top_value(h, "Manufacturer")
    return bool(man) and man.lower().startswith("bruker")


register_reader(ReaderPlugin("nordif", "NORDIF", _detect_nordif, _load_nordif,
                             "NORDIF Pattern.dat with Setting.txt (kikuchipy)"))
register_reader(ReaderPlugin("bruker_h5ebsd", "Bruker Nano", _detect_bruker, _kp_load,
                             "Bruker ESPRIT h5ebsd with RawPatterns (kikuchipy); unverified on real exports"))
