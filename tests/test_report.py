import os

from kikuchiworkbench.cli import main
from kikuchiworkbench.io.readers import write_fixture
from kikuchiworkbench.masters.importer import load_master
from kikuchiworkbench.pipeline import IndexingConfig, run_indexing_job
from kikuchiworkbench.synthetic import SyntheticSpec, make_synthetic_scan


def test_report_written_after_job(tmp_path, kp_data_dir, capsys):
    mp = os.path.join(kp_data_dir, "emsoft_ebsd_master_pattern", "ni_mc_mp_20kv_uint8_gzip_opts9.h5")
    scan, truth = make_synthetic_scan([load_master(mp)], SyntheticSpec(nrows=2, ncols=3))
    fx = write_fixture(tmp_path / "s.h5", scan, truth)
    cfg = IndexingConfig.from_dict({"scan": str(fx), "phases": [{"master": mp, "name": "Ni"}],
                                    "sampling": {"resolution_deg": 6}, "preset": "standard"})
    job, _ = run_indexing_job(cfg, tmp_path / "jobs")
    md = (job.outputs / "report.md").read_text()
    html = (job.outputs / "report.html").read_text()
    assert "## Results" in md and "indexed 6" in md and "Preset: standard" in md
    assert "data:image/png;base64," in html and "<h2>Settings</h2>" in html
    assert "not probabilities" in html
    (job.outputs / "report.html").unlink()
    assert main(["report", str(job.path)]) == 0
    assert (job.outputs / "report.html").exists() and "Report:" in capsys.readouterr().out
