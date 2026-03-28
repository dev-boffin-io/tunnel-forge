# file: core/process.py

import os
import signal
import subprocess
import threading
from queue import Queue, Empty
from typing import Optional

from utils.logger import get_logger

log = get_logger("process")


def build_popen_kwargs() -> dict:
    """
    Platform-safe Popen kwargs: new session on POSIX, new process group on Windows.
    Both prevent Ctrl-C from propagating to the child.
    """
    kwargs: dict = {
        "stdout": subprocess.PIPE,
        "stderr": subprocess.STDOUT,
        "text": True,
        "bufsize": 1,
    }
    if os.name != "nt":
        kwargs["start_new_session"] = True
    else:
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    return kwargs


def enqueue_output(stream, queue: Queue) -> None:
    """
    Read lines from a stream into a queue on a daemon thread.
    Silently exits on broken pipe or stream closure.
    """
    try:
        for line in iter(stream.readline, ""):
            if not line:
                break
            queue.put(line)
    except (OSError, ValueError):
        # BrokenPipeError, ValueError('I/O on closed file') — normal on shutdown
        pass
    finally:
        try:
            stream.close()
        except Exception:
            pass


def drain_queue(q: Queue) -> None:
    """Discard all pending items from the queue."""
    while True:
        try:
            q.get_nowait()
        except Empty:
            break


def safe_terminate(process: Optional[subprocess.Popen]) -> None:
    """
    Gracefully terminate a subprocess, falling back to SIGKILL.
    Handles Windows (CTRL_BREAK_EVENT) and POSIX (kill process group).
    """
    if not process or process.poll() is not None:
        return

    log.debug("Terminating PID %d", process.pid)

    # --- POSIX: kill the entire process group ---------------------------------
    if os.name != "nt":
        try:
            os.killpg(os.getpgid(process.pid), signal.SIGTERM)
            process.wait(timeout=3)
            log.debug("PID %d terminated via SIGTERM", process.pid)
            return
        except ProcessLookupError:
            return  # already gone
        except Exception as exc:
            log.warning("SIGTERM failed for PID %d: %s", process.pid, exc)
    else:
        # --- Windows: CTRL_BREAK_EVENT then fall through ----------------------
        try:
            process.send_signal(signal.CTRL_BREAK_EVENT)
            process.wait(timeout=3)
            return
        except Exception as exc:
            log.warning("CTRL_BREAK_EVENT failed: %s", exc)

    # --- Hard kill fallback ---------------------------------------------------
    try:
        process.kill()
        log.debug("PID %d killed (SIGKILL)", process.pid)
    except Exception as exc:
        log.error("Kill failed for PID %d: %s", process.pid, exc)


def start_subprocess(cmd: list[str]) -> tuple[subprocess.Popen, Queue]:
    """
    Launch cmd and return (process, output_queue).
    A daemon thread immediately begins draining stdout into the queue.
    """
    process = subprocess.Popen(cmd, **build_popen_kwargs())
    q: Queue = Queue()
    threading.Thread(
        target=enqueue_output,
        args=(process.stdout, q),
        daemon=True,
    ).start()
    log.info("Started subprocess PID %d: %s", process.pid, " ".join(cmd))
    return process, q
