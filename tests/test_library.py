import os
import shutil

from kikuchiworkbench.cli import main
from kikuchiworkbench.crystal.cif import make_cubic_model
from kikuchiworkbench.library import PhaseLibrary
from kikuchiworkbench.masters.kinematical import simulate_kinematical_master


def test_library_link_copy_search_stale(tmp_path, kp_data_dir, capsys):
    ni = tmp_path / "ni.h5"
    shutil.copy(os.path.join(kp_data_dir, "emsoft_ebsd_master_pattern", "ni_mc_mp_20kv_uint8_gzip_opts9.h5"), ni)
    cu = simulate_kinematical_master(make_cubic_model("Cu", "Cu", 3.615), tmp_path / "cu.h5", half_size=30)
    lib = PhaseLibrary(tmp_path / "cache")
    assert lib.entries() == []
    e = lib.add(ni, name="Ni (EMsoft)")
    assert e["source"] == "linked" and e["formula"] == "Ni" and not e["kinematical"]
    lib.add(cu, copy=True)
    ents = lib.entries()
    assert {x["source"] for x in ents} == {"linked", "cached"}
    assert [x["formula"] for x in lib.entries("cu")] == ["Cu"] and lib.entries("cu")[0]["kinematical"]
    assert len(lib.entries("225")) == 2
    # linked file changes -> stale, not silently used
    with open(ni, "ab") as f:
        f.write(b"\0")
    stale = [x for x in lib.entries() if x["source"] == "linked"][0]
    assert stale["stale"] and "changed" in stale["stale_reason"]
    assert lib.clean()["stale_links"] == 1
    assert main(["library", "--cache", str(tmp_path / "cache"), "list"]) == 0
    out = capsys.readouterr().out
    assert "Cu" in out and "KINEMATICAL" in out
    assert lib.remove(ents[0]["sha256"][:10]) >= 1
