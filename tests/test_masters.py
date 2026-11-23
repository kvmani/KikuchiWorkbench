import os

import h5py
import numpy as np
import pytest

from kikuchiworkbench.cache import ArtifactCache, make_key
from kikuchiworkbench.crystal.cif import make_cubic_model
from kikuchiworkbench.errors import MasterPatternError
from kikuchiworkbench.masters.cache import add_master
from kikuchiworkbench.masters.importer import inspect_master, load_master
from kikuchiworkbench.masters.kinematical import is_kinematical, simulate_kinematical_master


@pytest.fixture(scope="session")
def ni_emsoft(kp_data_dir):
    return os.path.join(kp_data_dir, "emsoft_ebsd_master_pattern", "ni_mc_mp_20kv_uint8_gzip_opts9.h5")


@pytest.fixture(scope="session")
def kin_ni(tmp_path_factory):
    p = tmp_path_factory.mktemp("kin") / "ni_kin.h5"
    return simulate_kinematical_master(make_cubic_model("Ni", "Ni", 3.524), p, half_size=60)


def test_inspect_emsoft_ni(ni_emsoft):
    i = inspect_master(ni_emsoft)
    assert i.space_group == 225 and i.point_group == "m-3m"
    assert i.hemispheres == ["north", "south"] and i.npx == 200
    assert i.energies_keV == [20.0] and i.sample_tilt_deg == 70.0
    assert i.emsoft_version.startswith("5_0") and not is_kinematical(i.program)
    assert len(i.sha256) == 64
    flat = str(i.nml)
    assert "UserEmail" not in flat and "@" not in flat  # personal data dropped


def test_load_matches_kikuchipy(ni_emsoft):
    import kikuchipy as kp

    lm = load_master(ni_emsoft)
    ref = kp.data.nickel_ebsd_master_pattern_small(projection="lambert", hemisphere="both")
    np.testing.assert_allclose(lm.signal.data, ref.data)
    assert lm.energy_mode == "single" and lm.energy_keV == 20.0
    assert load_master(ni_emsoft, energy="weighted").energy_mode == "weighted"
    with pytest.raises(MasterPatternError):
        load_master(ni_emsoft, energy=15.0)


def test_constant_master_rejected(kp_data_dir):
    # kikuchipy's tiny multi-energy Al2Cu sample stores constant slices: must be rejected
    with pytest.raises(MasterPatternError, match="constant"):
        inspect_master(os.path.join(kp_data_dir, "emsoft_ebsd_master_pattern", "master_patterns.h5"))


def test_not_a_master(kp_data_dir, tmp_path):
    with pytest.raises(MasterPatternError):
        inspect_master(os.path.join(kp_data_dir, "emsoft_ebsd", "simulated_ebsd.h5"))
    bad = tmp_path / "x.h5"
    bad.write_bytes(b"not hdf5")
    with pytest.raises(MasterPatternError):
        inspect_master(bad)


def _multi_energy_master(path, energies=(15.0, 18.0, 20.0)):
    n = 7
    rng = np.random.default_rng(1)
    m = make_cubic_model("Ni", "Ni", 3.524)
    from kikuchiworkbench.crystal.xtal import write_crystal_group

    with h5py.File(path, "w") as h:
        write_crystal_group(h.create_group("CrystalData"), m)
        g = h.create_group("EMData/EBSDmaster")
        data = np.stack([np.full((n, n), e, np.float32) + rng.random((n, n), np.float32) for e in energies])
        g["mLPNH"] = data[None]
        g["mLPSH"] = data[None]
        g["EkeVs"] = np.asarray(energies, np.float32)
        acc = np.zeros((5, 5, len(energies)), np.int32)
        acc[..., :] = [1, 1, 2]
        h["EMData/MCOpenCL/accum_e"] = acc
        h["EMheader/EBSDmaster/ProgramName"] = np.array([b"EMEBSDmaster.f90"])
        h["NMLparameters/MCCLNameList/sig"] = np.array([70.0])
        h["NMLparameters/MCCLNameList/EkeV"] = np.array([20.0])
    return path


def test_energy_selection_and_weighting(tmp_path):
    p = _multi_energy_master(tmp_path / "me.h5")
    i = inspect_master(p)
    assert i.energies_keV == [15.0, 18.0, 20.0] and i.energy_weighting_available
    lm = load_master(p, energy=18.0)
    assert lm.energy_keV == 18.0 and 18 <= lm.signal.data.mean() < 19
    lw = load_master(p, energy="weighted")
    assert lw.weights == pytest.approx([0.25, 0.25, 0.5])
    assert lw.signal.data.mean() == pytest.approx(0.25 * 15 + 0.25 * 18 + 0.5 * 20 + 0.5, abs=0.1)
    assert "approximation" in lw.describe()["energy_weighting_note"]


def test_bad_energy_axis(tmp_path):
    p = _multi_energy_master(tmp_path / "bad.h5", energies=(20.0, 18.0, 15.0))
    with pytest.raises(MasterPatternError, match="increasing"):
        inspect_master(p)


def test_kinematical_master_labelled(kin_ni):
    i = inspect_master(kin_ni)
    assert is_kinematical(i.program) and i.space_group == 225
    lm = load_master(kin_ni)
    assert lm.signal.data.shape == (2, 121, 121)
    assert np.ptp(lm.signal.data) > 0


def test_cache_promotion(tmp_path, ni_emsoft):
    cache = ArtifactCache(tmp_path / "cache")
    p1 = add_master(cache, ni_emsoft, simulation={"preset": "x"})
    p2 = add_master(cache, ni_emsoft, simulation={"preset": "x"})
    assert p1 == p2 and p1.exists() and (p1.parent / "COMPLETE").exists()
    p3 = add_master(cache, ni_emsoft, simulation={"preset": "y"})
    assert p3 != p1
    assert len(cache.entries("masters")) == 2
    assert not any((cache.root / ".staging").iterdir())


def test_cache_failed_verification_not_promoted(tmp_path):
    cache = ArtifactCache(tmp_path / "c")
    fields = {"a": 1}
    with pytest.raises(RuntimeError), cache.stage() as st:
        (st / "payload").write_text("partial")

        def verify(_):
            raise RuntimeError("bad output")

        cache.promote(st, "dicts", fields, verify)
    assert cache.get("dicts", fields) is None
    assert not (cache.root / "dicts" / make_key(fields)).exists()
    # incomplete entries are ignored and cleaned
    (cache.root / "dicts" / "deadbeef").mkdir(parents=True)
    assert cache.entries("dicts") == []
    assert cache.clean_incomplete() >= 1
