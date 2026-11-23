import json
import threading

import numpy as np
import pytest

from kikuchiworkbench.errors import JobCancelled, MissingMetadataError
from kikuchiworkbench.indexing.sampling import SamplingSpec, sample_orientations
from kikuchiworkbench.io.readers import load_scan, write_fixture
from kikuchiworkbench.jobs import Job, is_valid_job
from kikuchiworkbench.manifest import RunManifest, validate_manifest_dict
from kikuchiworkbench.masters.importer import load_master
from kikuchiworkbench.pipeline import IndexingConfig, PhaseSpec, run_indexing, run_indexing_job
from kikuchiworkbench.synthetic import SyntheticSpec, make_synthetic_scan, misorientation_deg

RES = 6.0  # coarse grid keeps tests fast


@pytest.fixture(scope="module")
def ni(kp_data_dir):
    import os

    p = os.path.join(kp_data_dir, "emsoft_ebsd_master_pattern", "ni_mc_mp_20kv_uint8_gzip_opts9.h5")
    return p, load_master(p, phase_name="Ni")


def _cfg(paths, **kw):
    return IndexingConfig(scan={"path": "<memory>"}, phases=[PhaseSpec(master=p) for p in paths],
                          sampling={"resolution_deg": RES}, **kw)


def test_exact_grid_recovery(ni):
    path, m = ni
    rot = sample_orientations(m.phase, SamplingSpec(RES))
    pick = rot[np.array([3, 101, 777, 1500, 2222, 40, 900, 1234, 1999])]
    spec = SyntheticSpec(nrows=3, ncols=3, counts=0, background_fraction=0.0, dtype="uint16")
    scan, truth = make_synthetic_scan([m], spec, rotations=pick)
    r = run_indexing(_cfg([path], preprocessing=[]), scan=scan, masters=[m], export=False)
    mis = misorientation_deg(r.best_quaternion[0], truth["quaternion"], m.phase.point_group)
    assert np.all(mis < 0.5), mis  # exact grid points recovered up to symmetry
    assert np.all(r.decision.best_score > 0.99)


def test_identical_masters_are_ambiguous(ni):
    path, m = ni
    m2 = load_master(path, phase_name="Ni_copy")
    scan, _ = make_synthetic_scan([m], SyntheticSpec(nrows=2, ncols=3, seed=5))
    r = run_indexing(_cfg([path, path]), scan=scan, masters=[m, m2], export=False)
    assert r.decision.counts()["ambiguous"] == 6
    assert np.all(r.decision.tie)
    assert np.all(r.decision.phase == -1)


def test_noise_patterns_rejected(ni):
    path, m = ni
    scan, _ = make_synthetic_scan([m], SyntheticSpec(nrows=3, ncols=3, seed=7))
    rng = np.random.default_rng(0)
    pats = np.asarray(scan.patterns).copy()
    pats[:4] = rng.poisson(300, pats[:4].shape)
    from dataclasses import replace

    noisy = replace(scan, patterns=pats)
    r = run_indexing(_cfg([path]), scan=noisy, masters=[m], export=False)
    assert np.all(r.decision.label[:4] == 2)  # unindexed
    assert np.all(r.decision.label[4:] == 0)
    assert r.signal[:4].max() < r.signal[4:].min()


def test_fixture_end_to_end_with_job(tmp_path, ni):
    path, m = ni
    scan, truth = make_synthetic_scan([m], SyntheticSpec(nrows=3, ncols=4, seed=11))
    fx = write_fixture(tmp_path / "scan.h5", scan, truth=truth)
    cfg = IndexingConfig.from_dict({"scan": str(fx), "phases": [{"master": path, "name": "Ni"}],
                                    "sampling": {"resolution_deg": RES}, "roi": [0, 2, 0, 4]})
    job, r = run_indexing_job(cfg, tmp_path / "jobs")
    assert is_valid_job(job.path)
    assert r.n_points == 8
    out = job.outputs
    for f in ("phase_map.png", "ipf_z_map.png", "score_map.png", "results.csv", "results.h5",
              "manifest.json"):
        assert (out / f).exists(), f
    man = json.loads((out / "manifest.json").read_text())
    validate_manifest_dict(man)
    assert man["inputs"]["scan"]["sha256"]
    assert man["parameters"]["matching"]["backend_used"] == "cpu"
    assert man["thresholds"]["provenance"].startswith("provisional")
    assert any(e["kind"] == "roi" for e in man["events"])
    assert RunManifest.read(out / "manifest.json").run_id == man["run_id"]
    status = json.loads((job.path / "status.json").read_text())
    assert status["state"] == "completed"
    lines = (out / "results.csv").read_text().splitlines()
    assert len(lines) == 9 and "phase_margin" in lines[0]


