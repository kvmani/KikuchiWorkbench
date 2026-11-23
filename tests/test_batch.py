import json
import os

import yaml

from kikuchiworkbench.batch import BatchQueue
from kikuchiworkbench.cli import main
from kikuchiworkbench.io.readers import write_fixture
from kikuchiworkbench.masters.importer import load_master
from kikuchiworkbench.project import Project
from kikuchiworkbench.synthetic import SyntheticSpec, make_synthetic_scan


def _setup(tmp_path, kp_data_dir):
    mp = os.path.join(kp_data_dir, "emsoft_ebsd_master_pattern", "ni_mc_mp_20kv_uint8_gzip_opts9.h5")
    scan, truth = make_synthetic_scan([load_master(mp)], SyntheticSpec(nrows=2, ncols=3))
    fx = write_fixture(tmp_path / "s.h5", scan, truth)
    good = tmp_path / "good.yaml"
    good.write_text(yaml.safe_dump({"scan": str(fx), "phases": [{"master": mp, "name": "Ni"}],
                                    "sampling": {"resolution_deg": 6}}))
    bad = tmp_path / "bad.yaml"
    bad.write_text(yaml.safe_dump({"scan": str(tmp_path / "missing.h5"), "phases": [mp]}))
    proj = Project(name="p", scan={"path": str(fx)}, phases=[{"name": "Ni", "master": mp}],
                   geometry={"pc": [0.421, 0.2165, 0.502], "pc_convention": "bruker"},
                   settings={"resolution_deg": 6.0, "backend": "cpu"})
    pp = proj.save(tmp_path / "p.kwbproj")
    return good, bad, pp


def test_batch_runs_records_and_resumes(tmp_path, kp_data_dir):
    good, bad, pp = _setup(tmp_path, kp_data_dir)
    q = BatchQueue(tmp_path / "queue.json")
    q.add(good)
    q.add(bad)
    q.add(pp, roi=[0, 1, 0, 3])
    counts = q.run(tmp_path / "jobs")
    assert counts["completed"] == 2 and counts["failed"] == 1
    st = {it.label: it for it in BatchQueue(tmp_path / "queue.json").items}
    assert st["good"].counts["indexed"] == 6 and "FileNotFoundError" in st["bad"].message
    assert st["p"].counts["indexed"] == 3  # ROI applied to the project item
    assert len(Project.load(pp).runs) == 1
    # simulate a crash mid-run: item left 'running' becomes 'pending' on reload
    d = json.loads((tmp_path / "queue.json").read_text())
    d["items"][0]["status"] = "running"
    (tmp_path / "queue.json").write_text(json.dumps(d))
    q2 = BatchQueue(tmp_path / "queue.json")
    assert q2.items[0].status == "pending" and "resumed" in q2.items[0].message
    assert q2.retry_failed() == 1


def test_batch_cli(tmp_path, kp_data_dir, capsys):
    good, _, _ = _setup(tmp_path, kp_data_dir)
    qf = str(tmp_path / "q.json")
    assert main(["batch", "add", qf, str(good), "--preset", "quick"]) == 0
    assert main(["batch", "run", qf, "--jobs", str(tmp_path / "jobs")]) == 0
    assert main(["batch", "status", qf]) == 0
    assert "completed" in capsys.readouterr().out
