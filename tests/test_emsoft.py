import os
import sys
from pathlib import Path

import pytest

from kikuchiworkbench.cache import ArtifactCache
from kikuchiworkbench.crystal.cif import read_cif
from kikuchiworkbench.emsoft.jobs import (
    EMsoftInstall,
    EMsoftPreset,
    parse_namelist,
    plan_master_job,
    run_master_job,
)
from kikuchiworkbench.errors import EMsoftError, JobCancelled
from kikuchiworkbench.jobs import Job, is_valid_job
from kikuchiworkbench.masters.importer import inspect_master

HERE = Path(__file__).parent
MOCK = HERE / "mock_emsoft"


@pytest.fixture
def install():
    return EMsoftInstall(bin_dir=str(MOCK), launcher=[sys.executable],
                         base_config={"EMsoftpathname": "/opt/EMsoft", "UserName": "x"})


@pytest.fixture
def ni_model():
    return read_cif(HERE / "data" / "cif" / "ni.cif")


def test_presets_and_namelists(tmp_path, ni_model):
    p = EMsoftPreset.named("quick")
    plan = plan_master_job(ni_model, p, tmp_path / "w")
    mc = parse_namelist(plan.mc_nml.read_text())
    assert mc["xtalname"] == plan.xtal.name and mc["sig"] == pytest.approx(70.0)
    assert mc["EkeV"] == pytest.approx(20.0) and mc["numsx"] % 2 == 1
    ms = parse_namelist(plan.master_nml.read_text())
    assert ms["energyfile"] == plan.data_file.name and ms["restart"] is False
    assert parse_namelist(plan.bethe_nml.read_text())["c3"] == pytest.approx(50.0)
    d = plan.describe()
    assert [s["stage"] for s in d["stages"]] == ["monte_carlo", "master"]
    assert "not yet validated" in d["status"]
    with pytest.raises(EMsoftError):
        EMsoftPreset.named("nope")
    bad = EMsoftPreset.named("quick")
    bad.mc_numsx = 200
    with pytest.raises(EMsoftError):
        bad.validate()


def test_run_with_mock(tmp_path, ni_model, install):
    plan = plan_master_job(ni_model, EMsoftPreset.named("quick"), tmp_path / "w")
    cache = ArtifactCache(tmp_path / "cache")
    rec = run_master_job(plan, install, cache=cache)
    assert [s["stage"] for s in rec["stages"]] == ["monte_carlo", "master"]
    cached = Path(rec["cached_master"])
    assert cached.exists() and (cached.parent / "COMPLETE").exists()
    assert (cached.parent / "EMMCOpenCL.nml").exists()
    info = inspect_master(cached)
    assert info.space_group == 225
    # job-local EMsoft config; user's config untouched
    cfg = plan.config_home / ".config" / "EMsoft" / "EMsoftConfig.json"
    assert str(plan.work_dir.resolve()) in cfg.read_text()


def test_mc_failure_not_promoted(tmp_path, ni_model, install, monkeypatch):
    monkeypatch.setenv("MOCK_EMSOFT_FAIL", "mc")
    plan = plan_master_job(ni_model, EMsoftPreset.named("quick"), tmp_path / "w")
    cache = ArtifactCache(tmp_path / "cache")
    with pytest.raises(EMsoftError, match="EMMCOpenCL exited"):
        run_master_job(plan, install, cache=cache)
    assert cache.entries("masters") == []
    assert "simulated failure" in (plan.work_dir / "EMMCOpenCL.log").read_text()


def test_master_failure_not_promoted(tmp_path, ni_model, install, monkeypatch):
    monkeypatch.setenv("MOCK_EMSOFT_FAIL", "master")
    plan = plan_master_job(ni_model, EMsoftPreset.named("quick"), tmp_path / "w")
    cache = ArtifactCache(tmp_path / "cache")
    with pytest.raises(EMsoftError, match="EMEBSDmaster exited"):
        run_master_job(plan, install, cache=cache)
    assert cache.entries("masters") == []


def test_cancel_running_stage(tmp_path, ni_model, install, monkeypatch):
    monkeypatch.setenv("MOCK_EMSOFT_SLEEP", "30")
    job = Job.create(tmp_path / "jobs", "emsoft")
    plan = plan_master_job(ni_model, EMsoftPreset.named("quick"), job.work)
    import threading

    threading.Timer(1.0, job.cancel_token.cancel).start()
    with pytest.raises(JobCancelled):
        job.run(lambda j: run_master_job(plan, install, cache=ArtifactCache(tmp_path / "c"), job=j))
    assert not is_valid_job(job.path)


def test_missing_executables(tmp_path):
    inst = EMsoftInstall(bin_dir=str(tmp_path))
    with pytest.raises(EMsoftError, match="KWB_EMSOFT_BIN"):
        inst.exe("EMMCOpenCL")
    assert "MISSING" in inst.check()["executables"]["EMMCOpenCL"]


@pytest.mark.emsoft
def test_real_emsoft_quick(tmp_path, ni_model):
    """Runs the real EMsoft chain. Requires KWB_EMSOFT_BIN and an OpenCL device."""
    inst = EMsoftInstall.discover()
    if inst is None:
        pytest.skip("EMsoft not installed (set KWB_EMSOFT_BIN)")
    plan = plan_master_job(ni_model, EMsoftPreset.named("quick"), tmp_path / "w")
    rec = run_master_job(plan, inst, cache=ArtifactCache(tmp_path / "cache"), timeout_s=7200)
    assert rec["master_info"]["space_group"] == 225
    assert os.path.exists(rec["cached_master"])
