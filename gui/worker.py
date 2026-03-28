# file: gui/worker.py

from __future__ import annotations

import time
from queue import Empty
from typing import Optional

from PyQt6.QtCore import QThread, pyqtSignal

from constants import MAX_RESTARTS, RESTART_DELAY_S
from core.parser import extract_url, is_connected_signal
from core.process import drain_queue, safe_terminate, start_subprocess
from utils.logger import get_logger

log = get_logger("worker")


class WorkerThread(QThread):
    """
    Runs a cloudflared subprocess off the GUI thread.

    Signals
    -------
    log_signal       — one line of raw log text
    url_signal       — a tunnel URL was detected
    connected_signal — tunnel connection confirmed
    stopped_signal   — worker has fully stopped
    """

    log_signal:       pyqtSignal = pyqtSignal(str)
    url_signal:       pyqtSignal = pyqtSignal(str)
    connected_signal: pyqtSignal = pyqtSignal()
    stopped_signal:   pyqtSignal = pyqtSignal()

    def __init__(self, cmd: list[str], static_url: Optional[str] = None) -> None:
        super().__init__()
        self.cmd        = cmd
        self.static_url = static_url
        self._running   = True
        self._process   = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def stop(self) -> None:
        """Signal the worker to stop and terminate the subprocess."""
        self._running = False
        safe_terminate(self._process)

    # ------------------------------------------------------------------
    # Thread entry point
    # ------------------------------------------------------------------

    def run(self) -> None:
        # For custom tunnels the URL is known before the process starts.
        if self.static_url:
            self.url_signal.emit(self.static_url)
            self.connected_signal.emit()

        for attempt in range(1, MAX_RESTARTS + 1):
            if not self._running:
                break

            current_url: Optional[str] = self.static_url

            try:
                self._process, q = start_subprocess(self.cmd)

                while self._running and self._process.poll() is None:
                    try:
                        line = q.get(timeout=0.1).strip()
                    except Empty:
                        continue

                    self.log_signal.emit(line)

                    if is_connected_signal(line):
                        self.connected_signal.emit()

                    url = extract_url(line)
                    if url and url != current_url:
                        current_url = url
                        self.url_signal.emit(url)

            except Exception as exc:
                self.log_signal.emit(f"[ERR] {exc}")
                log.error("WorkerThread error: %s", exc)
                break

            finally:
                safe_terminate(self._process)
                drain_queue(q)  # type: ignore[possibly-undefined]
                current_url = self.static_url

            if not self._running:
                break

            if attempt < MAX_RESTARTS:
                self.log_signal.emit(
                    f"[WARN] Tunnel stopped — restarting ({attempt}/{MAX_RESTARTS})..."
                )
                self.msleep(int(RESTART_DELAY_S * 1000))

        self.stopped_signal.emit()
