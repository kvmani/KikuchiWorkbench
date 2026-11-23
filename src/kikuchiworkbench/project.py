"""Project files (``.kwbproj``, JSON): everything needed to reopen and rerun a study.

Stores the scan path and load options, candidate phases, detector geometry (including calibration results),
indexing settings and the history of runs (job folders, counts). Paths are stored relative to the project file
when possible so a project folder can be moved. Project files are small text files; scans, masters and results
stay where they are.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path

PROJECT_VERSION = "1"
PROJECT_SUFFIX = ".kwbproj"


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")


@dataclass
class Project:
    name: str = "untitled"
    scan: dict = field(default_factory=dict)       # {"path": str, "load_kwargs": {...}}
    geometry: dict = field(default_factory=dict)   # {"pc": [...], "pc_convention": "bruker", "tilt", "binning", ...}
    phases: list = field(default_factory=list)     # [{"name", "master", "energy"}]
    settings: dict = field(default_factory=dict)   # preset, resolution_deg, bin2, refine, cache, roi, decision...
    runs: list = field(default_factory=list)       # [{"job_dir", "created_utc", "counts", "n_points", "preset"}]
    notes: str = ""
    version: str = PROJECT_VERSION
    created_utc: str = field(default_factory=_now)
    modified_utc: str = field(default_factory=_now)
    path: str | None = None  # where it was loaded from / saved to (not written)

    # ------------------------------------------------------------- paths

    def _rel(self, p: str | None, base: Path) -> str | None:
        if not p or p.startswith("<"):
            return p
        try:
            return os.path.relpath(Path(p).resolve(), base.resolve())
        except ValueError:  # different drive on Windows
            return str(Path(p).resolve())

    def _abs(self, p: str | None, base: Path) -> str | None:
        if not p or p.startswith("<"):
            return p
        q = Path(p)
        return str(q if q.is_absolute() else (base / q).resolve())

    # ------------------------------------------------------------- io

    def save(self, path: str | os.PathLike) -> Path:
        p = Path(path)
        if p.suffix != PROJECT_SUFFIX:
            p = p.with_suffix(PROJECT_SUFFIX)
        p.parent.mkdir(parents=True, exist_ok=True)
        base = p.parent
        self.modified_utc = _now()
        d = asdict(self)
        d.pop("path")
        d["scan"] = {**self.scan, "path": self._rel(self.scan.get("path"), base)}
        d["phases"] = [{**ph, "master": self._rel(ph.get("master"), base)} for ph in self.phases]
        d["runs"] = [{**r, "job_dir": self._rel(r.get("job_dir"), base)} for r in self.runs]
        tmp = p.with_suffix(p.suffix + ".tmp")
        tmp.write_text(json.dumps(d, indent=2, default=str))
        os.replace(tmp, p)
        self.path = str(p)
        return p

    @classmethod
    def load(cls, path: str | os.PathLike) -> Project:
        p = Path(path)
        d = json.loads(p.read_text())
        if str(d.get("version", "1")).split(".")[0] != PROJECT_VERSION:
            raise ValueError(f"Unsupported project version {d.get('version')}")
        known = set(cls.__dataclass_fields__) - {"path"}
        proj = cls(**{k: v for k, v in d.items() if k in known})
        base = p.parent
        proj.scan = {**proj.scan, "path": proj._abs(proj.scan.get("path"), base)}
        proj.phases = [{**ph, "master": proj._abs(ph.get("master"), base)} for ph in proj.phases]
        proj.runs = [{**r, "job_dir": proj._abs(r.get("job_dir"), base)} for r in proj.runs]
        proj.path = str(p)
        return proj

    # ------------------------------------------------------------- conversion

    def to_config_dict(self) -> dict:
        """Indexing configuration (dict) equivalent to this project's settings."""
        from .indexing.preprocessing import DEFAULT_PIPELINE

        s = self.settings
        scan = {"path": self.scan.get("path"), **(self.scan.get("load_kwargs") or {})}
        if self.geometry.get("pc") is not None:
            scan["geometry"] = {k: v for k, v in self.geometry.items()
                                if k in ("pc", "pc_convention", "tilt", "binning", "px_size", "sample_tilt",
                                         "azimuthal", "twist")}
        cfg: dict = {
            "scan": scan,
            "phases": [{k: v for k, v in ph.items() if k in ("master", "name", "energy")} for ph in self.phases],
            "sampling": {"resolution_deg": s.get("resolution_deg", 3.0)},
            "matching": {"backend": s.get("backend", "auto"), "cache_dictionary": s.get("cache", False)},
            "decision": {k: s[k] for k in ("min_score", "ambiguity_margin") if k in s},
        }
        pre = [dict(x) for x in DEFAULT_PIPELINE]
        if s.get("bin2"):
            pre.append({"op": "bin", "factor": 2})
        cfg["preprocessing"] = pre
        if s.get("refine"):
            cfg["refinement"] = {"enabled": True}
        if s.get("roi"):
            cfg["roi"] = list(s["roi"])
        if s.get("preset"):
            cfg["preset"] = s["preset"]
        if cfg["decision"]:
            cfg["decision"]["provenance"] = s.get("decision_provenance", f"project {self.name}")
        return cfg

    def to_indexing_config(self):
        from .pipeline import IndexingConfig

        return IndexingConfig.from_dict(self.to_config_dict())

    def add_run(self, job_dir: str | os.PathLike, result=None, config=None) -> dict:
        rec = {"job_dir": str(job_dir), "created_utc": _now()}
        if result is not None:
            rec.update(counts=result.decision.counts(), n_points=result.n_points,
                       phase_names=list(result.phase_names))
        if config is not None:
            rec["preset"] = getattr(config, "preset", None)
            rec["roi"] = getattr(config, "roi", None)
        self.runs.append(rec)
        return rec

    def summary_lines(self) -> list[str]:
        lines = [f"Project: {self.name} (file {self.path})", f"Scan: {self.scan.get('path')}"]
        if self.geometry.get("pc") is not None:
            lines.append(f"Geometry: PC {self.geometry.get('pc')} ({self.geometry.get('pc_convention', 'bruker')}), "
                         f"source {self.geometry.get('source', 'user')}")
        for ph in self.phases:
            lines.append(f"Phase: {ph.get('name')} <- {ph.get('master')}")
        lines.append(f"Settings: {self.settings}")
        for r in self.runs:
            lines.append(f"Run {r.get('created_utc')}: {r.get('counts')} in {r.get('job_dir')}")
        return lines


def geometry_from_scan(scan) -> dict:
    """Capture a scan's current detector geometry for a project (Bruker convention)."""
    import numpy as np

    d = scan.detector
    g = {"pc": [float(v) for v in np.asarray(d.pc_average).ravel()], "pc_convention": "bruker",
         "tilt": float(d.tilt), "binning": int(d.binning), "sample_tilt": float(d.sample_tilt),
         "source": scan.geometry_source}
    cal = scan.metadata.get("pc_calibration")
    if cal:
        g["calibration"] = {k: cal[k] for k in ("pc_bruker", "pc_bruker_start", "pc_spread_std", "n_used",
                                                "reference_phase") if k in cal}
    return g
