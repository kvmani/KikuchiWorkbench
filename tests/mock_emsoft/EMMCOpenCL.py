"""Mock EMMCOpenCL: reads the namelist and the job-local EMsoftConfig, writes an MC HDF5."""

import sys
from pathlib import Path

import _common
import h5py
import numpy as np

from kikuchiworkbench.emsoft.jobs import parse_namelist

nml = parse_namelist(Path(sys.argv[1]).read_text())
_common.maybe_fail("mc")
xtal = _common.resolve(nml["xtalname"], "EMXtalFolderpathname")
out = _common.resolve(nml["dataname"])
assert xtal.exists(), xtal
n_e = int(round((nml["EkeV"] - nml["Ehistmin"]) / nml["Ebinsize"])) + 1
with h5py.File(xtal, "r") as src, h5py.File(out, "w") as h:
    src.copy("CrystalData", h)
    g = h.create_group("EMData/MCOpenCL")
    ns = min(int(nml["numsx"]), 21)
    g["accum_e"] = np.ones((ns, ns, n_e), dtype=np.int32)
    g["accum_z"] = np.ones((5, 5, 10, n_e), dtype=np.int32)
    g["numEbins"] = np.array([n_e], dtype=np.int32)
    h["EMheader/MCOpenCL/ProgramName"] = np.array([b"EMMCOpenCL.f90"])
    h["EMheader/MCOpenCL/Version"] = np.array([b"mock_5_0"])
    mc = h.create_group("NMLparameters/MCCLNameList")
    for k in ("sig", "EkeV", "Ehistmin", "Ebinsize", "totnum_el", "numsx"):
        mc[k] = np.array([nml[k]])
    mc["MCmode"] = np.array([b"CSDA"])
print("mock EMMCOpenCL done")
