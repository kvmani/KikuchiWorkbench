import pytest
from orix.crystal_map import Phase

from kikuchiworkbench.cli import main
from kikuchiworkbench.pipeline import IndexingConfig
from kikuchiworkbench.presets import PRESETS, apply_preset, launch_check


def test_apply_preset_explicit_values_win():
    cfg = {"scan": "s.h5", "phases": ["m.h5"], "sampling": {"resolution_deg": 1.5}}
    out = apply_preset(cfg, "phase_study")
    assert out["sampling"]["resolution_deg"] == 1.5  # explicit wins
    assert out["refinement"]["enabled"] and out["calibration"]["enabled"]
    assert any(s["op"] == "bin" for s in out["preprocessing"])
    assert out["preset"] == "phase_study"
    assert cfg.get("refinement") is None  # input not mutated
    with pytest.raises(ValueError):
        apply_preset(cfg, "turbo")


def test_config_loader_records_preset(tmp_path):
    c = IndexingConfig.from_dict({"scan": "s.h5", "phases": ["m.h5"]}, base_dir=tmp_path, preset="quick")
    assert c.preset == "quick" and c.sampling["resolution_deg"] == 5.0
    assert c.to_dict()["preset"] == "quick"
    c2 = IndexingConfig.from_dict({"scan": "s.h5", "phases": ["m.h5"], "preset": "standard"})
    assert c2.sampling["resolution_deg"] == 3.0 and c2.matching["cache_dictionary"]
    c3 = IndexingConfig.from_dict({"scan": "s.h5", "phases": ["m.h5"]})
    assert c3.preset is None


def test_launch_check_estimates_and_warns():
    pg = Phase(space_group=225).point_group
    small = launch_check(100, 3600, {"Ni": pg}, 5.0)
    assert small.est_total_s < 60 and not small.warnings
    big = launch_check(2_000_000, 20000, {"A": pg, "B": pg}, 1.0, refine=True)
    assert big.est_total_s > 3600 and any("one hour" in w for w in big.warnings)
    assert "orientations" in big.summary()
    assert launch_check(10, 3600, {"Ni": pg}, 5.0, cached=True).est_projection_s == 0


def test_cli_lists_presets(capsys):
    assert main(["presets"]) == 0
    out = capsys.readouterr().out
    for name in PRESETS:
        assert name in out
