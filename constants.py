# file: constants.py

import re
from pathlib import Path

VERSION = "3.0.0"
APP_ID  = "tunnel-forge-single-instance"

CF_DIR = Path.home() / ".cloudflared"

URL_REGEX = re.compile(
    r'https://[a-zA-Z0-9.-]+\.(trycloudflare\.com|[a-zA-Z]{2,})'
)

CONNECTED_SIGNALS = (
    "Registered tunnel connection",
    "Connection established",
    "connIndex=0",
)

MAX_RESTARTS    = 3
RESTART_DELAY_S = 2
SERVICE_CHECK_RETRIES = 3
SERVICE_CHECK_DELAY_S = 0.5
