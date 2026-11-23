"""Batch queue: run several indexing configs or projects sequentially, resumably.

The queue is a JSON file. Each item records its status (pending, running, completed, failed, cancelled), job
folder and message, and the file is saved after every state change. Loading a queue resets items left in
``running`` by a crash to ``pending`` so ``run`` resumes where it stopped. Items run through the same
``run_indexing_job`` path as the CLI and GUI.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import traceback
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .errors import JobCancelled

STATUSES = ("pending", "running", "completed", "failed", "cancelled")


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")


@dataclass
class BatchItem:
    path: str
    kind: str  # "config" | "project"
    preset: str | None = None
    roi: list | None = None
    label: str = ""
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    status: str = "pending"
    job_dir: str | None = None
    message: str = ""
    counts: dict | None = None
    started_utc: str | None = None
    finished_utc: str | None = None


class BatchQueue:
    def __init__(self, path: str | os.PathLike):
        self.path = Path(path)
        self.items: list[BatchItem] = []
        if self.path.exists():
            self._load()

    def _load(self) -> None:
        d = json.loads(self.path.read_text())
        self.items = [BatchItem(**it) for it in d.get("items", [])]
        resumed = 0
        for it in self.items:
            if it.status == "running":  # interrupted by a crash or restart
                it.status = "pending"
                it.message = "resumed after interruption"
                resumed += 1
        if resumed:
            self.save()

    def save(self) -> Path:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps({"version": "1", "items": [asdict(i) for i in self.items]}, indent=2))
        os.replace(tmp, self.path)
        return self.path

    def add(self, path: str | os.PathLike, preset: str | None = None, roi=None, label: str = "") -> BatchItem:
        p = Path(path).resolve()
        if not p.exists():
            raise FileNotFoundError(p)
        kind = "project" if p.suffix == ".kwbproj" else "config"
        item = BatchItem(path=str(p), kind=kind, preset=preset, roi=list(roi) if roi else None,
                         label=label or p.stem)
        self.items.append(item)
        self.save()
        return item

    def counts(self) -> dict:
        return {s: sum(1 for i in self.items if i.status == s) for s in STATUSES}

    def retry_failed(self) -> int:
        n = 0
        for it in self.items:
            if it.status in ("failed", "cancelled"):
                it.status, it.message = "pending", "queued for retry"
                n += 1
        self.save()
        return n

    def _config_for(self, item: BatchItem):
        from .pipeline import IndexingConfig

        if item.kind == "project":
            from .project import Project

            d = Project.load(item.path).to_config_dict()
            cfg = IndexingConfig.from_dict(d, preset=item.preset)
        else:
            cfg = IndexingConfig.from_file(item.path, preset=item.preset)
        if item.roi:
            cfg.roi = list(item.roi)
        return cfg

    def run(self, jobs_root: str | os.PathLike, listener=None, cancel=None, on_item=None) -> dict:
        """Run all pending items in order. ``cancel`` (CancelToken) stops after/within the current item."""
        from .pipeline import run_indexing_job

        for item in self.items:
            if item.status != "pending":
                continue
            if cancel is not None and cancel.cancelled:
                break
            item.status, item.started_utc, item.message = "running", _now(), ""
            self.save()
            if on_item:
                on_item(item)
            job = None
            try:
                from .jobs import Job

                cfg = self._config_for(item)
                job = Job.create(jobs_root, "batch")
                if cancel is not None:
                    job.cancel_token = cancel
                item.job_dir = str(job.path)
                self.save()
                _, result = run_indexing_job(cfg, jobs_root, listener=listener, job=job)
                item.status, item.counts = "completed", result.decision.counts()
                if item.kind == "project":
                    from .project import Project

                    proj = Project.load(item.path)
                    proj.add_run(job.path, result, cfg)
                    proj.save(item.path)
            except JobCancelled:
                item.status, item.message = "cancelled", "cancelled by user"
            except Exception as e:
                item.status = "failed"
                item.message = f"{type(e).__name__}: {e}"
                if job is not None:
                    (job.path / "batch_error.txt").write_text(traceback.format_exc())
            item.finished_utc = _now()
            self.save()
            if on_item:
                on_item(item)
            if item.status == "cancelled":
                break
        return self.counts()
