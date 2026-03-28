# file: core/network.py

import socket
import time

from constants import SERVICE_CHECK_RETRIES, SERVICE_CHECK_DELAY_S
from utils.logger import get_logger

log = get_logger("network")


def is_port_valid(port: int) -> bool:
    return 1 <= port <= 65535


def is_service_running(
    port: int,
    retries: int = SERVICE_CHECK_RETRIES,
    delay: float = SERVICE_CHECK_DELAY_S,
) -> bool:
    """
    Try to connect to localhost:<port> up to `retries` times.
    Handles race conditions where the app just started but isn't ready yet.
    """
    for attempt in range(1, retries + 1):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1.5):
                log.debug("Port %d is reachable (attempt %d)", port, attempt)
                return True
        except OSError:
            if attempt < retries:
                log.debug(
                    "Port %d not ready yet, retrying in %.1fs (%d/%d)",
                    port, delay, attempt, retries,
                )
                time.sleep(delay)
    log.warning("Port %d is not reachable after %d attempts", port, retries)
    return False


def get_local_pid_on_port(port: int) -> int | None:
    """
    Return PID of the process listening on a port, or None.
    Requires psutil; silently returns None if unavailable.
    """
    try:
        import psutil  # optional dependency
        for conn in psutil.net_connections(kind="inet"):
            if conn.laddr.port == port and conn.status == "LISTEN":
                return conn.pid
    except Exception:
        pass
    return None
