"""Import and verify EMsoft EBSD master-pattern HDF5 files.

A master is only accepted when its projection, hemispheres, energy bins and
crystal data are consistent. The returned :class:`MasterInfo` records the
provenance stored in the file (personal fields such as user e-mail are
dropped) and the checksum of the file.
"""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field
from pathlib import Path

import h5py
import numpy as np

from ..crystal.xtal import crystal_model_from_group
from ..errors import MasterPatternError
from ..provenance import sha256_file

_PRIVATE_KEYS = {"UserEmail", "UserName", "UserLocation", "HostName", "Creator"}

ENERGY_MODES = ("max", "weighted")


@dataclass
class MasterInfo:
    path: str
    sha256: str
    phase_name: str
    space_group: int
    point_group: str
    crystal_system: int | None
    lattice_nm_deg: list[float]
    atom_types: list[int]
    energies_keV: list[float]
    npx: int
    projection: str
    hemispheres: list[str]
    dtype: str
    program: str | None
    emsoft_version: str | None
    sample_tilt_deg: float | None
    beam_energy_keV: float | None
    mc_mode: str | None
    total_electrons: int | None
    energy_weighting_available: bool
    nml: dict = field(default_factory=dict)
    checks: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    def cache_key_fields(self) -> dict:
        """Fields identifying the physics of this master (for cache keys)."""
        return {
            "sha256": self.sha256,
            "space_group": self.space_group,
            "lattice_nm_deg": [round(v, 6) for v in self.lattice_nm_deg],
            "energies_keV": self.energies_keV,
            "npx": self.npx,
            "sample_tilt_deg": self.sample_tilt_deg,
        }


def _val(obj, default=None):
    if obj is None:
        return default
    v = obj[()]
    if isinstance(v, np.ndarray):
        if v.dtype.kind == "O":
            return [x.decode(errors="replace") if isinstance(x, bytes) else x for x in v.ravel()]
        if v.size == 1:
            v = v.ravel()[0]
        else:
            return v.tolist()
    if isinstance(v, bytes):
        v = v.decode(errors="replace").strip().rstrip("\x00")
    if isinstance(v, np.generic):
        v = v.item()
    return v


def _group_to_dict(g: h5py.Group) -> dict:
    out = {}
    for k, v in g.items():
        if k in _PRIVATE_KEYS:
            continue
        if isinstance(v, h5py.Group):
            out[k] = _group_to_dict(v)
        elif v.size <= 64:
            out[k] = _val(v)
    return out


