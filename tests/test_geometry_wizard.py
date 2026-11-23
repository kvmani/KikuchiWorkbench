import numpy as np

from kikuchiworkbench.geometry_wizard import band_segments, fit_score
from kikuchiworkbench.masters.importer import load_master
from kikuchiworkbench.synthetic import SyntheticSpec, make_synthetic_scan


def test_overlay_and_fit_peak_at_true_pc(kp_data_dir):
    import os

    from kikuchipy.detectors import EBSDDetector

    m = load_master(os.path.join(kp_data_dir, "emsoft_ebsd_master_pattern", "ni_mc_mp_20kv_uint8_gzip_opts9.h5"))
    scan, truth = make_synthetic_scan([m], SyntheticSpec(nrows=1, ncols=1, counts=0, background_fraction=0))
    det = scan.detector
    q = truth["quaternion"][0]
    segs = band_segments(m.phase, det, q)
    assert segs.ndim == 3 and segs.shape[1:] == (2, 2) and len(segs) > 5
    meas = np.asarray(scan.patterns[0], dtype=np.float32)
    true = fit_score(m, det, q, meas)
    pc = np.asarray(det.pc_average).ravel()
    off = EBSDDetector(shape=det.shape, pc=pc + [0.03, 0, 0], sample_tilt=det.sample_tilt, binning=det.binning,
                       px_size=det.px_size)
    assert true > 0.99 and fit_score(m, off, q, meas) < true - 0.1
    moved = band_segments(m.phase, off, q)
    assert not np.allclose(moved[: min(len(moved), len(segs))], segs[: min(len(moved), len(segs))])
