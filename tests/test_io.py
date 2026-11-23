import os

import numpy as np
import pytest

from conftest import make_edax_h5, make_h5oina, make_up
from kikuchiworkbench.errors import (
    MissingMetadataError,
    PatternFreeInputError,
    UnsupportedFormatError,
)
from kikuchiworkbench.io.detect import detect_format
from kikuchiworkbench.io.readers import load_scan, read_fixture_truth, write_fixture
from kikuchiworkbench.io.scan import GridInfo, grid_coordinates, grid_indices


def test_bundled_vendor_samples(kp_data_dir):
    s = load_scan(os.path.join(kp_data_dir, "oxford_binary", "patterns.ebsp"))
    assert s.file_format == "oxford_ebsp" and s.n_points == 9 and s.pattern_shape == (60, 60)
    assert s.geometry_source.startswith("missing")
    s = load_scan(os.path.join(kp_data_dir, "edax_binary", "edax_binary.up1"), nav_shape=(3, 3))
    assert s.file_format == "edax_up1" and s.grid.nrows == 3
    s = load_scan(os.path.join(kp_data_dir, "edax_h5ebsd", "patterns.h5"))
    assert s.file_format == "edax_h5ebsd" and s.vendor == "EDAX/TSL" and s.n_points == 9
    assert s.geometry_source.startswith("missing")  # PC stored as zeros in this sample


def test_patterns_read_only(kp_data_dir):
    s = load_scan(os.path.join(kp_data_dir, "edax_h5ebsd", "patterns.h5"))
    with pytest.raises(ValueError):
        s.patterns[0, 0, 0] = 1
    chunk = s.get_patterns(0, 2)
    chunk[:] = 0  # copies are writable and do not affect the source
    assert s.patterns.max() > 0


def test_h5oina_prefers_raw(tmp_path):
    p = make_h5oina(tmp_path / "a.h5oina")
    s = load_scan(p)
    assert s.file_format == "oxford_h5oina"
    assert s.dataset_path.endswith("Unprocessed Patterns")
    assert np.all(np.asarray(s.patterns) == 7)
    s2 = load_scan(p, prefer_raw=False)
    assert s2.dataset_path.endswith("Processed Patterns")
    # Oxford PC -> Bruker: pcy_B = 1 - pcy_O * aspect, pcz_B = pcz_O * aspect (aspect = 30/20)
    np.testing.assert_allclose(s.detector.pc_average, [0.45, 1 - 0.62 * 1.5, 0.71 * 1.5], atol=1e-6)
    assert s.detector.binning == 8 and s.detector.sample_tilt == pytest.approx(70.0)
    assert s.grid.nrows == 2 and s.grid.ncols == 3


def test_h5oina_processed_only_warns(tmp_path):
    p = make_h5oina(tmp_path / "b.h5oina", raw=False)
    s = load_scan(p)
    assert s.dataset_path.endswith("Processed Patterns")
    assert any("processed" in w.lower() for w in s.warnings)


def test_h5oina_pattern_free(tmp_path):
    p = make_h5oina(tmp_path / "c.h5oina", raw=False, processed=False)
    with pytest.raises(PatternFreeInputError) as e:
        detect_format(p)
    assert "AZtec" in str(e.value)


def test_ebsp_with_companion(tmp_path, kp_data_dir):
    comp = make_h5oina(tmp_path / "comp.h5oina", ny=3, nx=3, sy=60, sx=60, raw=False, processed=False)
    s = load_scan(os.path.join(kp_data_dir, "oxford_binary", "patterns.ebsp"), companion=comp)
    assert s.geometry_source == "user"
    np.testing.assert_allclose(s.detector.pc_average, [0.45, 1 - 0.62, 0.71], atol=1e-6)


def test_edax_square_order_and_pc(tmp_path):
    p = make_edax_h5(tmp_path / "sq.h5", nrows=3, ncols=4)
    s = load_scan(p)
    assert s.grid.grid_type == "square" and s.n_points == 12
    assert [int(v) for v in np.asarray(s.patterns)[:, 0, 0]] == list(range(12))
    # TSL -> Bruker for non-square (16x20): pcy_B = 1 - y*, pcz_B = z* * min(16,20)/16
    np.testing.assert_allclose(s.detector.pc_average, [0.48, 1 - 0.71, 0.66], atol=1e-6)
    assert s.geometry_source == "file"
    assert s.detector.tilt == pytest.approx(5.0)


