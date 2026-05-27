# file: utils/paths.py

import json
import os
import shutil
import sys
from pathlib import Path

from utils.logger import get_logger

log = get_logger("paths")

# ── Settings file (stores user-overridden cloudflared path) ──────────────────

def _settings_path() -> Path:
    """Return path to tunnel-forge settings JSON file."""
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA", Path.home()))
    else:
        base = Path.home() / ".config"
    return base / "tunnel-forge" / "settings.json"


def _load_settings() -> dict:
    p = _settings_path()
    if p.exists():
        try:
            with open(p) as f:
                return json.load(f)
        except Exception as exc:
            log.warning("Could not load settings: %s", exc)
    return {}


def _save_settings(data: dict) -> None:
    p = _settings_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(p, "w") as f:
            json.dump(data, f, indent=2)
    except Exception as exc:
        log.warning("Could not save settings: %s", exc)


def get_custom_cloudflared_path() -> str | None:
    """Return user-configured cloudflared path (if any)."""
    return _load_settings().get("cloudflared_path") or None


def set_custom_cloudflared_path(path: str | None) -> None:
    """Persist a user-configured cloudflared path. Pass None to clear."""
    data = _load_settings()
    if path:
        data["cloudflared_path"] = path
    else:
        data.pop("cloudflared_path", None)
    _save_settings(data)
    log.info("Custom cloudflared path set to: %s", path)


# ── Core helpers ─────────────────────────────────────────────────────────────

def get_base_dir() -> str:
    """Return the base directory of the running app (frozen or script)."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__ + "/.."))


def get_icon_path() -> str | None:
    """
    Resolve tunnel-forge.png. Search order:
    1. PyInstaller bundle (_MEIPASS)
    2. assets/ subfolder next to main.py
    3. Directly next to main.py
    """
    if hasattr(sys, "_MEIPASS"):
        p = os.path.join(sys._MEIPASS, "assets", "tunnel-forge.png")
        if os.path.exists(p):
            return p

    base = get_base_dir()
    candidates = [
        os.path.join(base, "assets", "tunnel-forge.png"),
        os.path.join(base, "tunnel-forge.png"),
    ]
    for p in candidates:
        if os.path.exists(p):
            log.debug("Icon found: %s", p)
            return p

    log.warning("tunnel-forge.png not found in assets/ or base dir")
    return None


def get_cloudflared_path() -> str | None:
    """
    Locate the cloudflared binary. Search order:
    1. User-configured custom path (settings.json)
    2. PyInstaller bundle (_MEIPASS)
    3. Alongside the executable / script
    4. System PATH via shutil.which
    Returns None when not found anywhere.
    """
    binary = "cloudflared.exe" if os.name == "nt" else "cloudflared"

    # 1. Custom path set by user via Settings / Browse
    custom = get_custom_cloudflared_path()
    if custom:
        if os.path.isfile(custom):
            log.debug("cloudflared found (custom path): %s", custom)
            return custom
        log.warning("Custom cloudflared path set but not found: %s", custom)

    # 2. PyInstaller bundle
    if hasattr(sys, "_MEIPASS"):
        p = os.path.join(sys._MEIPASS, binary)
        if os.path.exists(p):
            log.debug("cloudflared found in bundle: %s", p)
            return p

    # 3. Alongside app
    p = os.path.join(get_base_dir(), binary)
    if os.path.exists(p):
        log.debug("cloudflared found alongside app: %s", p)
        return p

    # 4. System PATH
    which = shutil.which("cloudflared")
    if which:
        log.debug("cloudflared found on PATH: %s", which)
        return which

    log.error("cloudflared binary not found anywhere")
    return None
