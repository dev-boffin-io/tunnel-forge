# file: core/parser.py

import re
from typing import Optional

from constants import URL_REGEX, CONNECTED_SIGNALS
from utils.logger import get_logger

log = get_logger("parser")

# UUID pattern for tunnel ID extraction
_UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f-]{27}")

# Hostname validation (basic)
_HOSTNAME_RE = re.compile(
    r"^(?:[a-zA-Z0-9](?:[a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}$"
)

# Scheme prefix stripper
_SCHEME_RE = re.compile(r"^https?://")


def extract_url(line: str) -> Optional[str]:
    """Return the first cloudflare URL found in a log line, or None."""
    m = URL_REGEX.search(line)
    if m:
        url = m.group()
        log.debug("URL extracted: %s", url)
        return url
    return None


def is_connected_signal(line: str) -> bool:
    """Return True if the log line indicates a live tunnel connection."""
    return any(sig in line for sig in CONNECTED_SIGNALS)


def extract_tunnel_id(output: str) -> Optional[str]:
    """Parse tunnel UUID from `cloudflared tunnel create` output."""
    m = _UUID_RE.search(output)
    return m.group() if m else None


def is_valid_hostname(hostname: str) -> bool:
    """Validate a custom hostname (no scheme prefix)."""
    clean = _SCHEME_RE.sub("", hostname)
    return bool(_HOSTNAME_RE.match(clean))


def normalize_hostname(hostname: str) -> str:
    """Strip scheme prefix and return bare hostname."""
    return _SCHEME_RE.sub("", hostname)
