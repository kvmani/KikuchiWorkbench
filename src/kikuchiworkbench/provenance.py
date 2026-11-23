"""Checksums, software versions and hardware information for provenance."""

from __future__ import annotations

import hashlib
import importlib.metadata
import os
import platform
import sys
from pathlib import Path

_TRACKED = [
    "kikuchiworkbench",
    "kikuchipy",
    "orix",
    "numpy",
    "scipy",
    "h5py",
    "diffpy.structure",
    "matplotlib",
    "PySide6",
    "torch",
]


def sha256_file(path: str | os.PathLike, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_array(arr) -> str:
    import numpy as np

    a = np.ascontiguousarray(arr)
    h = hashlib.sha256()
    h.update(str(a.dtype).encode())
    h.update(str(a.shape).encode())
    h.update(a.tobytes())
    return h.hexdigest()


def software_versions() -> dict[str, str | None]:
    out: dict[str, str | None] = {"python": sys.version.split()[0]}
    for name in _TRACKED:
        try:
            out[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            out[name] = None
    return out


def hardware_info() -> dict:
    info = {
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor() or None,
        "cpu_count": os.cpu_count(),
    }
    try:
        import numpy as np

        cfg = np.show_config(mode="dicts")  # numpy >= 1.25
        blas = cfg.get("Build Dependencies", {}).get("blas", {})
        info["blas"] = blas.get("name")
    except Exception:  # pragma: no cover - informational only
        info["blas"] = None
    return info


def file_record(path: str | os.PathLike) -> dict:
    p = Path(path)
    return {
        "path": str(p),
        "name": p.name,
        "size_bytes": p.stat().st_size,
        "sha256": sha256_file(p),
    }
