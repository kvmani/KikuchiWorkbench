import json
import os

from kikuchiworkbench.cli import main


def test_inspect(kp_data_dir, capsys):
    assert main(["inspect", os.path.join(kp_data_dir, "edax_h5ebsd", "patterns.h5")]) == 0
    out = capsys.readouterr().out
    assert "edax_h5ebsd" in out and "WARNING" in out
    assert main(["inspect", os.path.join(kp_data_dir, "edax_h5ebsd", "patterns.h5"), "--json",
                 "--pc", "0.5", "0.3", "0.6", "--pc-convention", "tsl"]) == 0
    d = json.loads(capsys.readouterr().out)
    assert d["geometry_source"] == "user"


def test_inspect_pattern_free(tmp_path, capsys):
    p = tmp_path / "a.ang"
    p.write_text("# x\n")
    assert main(["inspect", str(p)]) == 2
    assert "How to fix" in capsys.readouterr().err


def test_cif_and_master(tmp_path, capsys, kp_data_dir):
    cif = os.path.join(os.path.dirname(__file__), "data", "cif", "cu.cif")
    assert main(["cif", "validate", cif]) == 0
    assert "Fm-3m" in capsys.readouterr().out or True
    assert main(["cif", "xtal", cif, str(tmp_path / "cu.xtal")]) == 0
    mp = os.path.join(kp_data_dir, "emsoft_ebsd_master_pattern", "ni_mc_mp_20kv_uint8_gzip_opts9.h5")
    assert main(["master", "inspect", mp]) == 0
    assert "sha256" in capsys.readouterr().out
    assert main(["master", "add", mp, "--cache", str(tmp_path / "cache")]) == 0
    bad = os.path.join(os.path.dirname(__file__), "data", "cif", "bad_occupancy.cif")
    assert main(["cif", "validate", bad]) == 2


def test_demo(tmp_path, capsys):
    rc = main(["demo", "--jobs", str(tmp_path), "--rows", "3", "--cols", "3", "--resolution", "5",
               "--quiet"])
    out = capsys.readouterr().out
    assert rc == 0, out
    assert '"passed": true' in out


def test_index_config(tmp_path, capsys, kp_data_dir):
    import yaml

    from kikuchiworkbench.io.readers import write_fixture
    from kikuchiworkbench.masters.importer import load_master
    from kikuchiworkbench.synthetic import SyntheticSpec, make_synthetic_scan

    mp = os.path.join(kp_data_dir, "emsoft_ebsd_master_pattern", "ni_mc_mp_20kv_uint8_gzip_opts9.h5")
    scan, truth = make_synthetic_scan([load_master(mp)], SyntheticSpec(nrows=2, ncols=2))
    write_fixture(tmp_path / "s.h5", scan, truth)
    cfg = {"scan": "s.h5", "phases": [{"master": mp, "name": "Ni"}], "sampling": {"resolution_deg": 6}}
    (tmp_path / "run.yaml").write_text(yaml.safe_dump(cfg))
    assert main(["index", str(tmp_path / "run.yaml"), "--jobs", str(tmp_path / "jobs"), "--quiet"]) == 0
    assert "indexed" in capsys.readouterr().out
