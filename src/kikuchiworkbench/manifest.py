"""Versioned machine-readable run manifest.

The manifest records inputs (with checksums), conventions, parameters,
software, hardware, thresholds, automatic fallbacks/batch changes and exports.
Bump ``MANIFEST_SCHEMA_VERSION`` on any incompatible change.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from . import __version__, conventions, provenance

MANIFEST_SCHEMA_VERSION = "1.0"
REQUIRED_KEYS = (
    "schema_version",
    "run_id",
    "created_utc",
    "status",
    "inputs",
    "conventions",
    "parameters",
    "software",
    "hardware",
    "events",
    "outputs",
)


def _utcnow() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")


def _jsonable(obj: Any):
    if isinstance(obj, dict):
        return {str(k): _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return float(obj)
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    if isinstance(obj, Path):
        return str(obj)
    return obj


@dataclass
class RunManifest:
    kind: str = "indexing"
    run_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    created_utc: str = field(default_factory=_utcnow)
    status: str = "created"  # created | running | completed | failed | cancelled
    inputs: dict = field(default_factory=dict)
    conventions: dict = field(default_factory=conventions.describe)
    parameters: dict = field(default_factory=dict)
    software: dict = field(default_factory=provenance.software_versions)
    hardware: dict = field(default_factory=provenance.hardware_info)
    thresholds: dict = field(default_factory=dict)
    events: list = field(default_factory=list)  # fallbacks, batch changes, warnings
    results: dict = field(default_factory=dict)
    outputs: dict = field(default_factory=dict)
    schema_version: str = MANIFEST_SCHEMA_VERSION
    workbench_version: str = __version__

    def add_input(self, key: str, path: str | os.PathLike | None = None, **extra) -> None:
        rec = provenance.file_record(path) if path is not None else {}
        rec.update(extra)
        self.inputs[key] = rec

    def log_event(self, kind: str, message: str, **data) -> None:
        self.events.append({"time_utc": _utcnow(), "kind": kind, "message": message, **data})

    def to_dict(self) -> dict:
        return _jsonable(asdict(self))

    def write(self, path: str | os.PathLike) -> Path:
        p = Path(path)
        tmp = p.with_suffix(p.suffix + ".tmp")
        tmp.write_text(json.dumps(self.to_dict(), indent=2, sort_keys=False))
        os.replace(tmp, p)
        return p

    @classmethod
    def read(cls, path: str | os.PathLike) -> RunManifest:
        d = json.loads(Path(path).read_text())
        validate_manifest_dict(d)
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in d.items() if k in known})


def validate_manifest_dict(d: dict) -> None:
    missing = [k for k in REQUIRED_KEYS if k not in d]
    if missing:
        raise ValueError(f"Manifest is missing required keys: {missing}")
    major = str(d["schema_version"]).split(".")[0]
    if major != MANIFEST_SCHEMA_VERSION.split(".")[0]:
        raise ValueError(
            f"Unsupported manifest schema {d['schema_version']} (expected {MANIFEST_SCHEMA_VERSION})"
        )
