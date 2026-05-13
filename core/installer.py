# file: core/installer.py
"""
CloudflaredInstaller
====================
Cross-platform install / update / version-check for the cloudflared binary.

Supported platforms
-------------------
  Windows  : x86_64 → cloudflared-windows-amd64.exe
             arm64  → cloudflared-windows-arm64.exe
  macOS    : arm64  → cloudflared-darwin-arm64.tgz
             x86_64 → cloudflared-darwin-amd64.tgz
  Linux    : amd64  → cloudflared-linux-amd64
             arm64  → cloudflared-linux-arm64
             armv6  → cloudflared-linux-arm
             386    → cloudflared-linux-386

All downloads come from the official GitHub releases page.
The binary is saved to the same directory as the running app/executable,
which is also where utils/paths.get_cloudflared_path() looks first.
"""

from __future__ import annotations

import os
import platform
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path
from typing import Callable, Optional

from utils.logger import get_logger
from utils.paths import get_base_dir, get_cloudflared_path

log = get_logger("installer")

# ── Constants ────────────────────────────────────────────────────────────────

GITHUB_API_LATEST = (
    "https://api.github.com/repos/cloudflare/cloudflared/releases/latest"
)
GITHUB_DOWNLOAD_BASE = (
    "https://github.com/cloudflare/cloudflared/releases/latest/download"
)

# ── Platform detection ───────────────────────────────────────────────────────

def _detect_asset() -> tuple[str, bool]:
    """
    Return (asset_filename, is_tarball).

    Raises RuntimeError for unsupported platforms.
    """
    system  = platform.system().lower()   # 'windows' | 'linux' | 'darwin'
    machine = platform.machine().lower()  # 'x86_64' | 'amd64' | 'arm64' | 'aarch64' | 'armv6l' | 'i386' | 'i686'

    # ── Windows ──────────────────────────────────────────────────────────────
    if system == "windows":
        if machine in ("amd64", "x86_64"):
            return "cloudflared-windows-amd64.exe", False
        if machine in ("arm64", "aarch64"):
            return "cloudflared-windows-arm64.exe", False
        raise RuntimeError(f"Unsupported Windows architecture: {machine}")

    # ── macOS ────────────────────────────────────────────────────────────────
    if system == "darwin":
        if machine in ("arm64", "aarch64"):
            return "cloudflared-darwin-arm64.tgz", True
        return "cloudflared-darwin-amd64.tgz", True

    # ── Linux ────────────────────────────────────────────────────────────────
    if system == "linux":
        if machine in ("amd64", "x86_64"):
            return "cloudflared-linux-amd64", False
        if machine in ("arm64", "aarch64"):
            return "cloudflared-linux-arm64", False
        if machine.startswith("armv6"):
            return "cloudflared-linux-arm", False
        if machine in ("i386", "i686", "386"):
            return "cloudflared-linux-386", False
        raise RuntimeError(f"Unsupported Linux architecture: {machine}")

    raise RuntimeError(f"Unsupported platform: {system} / {machine}")


def _dest_path() -> Path:
    """Destination path for the binary (next to the app)."""
    binary_name = "cloudflared.exe" if os.name == "nt" else "cloudflared"
    return Path(get_base_dir()) / binary_name


# ── Version helpers ──────────────────────────────────────────────────────────

def get_installed_version() -> Optional[str]:
    """Return the version string of the installed binary, or None."""
    binary = get_cloudflared_path()
    if not binary:
        return None
    try:
        result = subprocess.run(
            [binary, "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        # typical output: "cloudflared version 2025.7.0 (built 2025-07-01...)"
        for part in result.stdout.split() + result.stderr.split():
            if part and part[0].isdigit() and "." in part:
                return part.strip("()")
        return result.stdout.strip() or result.stderr.strip() or "unknown"
    except Exception as exc:
        log.warning("Could not determine installed version: %s", exc)
        return None


def get_latest_version() -> Optional[str]:
    """Fetch the latest release tag from GitHub API (e.g. '2025.7.0')."""
    import json
    try:
        req = urllib.request.Request(
            GITHUB_API_LATEST,
            headers={"User-Agent": "tunnel-forge-updater/1.0"},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
            tag = data.get("tag_name", "")
            return tag.lstrip("v") if tag else None
    except Exception as exc:
        log.warning("Could not fetch latest version: %s", exc)
        return None


def is_update_available() -> tuple[bool, Optional[str], Optional[str]]:
    """
    Compare installed vs latest version.

    Returns (update_available, installed_version, latest_version).
    If either version is unknown, returns (False, ..., ...).
    """
    installed = get_installed_version()
    latest    = get_latest_version()
    if not installed or not latest:
        return False, installed, latest
    available = installed.strip() != latest.strip()
    return available, installed, latest


# ── Download + install ───────────────────────────────────────────────────────

def download_and_install(
    progress_cb: Optional[Callable[[int, int], None]] = None,
    log_cb:      Optional[Callable[[str], None]]      = None,
) -> str:
    """
    Download the latest cloudflared binary and install it next to the app.

    Parameters
    ----------
    progress_cb : callable(downloaded_bytes, total_bytes) or None
    log_cb      : callable(message: str) or None

    Returns
    -------
    str  Path to the installed binary.

    Raises
    ------
    RuntimeError on any failure.
    """

    def _log(msg: str) -> None:
        log.info(msg)
        if log_cb:
            log_cb(msg)

    asset, is_tarball = _detect_asset()
    url = f"{GITHUB_DOWNLOAD_BASE}/{asset}"
    dest = _dest_path()

    _log(f"Detected platform: {platform.system()} / {platform.machine()}")
    _log(f"Asset: {asset}")
    _log(f"Downloading from: {url}")

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_file = Path(tmp_dir) / asset

        # ── Download ─────────────────────────────────────────────────────────
        def _reporthook(block_num: int, block_size: int, total_size: int) -> None:
            if progress_cb and total_size > 0:
                downloaded = min(block_num * block_size, total_size)
                progress_cb(downloaded, total_size)

        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "tunnel-forge-installer/1.0"}
            )
            with urllib.request.urlopen(req, timeout=60) as resp, \
                 open(tmp_file, "wb") as fout:
                total = int(resp.headers.get("Content-Length", 0))
                downloaded = 0
                chunk = 65536
                while True:
                    data = resp.read(chunk)
                    if not data:
                        break
                    fout.write(data)
                    downloaded += len(data)
                    if progress_cb and total:
                        progress_cb(downloaded, total)
        except Exception as exc:
            raise RuntimeError(f"Download failed: {exc}") from exc

        _log("Download complete. Installing...")

        # ── Extract tarball (macOS) ───────────────────────────────────────────
        if is_tarball:
            with tarfile.open(tmp_file, "r:gz") as tar:
                # The binary inside the tarball is named 'cloudflared'
                member = next(
                    (m for m in tar.getmembers() if m.name.endswith("cloudflared")),
                    None,
                )
                if not member:
                    raise RuntimeError("cloudflared binary not found in tarball")
                member.name = os.path.basename(member.name)
                tar.extract(member, path=tmp_dir)
            tmp_binary = Path(tmp_dir) / "cloudflared"
        else:
            tmp_binary = tmp_file

        # ── Copy to destination ───────────────────────────────────────────────
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(tmp_binary), str(dest))

        # ── Set executable bit (Unix) ─────────────────────────────────────────
        if os.name != "nt":
            current = dest.stat().st_mode
            dest.chmod(current | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    _log(f"✅ Installed → {dest}")
    return str(dest)
