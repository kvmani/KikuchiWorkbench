"""Isolated job folders with status, logs, progress and cancellation.

Each job gets ``<root>/<timestamp>_<kind>_<id>/`` containing ``status.json``,
``job.log``, ``work/`` (scratch) and ``outputs/``. Only a successful job gets
a ``COMPLETE`` marker; failed or cancelled jobs get ``INVALID`` and their
status says why, so they cannot be mistaken for valid results.
"""

from __future__ import annotations

import datetime as _dt
import json
import logging
import os
import shutil
import threading
import time
import traceback
import uuid
from collections.abc import Callable
from pathlib import Path

from .errors import JobCancelled

ProgressFn = Callable[[float, str], None]


class CancelToken:
    def __init__(self):
        self._ev = threading.Event()

    def cancel(self) -> None:
        self._ev.set()

    @property
    def cancelled(self) -> bool:
        return self._ev.is_set()

    def raise_if_cancelled(self) -> None:
        if self._ev.is_set():
            raise JobCancelled("Job cancelled by user")


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")


class Job:
    def __init__(self, path: Path, kind: str):
        self.path = Path(path)
        self.kind = kind
        self.work = self.path / "work"
        self.outputs = self.path / "outputs"
        self.work.mkdir(parents=True, exist_ok=True)
        self.outputs.mkdir(parents=True, exist_ok=True)
        self.cancel_token = CancelToken()
        self.logger = logging.getLogger(f"kwb.job.{self.path.name}")
        self.logger.setLevel(logging.INFO)
        self.logger.propagate = False
        if not self.logger.handlers:
            fh = logging.FileHandler(self.path / "job.log", encoding="utf-8")
            fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
            self.logger.addHandler(fh)
        self._listeners: list[ProgressFn] = []
        self._last_status_write = 0.0
        self._status = {"kind": kind, "state": "created", "progress": 0.0, "message": "",
                        "created_utc": _now(), "updated_utc": _now()}
        self._write_status(force=True)

    @classmethod
    def create(cls, root: str | os.PathLike, kind: str) -> Job:
        stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        p = Path(root) / f"{stamp}_{kind}_{uuid.uuid4().hex[:6]}"
        p.mkdir(parents=True, exist_ok=False)
        return cls(p, kind)

    # ---------------------------------------------------------------- status

    def _write_status(self, force: bool = False) -> None:
        now = time.monotonic()
        if not force and now - self._last_status_write < 0.5:
            return
        self._last_status_write = now
        self._status["updated_utc"] = _now()
        tmp = self.path / "status.json.tmp"
        tmp.write_text(json.dumps(self._status, indent=2))
        os.replace(tmp, self.path / "status.json")

    @property
    def status(self) -> dict:
        return dict(self._status)

    def add_listener(self, fn: ProgressFn) -> None:
        self._listeners.append(fn)

    def progress(self, fraction: float, message: str = "") -> None:
        self.cancel_token.raise_if_cancelled()
        self._status.update(state="running", progress=float(min(max(fraction, 0.0), 1.0)),
                            message=message)
        self._write_status()
        if message:
            self.logger.info("%.1f%% %s", 100 * fraction, message)
        for fn in self._listeners:
            fn(fraction, message)

    def log(self, msg: str, level: int = logging.INFO) -> None:
        self.logger.log(level, msg)

    # ---------------------------------------------------------------- lifecycle

    def run(self, fn: Callable[[Job], object]):
        """Run ``fn(job)``; mark COMPLETE on success, INVALID on failure/cancel."""
        self._status.update(state="running", started_utc=_now())
        self._write_status(force=True)
        try:
            result = fn(self)
        except JobCancelled:
            self._finish("cancelled", "Cancelled by user")
            raise
        except BaseException as e:
            self.logger.error("Job failed: %s\n%s", e, traceback.format_exc())
            self._finish("failed", f"{type(e).__name__}: {e}")
            raise
        self._finish("completed", "Completed")
        return result

    def _finish(self, state: str, message: str) -> None:
        self._status.update(state=state, message=message, finished_utc=_now())
        if state == "completed":
            self._status["progress"] = 1.0
            (self.path / "COMPLETE").write_text("ok\n")
        else:
            (self.path / "INVALID").write_text(f"{state}: {message}\n")
            # scratch data of an invalid job is never reused
            shutil.rmtree(self.work, ignore_errors=True)
        self._write_status(force=True)
        self.logger.info("Job %s: %s", state, message)
        for h in list(self.logger.handlers):
            h.flush()
            h.close()
            self.logger.removeHandler(h)


def is_valid_job(path: str | os.PathLike) -> bool:
    p = Path(path)
    return (p / "COMPLETE").exists() and not (p / "INVALID").exists()