def test_missing_geometry_fails_job(tmp_path, kp_data_dir, ni):
    import os

    path, _ = ni
    cfg = IndexingConfig.from_dict({
        "scan": {"path": os.path.join(kp_data_dir, "oxford_binary", "patterns.ebsp")},
        "phases": [path], "sampling": {"resolution_deg": RES}})
    with pytest.raises(MissingMetadataError):
        run_indexing_job(cfg, tmp_path / "jobs")
    (jd,) = list((tmp_path / "jobs").iterdir())
    assert not is_valid_job(jd) and (jd / "INVALID").exists()
    assert json.loads((jd / "status.json").read_text())["state"] == "failed"


def test_placeholder_geometry_allowed_for_demo(tmp_path, kp_data_dir, ni):
    import os

    path, m = ni
    scan = load_scan(os.path.join(kp_data_dir, "oxford_binary", "patterns.ebsp"))
    cfg = _cfg([path], allow_placeholder_geometry=True)
    r = run_indexing(cfg, scan=scan, masters=[m], export=False)
    assert any("placeholder" in e["message"] for e in r.manifest.events)


def test_cancellation(tmp_path, ni):
    path, m = ni
    scan, _ = make_synthetic_scan([m], SyntheticSpec(nrows=2, ncols=2))
    job = Job.create(tmp_path / "jobs", "indexing")

    def cancel_soon(f, msg):
        if "matched" in msg:
            job.cancel_token.cancel()

    job.add_listener(cancel_soon)
    cfg = _cfg([path], matching={"dictionary_chunk": 200})
    with pytest.raises(JobCancelled):
        job.run(lambda j: run_indexing(cfg, job=j, scan=scan, masters=[m]))
    assert not is_valid_job(job.path)
    assert json.loads((job.path / "status.json").read_text())["state"] == "cancelled"
    assert not (job.outputs / "manifest.json").exists()


def test_cancel_from_other_thread(tmp_path, ni):
    path, m = ni
    scan, _ = make_synthetic_scan([m], SyntheticSpec(nrows=2, ncols=2))
    job = Job.create(tmp_path / "jobs", "indexing")
    t = threading.Timer(0.0, job.cancel_token.cancel)
    t.start()
    t.join()
    with pytest.raises(JobCancelled):
        job.run(lambda j: run_indexing(_cfg([path]), job=j, scan=scan, masters=[m]))


def test_dictionary_cache_hit_gives_identical_results(tmp_path, ni):
    path, m = ni
    scan, _ = make_synthetic_scan([m], SyntheticSpec(nrows=2, ncols=3, seed=3))
    mc = {"cache_dictionary": True, "cache_dir": str(tmp_path / "cache"), "dictionary_chunk": 700}
    r1 = run_indexing(_cfg([path], matching=mc), scan=scan, masters=[m], export=False)
    r2 = run_indexing(_cfg([path], matching=mc), scan=scan, masters=[m], export=False)
    r0 = run_indexing(_cfg([path]), scan=scan, masters=[m], export=False)
    msgs = [e["message"] for e in r1.manifest.events + r2.manifest.events if e["kind"] == "dictionary_cache"]
    assert "miss" in msgs[0] and "hit" in msgs[1]
    np.testing.assert_array_equal(r1.topk_index[0], r2.topk_index[0])
    np.testing.assert_array_equal(r0.topk_index[0], r1.topk_index[0])
    np.testing.assert_allclose(r0.topk_scores[0], r1.topk_scores[0], atol=1e-6)
    # a different detector must not reuse the cached dictionary
    from dataclasses import replace

    from kikuchiworkbench.io.readers import _detector

    d = scan.detector
    moved = replace(scan, detector=_detector(shape=d.shape, pc=[0.45, 0.25, 0.5], binning=d.binning,
                                             px_size=d.px_size, sample_tilt=d.sample_tilt))
    r3 = run_indexing(_cfg([path], matching=mc), scan=moved, masters=[m], export=False)
    assert any("miss" in e["message"] for e in r3.manifest.events if e["kind"] == "dictionary_cache")


def test_equal_budget_refinement(ni, tmp_path):
    path, m = ni
    m2 = load_master(path, phase_name="Ni_b")
    scan, truth = make_synthetic_scan([m], SyntheticSpec(nrows=2, ncols=3, seed=21))
    base = run_indexing(_cfg([path]), scan=scan, masters=[m], export=False)
    cfg = _cfg([path, path], refinement={"enabled": True, "maxeval": 150})
    r = run_indexing(cfg, scan=scan, masters=[m, m2], export=False)
    rec = r.manifest.parameters["refinement"]
    assert rec["equal_budget"] and rec["budget"]["trust_region_deg"] == RES
    assert set(rec["mean_evaluations_per_pattern"]) == {"Ni", "Ni_b"}
    mis0 = misorientation_deg(base.best_quaternion[0], truth["quaternion"], m.phase.point_group)
    mis1 = misorientation_deg(r.best_quaternion[0], truth["quaternion"], m.phase.point_group)
    assert np.median(mis1) < np.median(mis0) and np.median(mis1) < 1.0
    assert np.all(r.per_phase_best[:, 0] > r.dictionary_best[:, 0])
    # identical phases with identical budgets stay exactly tied -> ambiguous
    assert np.all(r.decision.tie)
