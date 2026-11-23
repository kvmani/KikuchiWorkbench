"""Mock EMEBSDmaster: requires the MC file, appends a (kinematical) master in EMsoft layout."""

import sys
from pathlib import Path

import _common
import h5py
import numpy as np

from kikuchiworkbench.crystal.xtal import crystal_model_from_group
from kikuchiworkbench.emsoft.jobs import parse_namelist
from kikuchiworkbench.masters.kinematical import simulate_kinematical_master

nml = parse_namelist(Path(sys.argv[1]).read_text())
_common.maybe_fail("master")
f = _common.resolve(nml["energyfile"])
with h5py.File(f, "r") as h:
    assert "EMData/MCOpenCL" in h
    model = crystal_model_from_group(h["CrystalData"], "mock")
    ekev = float(h["NMLparameters/MCCLNameList/EkeV"][0])
    sig = float(h["NMLparameters/MCCLNameList/sig"][0])
tmp = f.with_name("mock_master_tmp.h5")
simulate_kinematical_master(model, tmp, voltage_kV=ekev, half_size=min(int(nml["npx"]), 40),
                            sample_tilt_deg=sig)
with h5py.File(tmp, "r") as src, h5py.File(f, "a") as h:
    src.copy("EMData/EBSDmaster", h["EMData"])
    h["EMheader/EBSDmaster/ProgramName"] = np.array([b"EMEBSDmaster.f90"])
    h["EMheader/EBSDmaster/Version"] = np.array([b"mock_5_0"])
    em = h.create_group("NMLparameters/EBSDMasterNameList")
    em["npx"] = np.array([nml["npx"]])
tmp.unlink()
print("mock EMEBSDmaster done")
