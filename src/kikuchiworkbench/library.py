"""Phase library: verified master patterns available for projects.

Two kinds of entries, shown together:

* **cached** — masters promoted into the artifact cache (copied, verified, with provenance);
* **linked** — external master files registered in ``library.json`` (verified when added, not copied, so
  large EMsoft masters stay where they are). A linked entry whose file changed or disappeared is reported as
  stale instead of being used.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import shutil
from pathlib import Path

from .cache import ArtifactCache
from .crystal.cif import ELEMENTS
from .masters.importer import MasterInfo, inspect_master
from .masters.kinematical import is_kinematical
from .provenance import sha256_file

LIBRARY_FILE = "library.json"


def _entry(info: MasterInfo, source: str, path: str, extra: dict | None = None) -> dict:
    els = sorted({ELEMENTS[z - 1] for z in info.atom_types if 0 < z <= len(ELEMENTS)})
    e = {
        "name": info.phase_name, "elements": els, "formula": "-".join(els),
        "space_group": info.space_group, "point_group": info.point_group,
        "lattice_nm_deg": info.lattice_nm_deg, "energies_keV": info.energies_keV,
        "kinematical": is_kinematical(info.program), "program": info.program,
        "emsoft_version": info.emsoft_version, "sha256": info.sha256, "path": path, "source": source,
        "size_mb": round(Path(path).stat().st_size / 1e6, 1) if Path(path).exists() else None,
        "stale": False,
    }
    if extra:
        e.update(extra)
    return e


class PhaseLibrary:
    def __init__(self, root: str | os.PathLike | None = None):
        self.cache = ArtifactCache(root)
        self.file = self.cache.root / LIBRARY_FILE

    # ------------------------------------------------------------- linked registry

    def _read(self) -> dict:
        if self.file.exists():
            return json.loads(self.file.read_text())
        return {"version": "1", "linked": []}

    def _write(self, d: dict) -> None:
        tmp = self.file.with_suffix(".tmp")
        tmp.write_text(json.dumps(d, indent=2))
        os.replace(tmp, self.file)

    def add(self, path: str | os.PathLike, copy: bool = False, name: str | None = None) -> dict:
        """Verify a master and add it (linked by default; ``copy=True`` promotes it into the cache)."""
        p = Path(path).resolve()
        info = inspect_master(p)
        if name:
            info.phase_name = name
        if copy:
            from .masters.cache import add_master

            cached = add_master(self.cache, p)
            return _entry(info, "cached", str(cached))
        d = self._read()
        d["linked"] = [x for x in d["linked"] if x["sha256"] != info.sha256]
        rec = {"path": str(p), "sha256": info.sha256, "name": info.phase_name,
               "added_utc": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")}
        d["linked"].append(rec)
        self._write(d)
        return _entry(info, "linked", str(p))

    def remove(self, sha256_prefix: str) -> int:
        """Unlink linked entries and delete cached entries whose checksum starts with the prefix."""
        n = 0
        d = self._read()
        keep = [x for x in d["linked"] if not x["sha256"].startswith(sha256_prefix)]
        n += len(d["linked"]) - len(keep)
        d["linked"] = keep
        self._write(d)
        for entry in self.cache.entries("masters"):
            meta = self.cache.meta(entry)
            if meta.get("master_info", {}).get("sha256", "").startswith(sha256_prefix):
                shutil.rmtree(entry, ignore_errors=True)
                n += 1
        return n

    # ------------------------------------------------------------- listing

    def entries(self, query: str | None = None, verify_linked: bool = False) -> list[dict]:
        out = []
        for entry in self.cache.entries("masters"):
            meta = self.cache.meta(entry)
            mi = meta.get("master_info")
            if not mi:
                continue
            info = MasterInfo(**{k: v for k, v in mi.items() if k in MasterInfo.__dataclass_fields__})
            out.append(_entry(info, "cached", str(entry / "master.h5"), {"cache_key": meta.get("key")}))
        for rec in self._read()["linked"]:
            p = Path(rec["path"])
            if not p.exists():
                out.append({"name": rec.get("name"), "path": str(p), "sha256": rec["sha256"], "source": "linked",
                            "stale": True, "stale_reason": "file missing", "formula": "", "elements": [],
                            "space_group": None, "kinematical": None, "energies_keV": []})
                continue
            try:
                info = inspect_master(p)
            except Exception as e:
                out.append({"name": rec.get("name"), "path": str(p), "sha256": rec["sha256"], "source": "linked",
                            "stale": True, "stale_reason": f"no longer a valid master: {e}", "formula": "",
                            "elements": [], "space_group": None, "kinematical": None, "energies_keV": []})
                continue
            e = _entry(info, "linked", str(p))
            e["name"] = rec.get("name") or e["name"]
            if info.sha256 != rec["sha256"]:
                e.update(stale=True, stale_reason="file changed since it was added")
            out.append(e)
        if query:
            q = query.lower().strip()
            out = [e for e in out if q in str(e.get("name", "")).lower() or q in str(e.get("formula", "")).lower()
                   or q == str(e.get("space_group")) or q in [x.lower() for x in e.get("elements", [])]]
        return sorted(out, key=lambda e: (str(e.get("formula")), str(e.get("name"))))

    def clean(self) -> dict:
        """Remove incomplete cache entries and stale links."""
        removed_incomplete = self.cache.clean_incomplete()
        d = self._read()
        alive = [x for x in d["linked"] if Path(x["path"]).exists() and sha256_file(x["path"]) == x["sha256"]]
        stale = len(d["linked"]) - len(alive)
        d["linked"] = alive
        self._write(d)
        return {"incomplete_cache_entries": removed_incomplete, "stale_links": stale}

    def cache_usage(self) -> dict:
        usage = {}
        for kind_dir in self.cache.root.iterdir():
            if kind_dir.is_dir() and not kind_dir.name.startswith("."):
                usage[kind_dir.name] = round(sum(f.stat().st_size for f in kind_dir.rglob("*") if f.is_file()) / 1e9, 3)
        return usage