def inspect_master(path: str | os.PathLike) -> MasterInfo:
    """Verify an EMsoft master-pattern file without loading the full arrays."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(p)
    checks: list[str] = []
    warns: list[str] = []
    try:
        h = h5py.File(p, "r")
    except OSError as e:
        raise MasterPatternError(f"{p.name} is not a readable HDF5 file: {e}") from e
    with h:
        if "EMData" not in h or "EBSDmaster" not in h["EMData"]:
            raise MasterPatternError(
                f"{p.name} has no EMData/EBSDmaster group; it is not an EMsoft EBSD master.",
                "Run EMEBSDmaster on the Monte Carlo output, or select the master HDF5 (not the "
                "Monte Carlo-only file or a scan).",
            )
        mg = h["EMData/EBSDmaster"]
        for name in ("mLPNH", "EkeVs"):
            if name not in mg:
                raise MasterPatternError(f"{p.name}: required dataset EBSDmaster/{name} missing.")
        nh = mg["mLPNH"]
        hemispheres = ["north"]
        if "mLPSH" in mg:
            hemispheres.append("south")
            if mg["mLPSH"].shape != nh.shape:
                raise MasterPatternError(f"{p.name}: mLPNH and mLPSH shapes differ.")
        master_dtype = str(nh.dtype)
        shape = nh.shape  # (numset, nE, 2npx+1, 2npx+1) or (nE, 2npx+1, 2npx+1)
        if shape[-1] != shape[-2] or shape[-1] % 2 != 1:
            raise MasterPatternError(f"{p.name}: Lambert master must be square with odd size, got {shape}.")
        npx = (shape[-1] - 1) // 2
        energies = np.atleast_1d(np.asarray(mg["EkeVs"][()], dtype=float))
        n_e = shape[-3]
        if energies.size != n_e:
            raise MasterPatternError(
                f"{p.name}: {energies.size} energies in EkeVs but {n_e} energy bins in mLPNH."
            )
        if energies.size > 1 and not np.all(np.diff(energies) > 0):
            raise MasterPatternError(f"{p.name}: EkeVs are not strictly increasing: {energies}.")
        checks.append(f"Lambert projection, {len(hemispheres)} hemisphere(s), {n_e} energy bin(s)")

        # Sample a slice to check content is finite and non-constant
        # Check the highest-energy slice of the first set (the one used by default)
        if len(shape) == 4:
            sl = nh[0, n_e - 1]
        elif len(shape) == 3:
            sl = nh[n_e - 1]
        else:
            sl = nh[()]
        sl = np.asarray(sl, dtype=float)
        if not np.all(np.isfinite(sl)):
            raise MasterPatternError(f"{p.name}: master contains non-finite values.")
        if np.ptp(sl) <= 0:
            raise MasterPatternError(f"{p.name}: master slice is constant (failed simulation?).")
        checks.append("finite, non-constant intensities")

        if "CrystalData" not in h:
            raise MasterPatternError(f"{p.name}: CrystalData group missing; phase cannot be verified.")
        cd = h["CrystalData"]
        sg = int(_val(cd.get("SpaceGroupNumber"), 0))
        if not 1 <= sg <= 230:
            raise MasterPatternError(f"{p.name}: invalid space group number {sg}.")
        lat = [float(v) for v in np.asarray(cd["LatticeParameters"][()]).ravel()]
        atom_types = [int(v) for v in np.atleast_1d(cd["Atomtypes"][()])]
        crystal_system = int(_val(cd.get("CrystalSystem"), 0)) or None
        xtalname = _val(mg.get("xtalname")) if "xtalname" in mg else None
        phase_name = Path(str(xtalname)).stem if xtalname else p.stem
        try:
            model = crystal_model_from_group(cd, phase_name, str(p))
        except Exception as e:
            raise MasterPatternError(f"{p.name}: CrystalData could not be interpreted: {e}") from e
        if not model.sites:
            warns.append("No atom sites in CrystalData/AtomData.")
        checks.append(f"space group {sg}, lattice (nm, deg) {lat}")

        hdr = h.get("EMheader/EBSDmaster")
        program = _val(hdr.get("ProgramName")) if hdr else None
        version = _val(hdr.get("Version")) if hdr else None
        mc_nml = h.get("NMLparameters/MCCLNameList")
        tilt = float(_val(mc_nml.get("sig"))) if mc_nml is not None and "sig" in mc_nml else None
        ekev = float(_val(mc_nml.get("EkeV"))) if mc_nml is not None and "EkeV" in mc_nml else None
        mcmode = _val(mc_nml.get("MCmode")) if mc_nml is not None and "MCmode" in mc_nml else None
        totnum = int(_val(mc_nml.get("totnum_el"))) if mc_nml is not None and "totnum_el" in mc_nml else None
        if tilt is None:
            warns.append("Monte Carlo sample tilt (sig) not recorded; cannot check against scan tilt.")
        if ekev is not None and abs(ekev - energies.max()) > 1.0:
            warns.append(f"Beam energy {ekev} keV differs from highest master energy {energies.max()} keV.")
        nml = _group_to_dict(h["NMLparameters"]) if "NMLparameters" in h else {}
        weighting = "EMData/MCOpenCL/accum_e" in h
        if energies.size > 1 and not weighting:
            warns.append("Multiple energies but no MC energy histogram (accum_e); only single-energy use.")

    phase = model.to_orix_phase(name=phase_name)
    pg = phase.point_group.name if phase.point_group is not None else ""
    return MasterInfo(
        path=str(p),
        sha256=sha256_file(p),
        phase_name=phase_name,
        space_group=sg,
        point_group=pg,
        crystal_system=crystal_system,
        lattice_nm_deg=lat,
        atom_types=atom_types,
        energies_keV=[float(e) for e in energies],
        npx=npx,
        projection="lambert",
        hemispheres=hemispheres,
        dtype=master_dtype,
        program=program,
        emsoft_version=version,
        sample_tilt_deg=tilt,
        beam_energy_keV=ekev,
        mc_mode=mcmode,
        total_electrons=totnum,
        energy_weighting_available=weighting,
        nml=nml,
        checks=checks,
        warnings=warns,
    )


def energy_weights(path: str | os.PathLike) -> np.ndarray | None:
    """Global energy weights from the MC energy histogram (spatially summed).

    This approximates EMsoft's position-dependent weighting by a single
    weight per energy bin; the approximation is recorded when used.
    """
    with h5py.File(path, "r") as h:
        if "EMData/MCOpenCL/accum_e" not in h:
            return None
        acc = np.asarray(h["EMData/MCOpenCL/accum_e"][()], dtype=float)
    # accum_e is stored (numsx, numsx, nE) in this HDF5 layout
    w = acc.reshape(-1, acc.shape[-1]).sum(axis=0)
    if w.sum() <= 0:
        return None
    return w / w.sum()


@dataclass
class LoadedMaster:
    signal: object  # kikuchipy EBSDMasterPattern, Lambert, both hemispheres, single energy
    info: MasterInfo
    energy_mode: str
    energy_keV: float | None
    weights: list[float] | None = None

    @property
    def phase(self):
        return self.signal.phase

    def describe(self) -> dict:
        d = {
            "phase_name": self.info.phase_name,
            "sha256": self.info.sha256,
            "path": self.info.path,
            "space_group": self.info.space_group,
            "energy_mode": self.energy_mode,
            "energy_keV": self.energy_keV,
            "energy_weights": self.weights,
        }
        if self.energy_mode == "weighted":
            d["energy_weighting_note"] = (
                "global weights from spatially summed MC histogram (approximation of EMsoft "
                "position-dependent weighting)"
            )
        return d


def _read_lambert(path, info: MasterInfo) -> np.ndarray:
    """Return Lambert data as (hemisphere, energy, rows, cols) float32."""
    with h5py.File(path, "r") as h:
        mg = h["EMData/EBSDmaster"]
        arrs = []
        for name in ("mLPNH", "mLPSH")[: len(info.hemispheres)]:
            a = np.asarray(mg[name][()], dtype=np.float32)
            if a.ndim == 4:
                a = a[0]  # first set (numset)
            if a.ndim == 2:
                a = a[None]
            arrs.append(a)
    return np.stack(arrs)


def load_master(
    path: str | os.PathLike,
    energy: str | float = "max",
    phase_name: str | None = None,
) -> LoadedMaster:
    """Load a verified master as a single-energy Lambert pattern.

    ``energy``: ``"max"`` (highest energy bin, default), a value in keV
    (nearest bin, must be within 0.5 keV), or ``"weighted"`` (MC histogram).
    Masters with only the northern hemisphere are mirrored to the south only
    for centrosymmetric Laue-equivalent use and a warning is recorded.
    """
    import kikuchipy as kp

    info = inspect_master(path)
    energies = np.asarray(info.energies_keV)
    data = _read_lambert(path, info)  # (hemi, nE, N, N)
    weights = None
    if energy == "weighted":
        w = energy_weights(path)
        if w is None or w.size != energies.size:
            raise MasterPatternError(
                f"{Path(path).name}: energy weighting requested but no compatible MC energy histogram.",
                "Use energy='max' or a specific energy in keV.",
            )
        sel = np.einsum("herc,e->hrc", data, w.astype(np.float32))
        e_val = None
        mode = "weighted"
        weights = [float(v) for v in w]
    else:
        if energy == "max":
            idx = int(np.argmax(energies))
        else:
            target = float(energy)
            idx = int(np.argmin(np.abs(energies - target)))
            if abs(energies[idx] - target) > 0.5:
                raise MasterPatternError(
                    f"Requested energy {target} keV not available; master energies are {list(energies)}."
                )
        e_val = float(energies[idx])
        mode = "single"
        sel = data[:, idx]
    if sel.shape[0] == 1:
        sel = np.concatenate([sel, sel], axis=0)
        info.warnings.append("Only the northern hemisphere is stored; it is reused for the south.")
    with h5py.File(path, "r") as h:
        model = crystal_model_from_group(h["CrystalData"], phase_name or info.phase_name, str(path))
    phase = model.to_orix_phase(name=phase_name or info.phase_name)
    if phase_name:
        info.phase_name = phase_name
    sig = kp.signals.EBSDMasterPattern(sel, phase=phase, hemisphere="both", projection="lambert")
    return LoadedMaster(sig, info, mode, e_val, weights)
