"""Background workers: long jobs run in QThreads so the GUI stays responsive."""

from __future__ import annotations

import traceback

from PySide6.QtCore import QObject, QThread, Signal, Slot

from ..errors import JobCancelled
from ..jobs import CancelToken


class Worker(QObject):
    progress = Signal(float, str)
    finished = Signal(object)
    failed = Signal(str)
    cancelled = Signal()

    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.cancel_token = CancelToken()

    @Slot()
    def run(self):
        try:
            result = self.fn(self, *self.args, **self.kwargs)
        except JobCancelled:
            self.cancelled.emit()
            return
        except Exception as e:  # reported to the GUI log, never swallowed silently
            self.failed.emit(f"{type(e).__name__}: {e}\n{traceback.format_exc()}")
            return
        self.finished.emit(result)

    def report(self, fraction: float, message: str = "") -> None:
        self.cancel_token.raise_if_cancelled()
        self.progress.emit(float(fraction), message)


_LIVE: set = set()  # keeps (thread, worker) alive until the thread has finished


def start_worker(parent, worker: Worker) -> QThread:
    """Run ``worker`` in a new QThread.

    Python keeps ownership of both objects (no ``deleteLater``) until the thread
    has finished, avoiding double deletion between Qt and the garbage collector.
    """
    thread = QThread()
    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    for sig in (worker.finished, worker.failed, worker.cancelled):
        sig.connect(thread.quit)
    pair = (thread, worker)
    _LIVE.add(pair)
    thread.finished.connect(lambda: _LIVE.discard(pair))
    thread.start()
    return thread
