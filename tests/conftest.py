import os
import struct
import warnings

import h5py
import numpy as np
import pytest

warnings.filterwarnings("ignore")


@pytest.fixture(scope="session")
def kp_data_dir():
    import kikuchipy as kp

    return os.path.join(os.path.dirname(kp.__file__), "data")


def make_h5oina(path, ny=2, nx=3, sy=20, sx=30, raw=True, processed=True, pc=(0.45, 0.62, 0.71),
                version="5.0"):
    """Write a minimal structural H5OINA file (not a real AZtec export)."""
    rng = np.random.default_rng(0)
    n = ny * nx
    with h5py.File(path, "w") as h:
        h["Manufacturer"] = "Oxford Instruments"
        h["Format Version"] = version
        g = h.create_group("1/EBSD")
        d = g.create_group("Data")
        hd = g.create_group("Header")
        if processed:
            d["Processed Patterns"] = rng.integers(0, 255, (n, sy, sx), dtype=np.uint8)
        if raw:
            # raw differs from processed so tests can tell which one was read
            d["Unprocessed Patterns"] = np.full((n, sy, sx), 7, dtype=np.uint16)
        d["Pattern Center X"] = np.full(n, pc[0], dtype=np.float32)
        d["Pattern Center Y"] = np.full(n, pc[1], dtype=np.float32)
        d["Detector Distance"] = np.full(n, pc[2], dtype=np.float32)
        d["Euler"] = np.zeros((n, 3), dtype=np.float32)
        hd["X Cells"] = np.array([nx], dtype=np.int32)
        hd["Y Cells"] = np.array([ny], dtype=np.int32)
        hd["X Step"] = np.array([0.5], dtype=np.float32)
        hd["Y Step"] = np.array([0.5], dtype=np.float32)
        hd["Pattern Width"] = np.array([sx], dtype=np.int32)
        hd["Pattern Height"] = np.array([sy], dtype=np.int32)
        hd["Beam Voltage"] = np.array([20.0], dtype=np.float32)
        hd["Tilt Angle"] = np.array([np.deg2rad(70.0)], dtype=np.float32)
        hd["Detector Orientation Euler"] = np.deg2rad(np.array([0.0, 90.0, 0.0], dtype=np.float32))
        hd["Camera Binning Mode"] = "8x8 (156x128 px)"  # binning = 1024 / 128
    return path


def make_edax_h5(path, nrows=3, ncols=4, sy=16, sx=20, grid="SqrGrid", pc=(0.48, 0.71, 0.66),
                 with_patterns=True):
    """Write a minimal structural EDAX H5EBSD file mimicking OIM key quirks."""
    if grid == "HexGrid":
        n = ((nrows + 1) // 2) * ncols + (nrows // 2) * (ncols - 1)
    else:
        n = nrows * ncols
    with h5py.File(path, "w") as h:
        h[" Manufacturer"] = np.array([b"EDAX"])
        h[" Version"] = np.array([b"OIM Analysis 8.6.0010 x64 [synthetic]"])
        s = h.create_group("Scan 1/EBSD")
        d = s.create_group("Data")
        hd = s.create_group("Header")
        if with_patterns:
            pats = np.zeros((n, sy, sx), dtype=np.uint8)
            for i in range(n):
                pats[i, 0, 0] = i  # point index encoded for order checks
            d["Pattern"] = pats
        for k in ("Phi1", "Phi", "Phi2", "CI", "IQ", "X Position", "Y Position"):
            d[k] = np.zeros(n, dtype=np.float32)
        d["Phase"] = np.zeros(n, dtype=np.int8)
        hd["Grid Type"] = np.array([grid.encode()])
        hd["nRows"] = np.array([nrows], dtype=np.int32)
        hd["nColumns"] = np.array([ncols], dtype=np.int32)
        hd["Step X"] = np.array([2.0], dtype=np.float32)
        hd["Step Y"] = np.array([2.0 if grid == "SqrGrid" else np.sqrt(3)], dtype=np.float32)
        hd["Pattern Width"] = np.array([sx], dtype=np.int32)
        hd["Pattern Height"] = np.array([sy], dtype=np.int32)
        hd["Sample Tilt"] = np.array([70.0], dtype=np.float32)
        hd["Camera Elevation Angle"] = np.array([5.0], dtype=np.float32)
        pcg = hd.create_group("Pattern Center Calibration")
        pcg["x-star"] = np.array([pc[0]], dtype=np.float32)
        pcg["y-star"] = np.array([pc[1]], dtype=np.float32)
        pcg["z-star"] = np.array([pc[2]], dtype=np.float32)
    return path


def make_up(path, n, sy=12, sx=14, version=3, nx=0, ny=0, is_hex=False, dx=1.0, dy=1.0):
    nbytes = 1 if str(path).endswith(".up1") else 2
    dtype = np.uint8 if nbytes == 1 else np.uint16
    offset = 16 if version == 1 else 42
    with open(path, "wb") as f:
        f.write(struct.pack("<4I", version, sx, sy, offset))
        if version >= 3:
            f.write(b"\x00")
            f.write(struct.pack("<2I", nx, ny))
            f.write(bytes([1 if is_hex else 0]))
            f.write(struct.pack("<2d", dx, dy))
        pats = np.zeros((n, sy, sx), dtype=dtype)
        for i in range(n):
            pats[i, 0, 0] = i
        f.write(pats.tobytes())
    return path
