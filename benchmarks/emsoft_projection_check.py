"""Check our master import + PC conversion + rotation convention against EMsoft's own detector projection.

Reference: kikuchipy's packaged `EBSD_TEST_Ni.h5` (EMsoft 4.2 EMEBSD, 640x480 px, xpc=ypc=20 px, L=15000 um,
delta=50 um, detector tilt 10 deg, Euler (TSL) = (120, 45, 60) deg). Master: EMsoft dynamical Ni master
(Zenodo 7498645, 20 keV slice; an independent run of the same physics) or, offline, kikuchipy's small Ni master.

Prints NCC for the documented convention and for deliberately wrong alternatives (xpc sign, vertical mirror,
transpose, phi1 + 90 deg). The documented convention must give the highest NCC by a clear gap.

    python benchmarks/emsoft_projection_check.py [--master ~/kwb_data/ni_master/ni_mc_mp_20kv.h5]
"""

import argparse
import json
import os
import warnings

import h5py
import numpy as np


def reference(path=None):
    import kikuchipy as kp

    path = path or os.path.join(os.path.dirname(kp.__file__), "data", "emsoft_ebsd", "EBSD_TEST_Ni.h5")
    with h5py.File(path, "r") as h:
        pat = np.asarray(h["EMData/EBSD/EBSDPatterns"][0], dtype=np.float32)
        eul = np.asarray(h["EMData/EBSD/EulerAngles"][0], dtype=float)
        nml = {k: v[()] for k, v in h["NMLparameters/EBSDNameList"].items()}
        version = h["EMheader/EBSD/Version"][0].decode()
    g = lambda k: float(np.ravel(nml[k])[0])  # noqa: E731
    return pat, eul, {"xpc": g("xpc"), "ypc": g("ypc"), "L": g("L"), "delta": g("delta"),
                      "thetac": g("thetac"), "numsx": int(g("numsx")), "numsy": int(g("numsy")),
                      "binning": int(g("binning")), "emsoft_version": version}


def ncc(a, b):
    a = (a - a.mean()) / (a.std() + 1e-12)
    b = (b - b.mean()) / (b.std() + 1e-12)
    return float((a * b).mean())


def run(master_path=None, sample_tilt=70.0) -> dict:
    from kikuchipy.detectors import EBSDDetector
    from orix.quaternion import Rotation

    from kikuchiworkbench.conventions import DetectorShape, to_bruker
    from kikuchiworkbench.masters.importer import load_master

    if master_path is None:
        from kikuchiworkbench.demo import bundled_ni_master

        master_path = bundled_ni_master()
    m = load_master(master_path, energy=20.0)
    pat, eul, g = reference()
    shape = DetectorShape(g["numsy"], g["numsx"], g["binning"])
    conv = "emsoft4" if g["emsoft_version"].startswith("4") else "emsoft"

    def project(pc_conv, euler, flip=None):
        pc = to_bruker([g["xpc"], g["ypc"], g["L"]], pc_conv, shape, px_size=g["delta"])
        det = EBSDDetector(shape=(g["numsy"], g["numsx"]), pc=pc, px_size=g["delta"], binning=g["binning"],
                           tilt=g["thetac"], sample_tilt=sample_tilt)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            sim = m.signal.get_patterns(Rotation.from_euler(euler), det, compute=True, show_progressbar=False)
        x = np.asarray(sim.data, dtype=np.float32).reshape(g["numsy"], g["numsx"])
        if flip == "vertical":
            x = x[::-1]
        elif flip == "horizontal":
            x = x[:, ::-1]
        return x, pc

    cases = {}
    x, pc = project(conv, eul)
    cases["documented"] = ncc(x, pat)
    other = "emsoft" if conv == "emsoft4" else "emsoft4"
    cases[f"wrong xpc sign ({other})"] = ncc(project(other, eul)[0], pat)
    cases["vertical mirror"] = ncc(project(conv, eul, "vertical")[0], pat)
    cases["horizontal mirror"] = ncc(project(conv, eul, "horizontal")[0], pat)
    cases["phi1 + 90 deg (HKL vs TSL)"] = ncc(project(conv, eul + [np.pi / 2, 0, 0])[0], pat)
    cases["phi1 <-> phi2 swapped"] = ncc(project(conv, eul[[2, 1, 0]])[0], pat)
    best_wrong = max(v for k, v in cases.items() if k != "documented")
    return {"reference": {**g, "euler_deg": np.rad2deg(eul).tolist()}, "master": str(master_path),
            "pc_bruker": [float(v) for v in np.ravel(pc)], "ncc": cases,
            "gap_to_best_wrong": cases["documented"] - best_wrong,
            "passed": bool(cases["documented"] > 0.8 and cases["documented"] - best_wrong > 0.2)}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--master", default=None)
    print(json.dumps(run(ap.parse_args().master), indent=2))
