"""Content-addressed artifact cache with atomic, verified promotion.

Layout::

    <root>/<kind>/<key>/            promoted entry
        meta.json                   key fields, provenance, verification record
        COMPLETE                    written last; entries without it are ignored
        <payload files>
    <root>/.staging/<uuid>/         in-progress entries (never read as results)

An entry is promoted only after the caller's ``verify`` callback succeeds, so
cancelled or failed jobs cannot be mistaken for valid cached results.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import uuid
from collections.abc import Callable
from contextlib import contextmanager
from pathlib import Path

COMPLETE_MARKER = "COMPLETE"


def canonical_json(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def make_key(fields: dict) -> str:
    return hashlib.sha256(canonical_json(fields).encode()).hexdigest()[:32]


def default_cache_root() -> Path:
    env = os.environ.get("KWB_CACHE_DIR")
    if env:
        return Path(env)
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        return base / "KikuchiWorkbench" / "cache"
    return Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "kikuchiworkbench"


class ArtifactCache:
    def __init__(self, root: str | os.PathLike | None = None):
        self.root = Path(root) if root is not None else default_cache_root()
        self.root.mkdir(parents=True, exist_ok=True)

    def entry_dir(self, kind: str, key: str) -> Path:
        return self.root / kind / key

    def get(self, kind: str, fields: dict) -> Path | None:
        d = self.entry_dir(kind, make_key(fields))
        if (d / COMPLETE_MARKER).exists():
            return d
        return None

    def meta(self, entry: Path) -> dict:
        return json.loads((entry / "meta.json").read_text())

    @contextmanager
    def stage(self):
        """Yield a fresh staging directory; removed if not promoted."""
        d = self.root / ".staging" / uuid.uuid4().hex
        d.mkdir(parents=True)
        try:
            yield d
        finally:
            if d.exists():
                shutil.rmtree(d, ignore_errors=True)

    def promote(
        self,
        staging: Path,
        kind: str,
        fields: dict,
        verify: Callable[[Path], dict] | None = None,
        extra_meta: dict | None = None,
    ) -> Path:
        """Verify ``staging`` and move it into the cache atomically."""
        record = verify(staging) if verify is not None else {"verified": "no verifier supplied"}
        key = make_key(fields)
        meta = {"kind": kind, "key": key, "fields": fields, "verification": record}
        if extra_meta:
            meta.update(extra_meta)
        (staging / "meta.json").write_text(json.dumps(meta, indent=2, default=str))
        (staging / COMPLETE_MARKER).write_text("ok\n")
        dest = self.entry_dir(kind, key)
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists():
            if (dest / COMPLETE_MARKER).exists():
                shutil.rmtree(staging, ignore_errors=True)
                return dest  # identical key already promoted
            shutil.rmtree(dest, ignore_errors=True)  # stale incomplete entry
        os.replace(staging, dest)
        return dest

    def entries(self, kind: str) -> list[Path]:
        d = self.root / kind
        if not d.exists():
            return []
        return sorted(p for p in d.iterdir() if (p / COMPLETE_MARKER).exists())

    def clean_incomplete(self) -> int:
        n = 0
        st = self.root / ".staging"
        if st.exists():
            for p in st.iterdir():
                shutil.rmtree(p, ignore_errors=True)
                n += 1
        for kind_dir in self.root.iterdir():
            if kind_dir.name.startswith(".") or not kind_dir.is_dir():
                continue
            for p in kind_dir.iterdir():
                if p.is_dir() and not (p / COMPLETE_MARKER).exists():
                    shutil.rmtree(p, ignore_errors=True)
                    n += 1
        return n
