"""Reusable master cache keyed by crystal, simulation settings and provenance."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from ..cache import ArtifactCache
from .importer import MasterInfo, inspect_master

KIND = "masters"


def master_cache_fields(info: MasterInfo, crystal: dict | None = None,
                        simulation: dict | None = None) -> dict:
    return {
        "master": info.cache_key_fields(),
        "crystal": crystal or {},
        "simulation": simulation or {},
        "program": info.program,
        "emsoft_version": info.emsoft_version,
    }


def add_master(cache: ArtifactCache, path: str | os.PathLike, crystal: dict | None = None,
               simulation: dict | None = None) -> Path:
    """Verify a master file and copy it into the cache. Returns the cached file path."""
    info = inspect_master(path)
    fields = master_cache_fields(info, crystal, simulation)
    hit = cache.get(KIND, fields)
    if hit is not None:
        return hit / "master.h5"
    with cache.stage() as st:
        shutil.copy2(path, st / "master.h5")

        def verify(d: Path) -> dict:
            again = inspect_master(d / "master.h5")
            if again.sha256 != info.sha256:
                raise RuntimeError("Checksum changed while copying master into cache")
            return {"sha256": again.sha256, "checks": again.checks, "warnings": again.warnings}

        entry = cache.promote(st, KIND, fields, verify, {"master_info": info.to_dict()})
    return entry / "master.h5"
