"""Write and read EMsoft crystal structure files (``.xtal``, HDF5).

Layout follows EMsoft 5 ``EMmkxtal`` output (``CrystalData`` group):

* ``LatticeParameters`` (6,) float64: a, b, c in **nm**, α, β, γ in degrees
* ``SpaceGroupNumber`` (1,) int32, ``SpaceGroupSetting`` (1,) int32 (origin choice)
* ``CrystalSystem`` (1,) int32 (EMsoft code, see ``EMSOFT_XTAL_SYSTEM``)
* ``Natomtypes`` (1,) int32, ``Atomtypes`` (n,) int32 (atomic numbers)
* ``AtomData`` (5, n) float32: x, y, z, site occupation, Debye-Waller B in **nm²**

The trigonal-in-hexagonal-axes crystal-system code and string field widths must
be confirmed against EMmkxtal output from the pinned EMsoft build (roadmap 3.7).
"""

from __future__ import annotations

import datetime as _dt
import os
from pathlib import Path

import h5py
import numpy as np

from .. import __version__
from ..errors import CrystalValidationError
from .cif import EMSOFT_XTAL_SYSTEM, CrystalModel, Site, crystal_system_of


def write_crystal_group(g: h5py.Group, model: CrystalModel) -> None:
    n = len(model.sites)
    g["LatticeParameters"] = np.asarray(model.lattice_nm_deg, dtype=np.float64)
    g["SpaceGroupNumber"] = np.array([model.space_group], dtype=np.int32)
    g["SpaceGroupSetting"] = np.array([model.setting], dtype=np.int32)
    g["CrystalSystem"] = np.array([EMSOFT_XTAL_SYSTEM[model.crystal_system]], dtype=np.int32)
    g["Natomtypes"] = np.array([n], dtype=np.int32)
    g["Atomtypes"] = np.array([s.Z for s in model.sites], dtype=np.int32)
    ad = np.zeros((5, n), dtype=np.float32)
    for i, s in enumerate(model.sites):
        ad[:, i] = [s.x, s.y, s.z, s.occupancy, s.B_iso_A2 / 100.0]  # Å² -> nm²
    g["AtomData"] = ad
    g["Source"] = np.array([f"{model.name} from {Path(model.source).name}".encode()])
    g["ProgramName"] = np.array([f"KikuchiWorkbench {__version__}".encode()])
    g["CreationDate"] = np.array([_dt.date.today().isoformat().encode()])


def write_xtal(model: CrystalModel, path: str | os.PathLike) -> Path:
    p = Path(path)
    tmp = p.with_suffix(p.suffix + ".tmp")
    with h5py.File(tmp, "w") as h:
        write_crystal_group(h.create_group("CrystalData"), model)
    os.replace(tmp, p)
    return p


def crystal_model_from_group(g: h5py.Group, name: str, source: str = "") -> CrystalModel:
    """Build a CrystalModel from an EMsoft ``CrystalData`` group."""
    from .cif import ELEMENTS

    lat = np.asarray(g["LatticeParameters"][()], dtype=float).ravel()
    sg = int(np.ravel(g["SpaceGroupNumber"][()])[0])
    setting = int(np.ravel(g["SpaceGroupSetting"][()])[0]) if "SpaceGroupSetting" in g else 1
    z = np.atleast_1d(g["Atomtypes"][()]).astype(int).ravel()
    ad = np.asarray(g["AtomData"][()], dtype=float)
    if ad.shape[0] != 5 and ad.shape[-1] == 5:
        ad = ad.T
    if ad.shape != (5, z.size):
        raise CrystalValidationError(f"{source}: AtomData shape {ad.shape} inconsistent with {z.size} atoms.")
    sites = [
        Site(f"{ELEMENTS[zi - 1]}{i + 1}", ELEMENTS[zi - 1], int(zi), float(ad[0, i]), float(ad[1, i]),
             float(ad[2, i]), float(ad[3, i]), float(ad[4, i]) * 100.0)
        for i, zi in enumerate(z)
    ]
    return CrystalModel(
        name=name, space_group=sg, hm_symbol="", setting=setting,
        crystal_system=crystal_system_of(sg), a=lat[0] * 10, b=lat[1] * 10, c=lat[2] * 10,
        alpha=lat[3], beta=lat[4], gamma=lat[5], sites=sites, source=source,
    )


def read_xtal(path: str | os.PathLike) -> CrystalModel:
    with h5py.File(path, "r") as h:
        if "CrystalData" not in h:
            raise CrystalValidationError(f"{path}: no CrystalData group.")
        return crystal_model_from_group(h["CrystalData"], Path(path).stem, str(path))
