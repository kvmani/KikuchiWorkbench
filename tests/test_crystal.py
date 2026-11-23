from pathlib import Path

import numpy as np
import pytest

from kikuchiworkbench.crystal.cif import cif_text_for, make_cubic_model, read_cif
from kikuchiworkbench.crystal.xtal import read_xtal, write_xtal
from kikuchiworkbench.errors import CrystalValidationError

CIF = Path(__file__).parent / "data" / "cif"


def _fhkl(model, dmin=0.9):
    from diffsims.crystallography import ReciprocalLatticeVector

    r = ReciprocalLatticeVector.from_min_dspacing(model.to_orix_phase(), dmin)
    r.sanitise_phase()
    r.calculate_structure_factor()
    o = np.lexsort(r.hkl.T)
    return r.hkl[o], np.abs(r.structure_factor)[o]


def test_ni_cu_positive():
    ni = read_cif(CIF / "ni.cif")
    cu = read_cif(CIF / "cu.cif")
    assert ni.space_group == cu.space_group == 225
    assert ni.a == pytest.approx(3.524) and cu.a == pytest.approx(3.615)
    assert ni.crystal_system == "cubic" and ni.elements == ["Ni"]
    assert ni.sites[0].B_iso_A2 == pytest.approx(8 * np.pi**2 * 0.0045)
    assert ni.lattice_nm_deg[0] == pytest.approx(0.3524)
    assert ni.source_sha256 and ni.summary_lines()


def test_equivalent_origin_shift_same_reflections():
    h1, a1 = _fhkl(read_cif(CIF / "ni.cif"))
    h2, a2 = _fhkl(read_cif(CIF / "ni_shifted_origin.cif"))
    np.testing.assert_array_equal(h1, h2)
    np.testing.assert_allclose(a1, a2, atol=1e-6)


def test_two_origin_choices_equivalent():
    m1 = read_cif(CIF / "si_origin1.cif")
    m2 = read_cif(CIF / "si_origin2.cif")
    assert (m1.setting, m2.setting) == (1, 2)
    h1, a1 = _fhkl(m1)
    h2, a2 = _fhkl(m2)
    np.testing.assert_array_equal(h1, h2)
    np.testing.assert_allclose(a1, a2, atol=1e-6)
    # diamond extinction: 200 forbidden, 111 allowed
    f = dict(zip(map(tuple, h1.astype(int)), a1, strict=True))
    assert f[(2, 0, 0)] < 1e-6 and f[(1, 1, 1)] > 1


@pytest.mark.parametrize(
    "name, fragment",
    [
        ("bad_occupancy.cif", "occupancy"),
        ("bad_mixed_site.cif", "Total occupancy"),
        ("bad_nm_units.cif", "nm"),
        ("bad_rhombohedral.cif", "Rhombohedral"),
        ("bad_origin_unspecified.cif", "two origin choices"),
        ("bad_magnetic.cif", "Magnetic"),
    ],
)
def test_negative_controls(name, fragment):
    with pytest.raises(CrystalValidationError) as e:
        read_cif(CIF / name)
    assert fragment in str(e.value)
    assert e.value.advice


def test_malformed_occupancy_text():
    txt = (CIF / "ni.cif").read_text().replace("1.0 0.0045", "abc 0.0045")
    with pytest.raises(CrystalValidationError):
        read_cif(txt)


def test_symop_origin_detection():
    base = (CIF / "si_origin2.cif").read_text().replace(" :2", "")
    from diffpy.structure.spacegroups import GetSpaceGroup

    g = GetSpaceGroup(227)
    # origin-1 operators from diffpy: no pure inversion -> setting 1
    ops = []
    for op in g.iter_symops():
        terms = []
        for row, t in zip(op.R, op.t, strict=True):
            s = "".join(
                ("+" if c > 0 else "-") + v for c, v in zip(row, "xyz", strict=True) if c != 0
            )
            if abs(t) > 1e-9:
                s += f"+{t:.4f}"
            terms.append(s.lstrip("+"))
        ops.append(",".join(terms))
    loop = "loop_\n_symmetry_equiv_pos_as_xyz\n" + "\n".join(f"'{o}'" for o in ops) + "\n"
    txt = base.replace("loop_\n_atom_site_label", loop + "loop_\n_atom_site_label")
    m = read_cif(txt)
    assert m.setting == 1


def test_metric_mismatch():
    txt = (CIF / "ni.cif").read_text().replace("_cell_length_c 3.5240(1)", "_cell_length_c 3.7")
    with pytest.raises(CrystalValidationError, match="Cubic"):
        read_cif(txt)


def test_round_trip_cif_and_xtal(tmp_path):
    m = read_cif(CIF / "si_origin2.cif")
    m2 = read_cif(cif_text_for(m))
    assert m2.key_fields() == m.key_fields()
    p = write_xtal(m, tmp_path / "si.xtal")
    r = read_xtal(p)
    assert r.space_group == 227 and r.setting == 2
    np.testing.assert_allclose(r.lattice_A_deg, m.lattice_A_deg)
    assert r.sites[0].Z == 14
    assert r.sites[0].B_iso_A2 == pytest.approx(m.sites[0].B_iso_A2, rel=1e-6)
    import h5py

    with h5py.File(p) as h:
        g = h["CrystalData"]
        assert g["AtomData"].shape == (5, 1)
        assert g["LatticeParameters"][0] == pytest.approx(0.5431)
        assert int(g["CrystalSystem"][0]) == 1


def test_make_cubic_model():
    m = make_cubic_model("cu_alt", "Cu", 3.70)
    assert m.a == 3.70 and m.space_group == 225
