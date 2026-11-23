import numpy as np
from orix.quaternion import Rotation

from kikuchiworkbench.compare import FRAME_CANDIDATES, compare_orientations
from kikuchiworkbench.io.readers import load_scan, write_fixture
from kikuchiworkbench.masters.importer import load_master
from kikuchiworkbench.pipeline import IndexingConfig, run_indexing_job
from kikuchiworkbench.synthetic import SyntheticSpec, make_synthetic_scan, random_rotations


def test_auto_frame_detects_rotation():
    from orix.crystal_map import Phase

    pg = Phase(space_group=225).point_group
    q = random_rotations(200, 3).data
    # vendor frame = workbench frame rotated: vendor * S = ours  ->  vendor = ours * S^-1
    s = Rotation.from_euler(np.deg2rad([FRAME_CANDIDATES["Rz90"]]))
    vendor = (Rotation(q) * ~s).data
    r = compare_orientations(q, vendor, pg, "auto")
    assert r["frame"] == "Rz90" and np.nanmax(r["disorientation_deg"]) < 1e-3
    assert r["frame_medians_tried"]["identity"] > 10
    assert np.nanmedian(compare_orientations(q, vendor, pg, "identity")["disorientation_deg"]) > 10


def test_vendor_comparison_in_job_and_report(tmp_path, kp_data_dir):
    import os

    mp = os.path.join(kp_data_dir, "emsoft_ebsd_master_pattern", "ni_mc_mp_20kv_uint8_gzip_opts9.h5")
    scan, truth = make_synthetic_scan([load_master(mp)], SyntheticSpec(nrows=3, ncols=3, seed=9))
    scan.vendor_euler_deg = truth["euler_deg"]  # a perfect 'vendor' in the same frame
    scan.vendor_phase = np.ones(9, dtype=int)
    fx = write_fixture(tmp_path / "s.h5", scan, truth)
    assert load_scan(fx).vendor_euler_deg is not None
    cfg = IndexingConfig.from_dict({"scan": str(fx), "phases": [{"master": mp, "name": "Ni"}],
                                    "sampling": {"resolution_deg": 5},
                                    "output": {"vendor_phase_names": {"1": "Ni"}}})
    job, r = run_indexing_job(cfg, tmp_path / "jobs")
    vc = r.manifest.results["vendor_comparison"]
    assert vc["frame"] == "identity" and vc["median_disorientation_deg"] < 4.0
    assert vc["phase_agreement_fraction"] == 1.0
    assert (job.outputs / "vendor_disorientation_map.png").exists()
    assert "Comparison with vendor indexing" in (job.outputs / "report.md").read_text()
