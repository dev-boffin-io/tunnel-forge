# file: utils/paths.py

import os
import sys
import shutil

from utils.logger import get_logger

log = get_logger("paths")


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
    1. PyInstaller bundle (_MEIPASS)
    2. Alongside the executable / script
    3. System PATH via shutil.which
    Returns None when not found anywhere.
    """
    binary = "cloudflared.exe" if os.name == "nt" else "cloudflared"

    if hasattr(sys, "_MEIPASS"):
        p = os.path.join(sys._MEIPASS, binary)
        if os.path.exists(p):
            log.debug("cloudflared found in bundle: %s", p)
            return p

    p = os.path.join(get_base_dir(), binary)
    if os.path.exists(p):
        log.debug("cloudflared found alongside app: %s", p)
        return p

    which = shutil.which("cloudflared")
    if which:
        log.debug("cloudflared found on PATH: %s", which)
        return which

    log.error("cloudflared binary not found anywhere")
    return None
