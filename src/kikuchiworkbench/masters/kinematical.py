"""Kinematical master patterns for offline synthetic fixtures.

These are computed with kikuchipy's ``KikuchiPatternSimulator`` (kinematical
theory: band positions and widths from Bragg angles, intensities from
structure factors). They are **not** dynamical EMsoft masters and are labelled
as such in the file (``EMheader/EBSDmaster/ProgramName``) and in every
manifest. They let the synthetic Ni/Cu discrimination exercise and the CPU
demo run without EMsoft or OpenCL.

Files are written in the EMsoft master HDF5 layout so the same import and
verification path is used for kinematical and dynamical masters.
"""

from __future__ import annotations

import os
import warnings
from pathlib import Path

import h5py
import numpy as np

from .. import __version__
from ..crystal.cif import CrystalModel
from ..crystal.xtal import write_crystal_group

KINEMATICAL_PROGRAM = "KikuchiWorkbench kinematical (NOT dynamical EMsoft)"


def simulate_kinematical_master(
    model: CrystalModel,
    out_path: str | os.PathLike,
    voltage_kV: float = 20.0,
    dmin_A: float = 0.8,
    half_size: int = 200,
    sample_tilt_deg: float = 70.0,
    intensity_fraction: float = 1e-3,
    phase_name: str | None = None,
) -> Path:
    """Compute a kinematical Lambert master (both hemispheres) and write it."""
    import kikuchipy as kp
    from diffsims.crystallography import ReciprocalLatticeVector

    phase = model.to_orix_phase(name=phase_name or model.name)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        ref = ReciprocalLatticeVector.from_min_dspacing(phase, dmin_A)
        ref.sanitise_phase()
        ref.calculate_structure_factor()
        f = np.abs(ref.structure_factor)
        ref = ref[f > intensity_fraction * f.max()]
        ref.calculate_theta(voltage_kV * 1e3)
        sim = kp.simulations.KikuchiPatternSimulator(ref)
        mp = sim.calculate_master_pattern(
            half_size=half_size, hemisphere="both", scaling="linear"
        )
        lam = mp.as_lambert(show_progressbar=False)
    data = np.asarray(lam.data, dtype=np.float32)  # (2, N, N)
    p = Path(out_path)
    tmp = p.with_suffix(p.suffix + ".tmp")
    with h5py.File(tmp, "w") as h:
        write_crystal_group(h.create_group("CrystalData"), model)
        m = h.create_group("EMData/EBSDmaster")
        m["mLPNH"] = data[0][None, None]
        m["mLPSH"] = data[1][None, None]
        m["EkeVs"] = np.array([voltage_kV], dtype=np.float32)
        m["numEbins"] = np.array([1], dtype=np.int32)
        m["numset"] = np.array([1], dtype=np.int32)
        m["xtalname"] = np.array([f"{model.name}.xtal".encode()])
        hdr = h.create_group("EMheader/EBSDmaster")
        hdr["ProgramName"] = np.array([KINEMATICAL_PROGRAM.encode()])
        hdr["Version"] = np.array([f"kikuchiworkbench {__version__}; kikuchipy {kp.__version__}".encode()])
        nml = h.create_group("NMLparameters")
        mc = nml.create_group("MCCLNameList")
        mc["sig"] = np.array([sample_tilt_deg])
        mc["EkeV"] = np.array([voltage_kV])
        mc["MCmode"] = np.array([b"none (kinematical)"])
        em = nml.create_group("EBSDMasterNameList")
        em["npx"] = np.array([half_size], dtype=np.int32)
        em["dmin"] = np.array([dmin_A / 10.0])  # nm, as in EMsoft
        em["latgridtype"] = np.array([b"Lambert"])
        em["kinematical_intensity_fraction"] = np.array([intensity_fraction])
        em["n_reflectors"] = np.array([int(ref.size)], dtype=np.int32)
    os.replace(tmp, p)
    return p


def is_kinematical(program: str | None) -> bool:
    return bool(program) and "kinematical" in str(program).lower()
