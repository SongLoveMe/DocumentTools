from __future__ import annotations

from typing import Callable

from PyQt5.QtCore import QObject, QRunnable, pyqtSignal

class WorkerSignals(QObject):
    completed = pyqtSignal(object)
    failed = pyqtSignal(str)

class Task(QRunnable):
    def __init__(self, action: Callable[[], object]):
        super().__init__()
        self.action = action
        self.signals = WorkerSignals()

    def run(self) -> None:
        try:
            self.signals.completed.emit(self.action())
        except Exception as exc:  # pragma: no cover - worker boundary
            self.signals.failed.emit(str(exc))
