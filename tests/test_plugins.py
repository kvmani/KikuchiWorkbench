import os
from pathlib import Path

import numpy as np
import pytest

from kikuchiworkbench.cli import main
from kikuchiworkbench.errors import UnsupportedFormatError
from kikuchiworkbench.io.detect import detect_format
from kikuchiworkbench.io.plugins import ReaderPlugin, register_reader, unregister_reader
from kikuchiworkbench.io.readers import load_scan
from kikuchiworkbench.io.scan import GRID_POINTS, GridInfo, ScanData


def test_nordif_plugin(kp_data_dir):
    p = os.path.join(kp_data_dir, "nordif", "Pattern.dat")
    info = detect_format(p)
    assert info.file_format == "nordif" and "plug-in" in info.notes[0]
    s = load_scan(p)
    assert s.n_points > 0 and s.geometry_source.startswith("missing")
    assert s.metadata["reader_plugin"] == "nordif"


def test_custom_plugin_registration(tmp_path):
    f = tmp_path / "scan.myfmt"
    f.write_bytes(b"MYFMT")

    def load(path, info, **kw):
        from kikuchipy.detectors import EBSDDetector

        pats = np.ones((2, 8, 8), np.uint8)
        return ScanData(pats, GridInfo(GRID_POINTS, 1, 2), EBSDDetector(shape=(8, 8)), np.zeros(2), np.zeros(2),
                        np.ones(2, bool), info.vendor, info.file_format)

    with pytest.raises(UnsupportedFormatError):
        detect_format(f)
    register_reader(ReaderPlugin("myfmt", "Acme", lambda p: Path(p).read_bytes()[:5] == b"MYFMT", load, "test"))
    try:
        s = load_scan(f)
        assert s.file_format == "myfmt" and s.n_points == 2
        with pytest.raises(ValueError):
            register_reader(ReaderPlugin("myfmt", "Acme", lambda p: False, load))
    finally:
        unregister_reader("myfmt")


def test_cli_readers(capsys):
    assert main(["readers"]) == 0
    out = capsys.readouterr().out
    assert "nordif" in out and "bruker_h5ebsd" in out
