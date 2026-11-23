import json
import os
import shutil

import pytest

from kikuchiworkbench.cli import main
from kikuchiworkbench.io.readers import write_fixture
from kikuchiworkbench.masters.importer import load_master
from kikuchiworkbench.project import Project
from kikuchiworkbench.synthetic import SyntheticSpec, make_synthetic_scan


@pytest.fixture
def study(tmp_path, kp_data_dir):
    d = tmp_path / "study"
    d.mkdir()
    mp = d / "ni_master.h5"
    shutil.copy(os.path.join(kp_data_dir, "emsoft_ebsd_master_pattern", "ni_mc_mp_20kv_uint8_gzip_opts9.h5"), mp)
    scan, truth = make_synthetic_scan([load_master(str(mp))], SyntheticSpec(nrows=2, ncols=3))
    fx = write_fixture(d / "scan.h5", scan, truth)
    proj = Project(name="ni_study", scan={"path": str(fx), "load_kwargs": {}},
                   geometry={"pc": [0.421, 0.2165, 0.502], "pc_convention": "bruker", "tilt": 0.0,
                             "source": "user"},
                   phases=[{"name": "Ni", "master": str(mp), "energy": "max"}],
                   settings={"resolution_deg": 6.0, "backend": "cpu", "min_score": 0.1,
                             "ambiguity_margin": 0.005})
    return d, proj


def test_round_trip_relative_paths_and_move(study, tmp_path):
    d, proj = study
    p = proj.save(d / "ni_study")  # suffix added
    assert p.suffix == ".kwbproj"
    raw = json.loads(p.read_text())
    assert raw["scan"]["path"] == "scan.h5" and raw["phases"][0]["master"] == "ni_master.h5"
    moved = tmp_path / "moved"
    shutil.move(str(d), moved)
    q = Project.load(moved / "ni_study.kwbproj")
    assert os.path.exists(q.scan["path"]) and os.path.exists(q.phases[0]["master"])
    assert q.settings["resolution_deg"] == 6.0 and q.name == "ni_study"


def test_to_config_and_cli_run(study, capsys):
    d, proj = study
    cfg = proj.to_indexing_config()
    assert cfg.scan["geometry"]["pc"] == [0.421, 0.2165, 0.502] and cfg.sampling["resolution_deg"] == 6.0
    p = proj.save(d / "ni_study.kwbproj")
    assert main(["project", "run", str(p), "--jobs", str(d / "jobs"), "--quiet"]) == 0
    q = Project.load(p)
    assert len(q.runs) == 1 and q.runs[0]["counts"]["indexed"] == 6
    assert main(["project", "show", str(p)]) == 0
    assert "Run " in capsys.readouterr().out


def test_bad_version(tmp_path):
    p = tmp_path / "x.kwbproj"
    p.write_text(json.dumps({"version": "9", "name": "x"}))
    with pytest.raises(ValueError):
        Project.load(p)