def test_edax_hex_grid(tmp_path):
    p = make_edax_h5(tmp_path / "hex.h5", nrows=3, ncols=4, grid="HexGrid")
    s = load_scan(p)
    assert s.grid.grid_type == "hexagonal" and s.n_points == 4 + 3 + 4
    rr, cc = s.map_indices()
    assert list(rr) == [0] * 4 + [1] * 3 + [2] * 4
    m = s.to_map(np.arange(s.n_points, dtype=float))
    assert np.isnan(m[1, 3]) and m[2, 0] == 7


def test_hex_coordinates():
    g = GridInfo("hexagonal", 3, 3, 2.0, np.sqrt(3))
    x, y = grid_coordinates(g)
    np.testing.assert_allclose(x, [0, 2, 4, 1, 3, 0, 2, 4])
    np.testing.assert_allclose(y, [0, 0, 0] + [np.sqrt(3)] * 2 + [2 * np.sqrt(3)] * 3)
    rr, cc = grid_indices(GridInfo("square", 2, 3))
    assert list(rr) == [0, 0, 0, 1, 1, 1] and list(cc) == [0, 1, 2, 0, 1, 2]


def test_up_versions(tmp_path):
    p1 = make_up(tmp_path / "v1.up1", 6, version=1)
    with pytest.raises(MissingMetadataError):
        load_scan(p1)
    s = load_scan(p1, nav_shape=(2, 3), step=0.5)
    assert s.grid.ncols == 3 and s.grid.step_x == 0.5
    p3 = make_up(tmp_path / "v3.up2", 6, version=3, nx=3, ny=2, dx=0.25, dy=0.25)
    s = load_scan(p3)
    assert s.grid.nrows == 2 and s.grid.ncols == 3 and s.dtype == np.uint16
    assert [int(v) for v in s.patterns[:, 0, 0]] == list(range(6))
    ph = make_up(tmp_path / "hex.up1", 8, version=3, nx=3, ny=3, is_hex=True, dx=1.0)
    s = load_scan(ph)
    assert s.grid.grid_type == "hexagonal" and s.n_points == 8
    bad = make_up(tmp_path / "v2.up1", 2, version=2)
    with pytest.raises(UnsupportedFormatError):
        detect_format(bad)


def test_user_geometry_override(tmp_path):
    p = make_edax_h5(tmp_path / "sq.h5")
    s = load_scan(p, geometry={"pc": [0.5, 0.4, 0.6], "pc_convention": "bruker", "binning": 4})
    assert s.geometry_source == "user" and s.detector.binning == 4
    np.testing.assert_allclose(s.detector.pc_average, [0.5, 0.4, 0.6])


@pytest.mark.parametrize("ext", [".ang", ".ctf", ".osc"])
def test_pattern_free_text(tmp_path, ext):
    p = tmp_path / f"scan{ext}"
    p.write_text("# header only\n")
    with pytest.raises(PatternFreeInputError) as e:
        load_scan(p)
    assert e.value.advice


def test_edax_pattern_free(tmp_path):
    p = make_edax_h5(tmp_path / "nop.h5", with_patterns=False)
    with pytest.raises(PatternFreeInputError):
        load_scan(p)


def test_unknown_files(tmp_path):
    p = tmp_path / "x.bin"
    p.write_bytes(b"\x00" * 100)
    with pytest.raises(UnsupportedFormatError):
        load_scan(p)
    import h5py

    q = tmp_path / "y.h5"
    with h5py.File(q, "w") as h:
        h["foo"] = 1
    with pytest.raises(UnsupportedFormatError):
        load_scan(q)


def test_fixture_round_trip(tmp_path):
    s = load_scan(make_edax_h5(tmp_path / "sq.h5"))
    out = write_fixture(tmp_path / "fx.h5", s, truth={"phase_id": np.arange(12) % 2,
                                                       "phase_names": ["a", "b"]},
                        provenance={"seed": 1})
    s2 = load_scan(out)
    assert s2.file_format == "kwb_fixture"
    np.testing.assert_array_equal(np.asarray(s2.patterns), np.asarray(s.patterns))
    np.testing.assert_allclose(s2.detector.pc_average, s.detector.pc_average)
    t = read_fixture_truth(out)
    assert t["phase_names"] == ["a", "b"] and t["provenance"]["seed"] == 1
