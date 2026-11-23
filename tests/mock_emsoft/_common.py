"""Shared helpers for mock EMsoft executables (tests only)."""

import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))


def config():
    home = Path(os.environ.get("HOME") or os.environ["USERPROFILE"])
    return json.loads((home / ".config" / "EMsoft" / "EMsoftConfig.json").read_text())


def resolve(name, key="EMdatapathname"):
    return Path(config()[key]) / name


def maybe_fail(stage):
    if os.environ.get("MOCK_EMSOFT_FAIL") == stage:
        print(f"mock {stage}: simulated failure")
        sys.exit(3)
    if os.environ.get("MOCK_EMSOFT_SLEEP"):
        time.sleep(float(os.environ["MOCK_EMSOFT_SLEEP"]))
