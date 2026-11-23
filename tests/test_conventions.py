import numpy as np
import pytest
from kikuchipy.detectors import EBSDDetector

from kikuchiworkbench.conventions import DetectorShape, convert_pc, from_bruker, to_bruker

# Asymmetric, off-centre, non-square geometry so sign/transpose/mirror errors show up.
PC = np.array([0.4137, 0.2219, 0.6031])
SHAPES = [DetectorShape(60, 80, 8), DetectorShape(80, 60, 2), DetectorShape(50, 50, 1)]
CONVS = ["tsl", "oxford", "emsoft", "emsoft4"]


@pytest.mark.parametrize("shape", SHAPES)
@pytest.mark.parametrize("conv", CONVS)
def test_round_trip(shape, conv):
    out = from_bruker(PC, conv, shape, px_size=59.2)
    back = to_bruker(out, conv, shape, px_size=59.2)
    np.testing.assert_allclose(back, PC, rtol=0, atol=1e-12)


@pytest.mark.parametrize("shape", SHAPES)
@pytest.mark.parametrize("conv", CONVS)
def test_matches_kikuchipy(shape, conv):
    det = EBSDDetector(shape=(shape.nrows, shape.ncols), pc=PC, binning=shape.binning, px_size=59.2)
    kp = {"tsl": det.pc_tsl, "oxford": det.pc_oxford, "emsoft": det.pc_emsoft,
          "emsoft4": lambda: det.pc_emsoft(4)}[conv]()
    ours = from_bruker(PC, conv, shape, px_size=59.2)
    np.testing.assert_allclose(ours, np.asarray(kp).reshape(3), atol=1e-10)
    det2 = EBSDDetector(shape=(shape.nrows, shape.ncols), pc=ours, binning=shape.binning,
                        px_size=59.2, convention=conv)
    np.testing.assert_allclose(det2.pc.reshape(3), PC, atol=1e-10)


def test_known_values():
    shape = DetectorShape(60, 80, 8)
    # EMsoft: PC left of centre (pcx<0.5) -> positive xpc; above centre (pcy<0.5) -> positive ypc
    xpc, ypc, L = from_bruker([0.4, 0.3, 0.6], "emsoft", shape, px_size=70)
    assert xpc == pytest.approx(64.0) and ypc == pytest.approx(96.0) and L == pytest.approx(20160.0)
    # TSL/Oxford flip the vertical axis
    assert from_bruker([0.4, 0.3, 0.6], "tsl", shape)[1] == pytest.approx(0.7)
    ox = from_bruker([0.4, 0.3, 0.6], "oxford", shape)
    assert ox[1] == pytest.approx(0.7 / (80 / 60)) and ox[2] == pytest.approx(0.6 / (80 / 60))


def test_mirror_is_detected():
    shape = DetectorShape(60, 80, 1)
    a = from_bruker([0.3, 0.2, 0.6], "tsl", shape)
    b = from_bruker([0.7, 0.2, 0.6], "tsl", shape)
    assert not np.allclose(a, b)


def test_vectorised_and_convert():
    shape = DetectorShape(60, 80, 4)
    pcs = np.stack([PC, PC + 0.01, PC - 0.02])
    out = convert_pc(pcs, "tsl", "oxford", shape)
    assert out.shape == (3, 3)
    np.testing.assert_allclose(convert_pc(out, "oxford", "tsl", shape), pcs, atol=1e-12)


def test_unknown_convention():
    with pytest.raises(ValueError):
        to_bruker(PC, "nope", DetectorShape(10, 10))
