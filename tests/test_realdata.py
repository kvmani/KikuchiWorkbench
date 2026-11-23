"""Per-vendor checks on real exports kept outside the repository.

Set KWB_REALDATA_DIR to a folder containing ``realdata.yaml``:

    files:
      - path: oxford/scan.h5oina          # relative to KWB_REALDATA_DIR
        vendor: Oxford Instruments
        file_format: oxford_h5oina
        software: AZtec 6.1               # recorded for the supported-versions matrix
        n_points: 1200
        pattern_shape: [128, 156]
        grid_type: square
        load_kwargs: {}                   # e.g. {nav_shape: [30, 40], step: 0.5}
"""

import os
from pathlib import Path

import numpy as np
import pytest

pytestmark = pytest.mark.realdata

ROOT = os.environ.get("KWB_REALDATA_DIR")


def _entries():
    if not ROOT:
        return []
    import yaml

    cfg = yaml.safe_load((Path(ROOT) / "realdata.yaml").read_text())
    return cfg.get("files", [])


@pytest.mark.skipif(not ROOT, reason="KWB_REALDATA_DIR not set")
@pytest.mark.parametrize("entry", _entries(), ids=lambda e: e["path"])
def test_real_file(entry):
    from kikuchiworkbench.io.detect import detect_format
    from kikuchiworkbench.io.readers import load_scan

    p = Path(ROOT) / entry["path"]
    info = detect_format(p)
    assert info.file_format == entry["file_format"]
    scan = load_scan(p, lazy=True, **entry.get("load_kwargs", {}))
    assert scan.vendor == entry["vendor"]
    if "n_points" in entry:
        assert scan.n_points == entry["n_points"]
    if "pattern_shape" in entry:
        assert list(scan.pattern_shape) == list(entry["pattern_shape"])
    if "grid_type" in entry:
        assert scan.grid.grid_type == entry["grid_type"]
    first = scan.get_patterns(0, 1)
    assert np.isfinite(first).all() and first.std() > 0
    if scan.static_background is None:
        assert scan.n_points >= 1
