# file: core/cloudflared.py

import os
import subprocess
import time
from typing import Optional

from utils.logger import get_logger
from utils.paths import get_cloudflared_path

log = get_logger("cloudflared")


class CloudflaredRunner:
    """
    Builds and validates cloudflared commands.
    Pure command construction — no subprocess spawning here.
    """

    def __init__(self) -> None:
        self.binary: Optional[str] = get_cloudflared_path()

    def is_available(self) -> bool:
        return self.binary is not None

    def build_command(
        self,
        mode: str,
        port: int | str,
        tunnel_name: Optional[str] = None,
        config_path: Optional[str] = None,
    ) -> list[str]:
        """
        Build a cloudflared CLI command list.

        mode="quick"  → anonymous quick tunnel
        mode="custom" → named tunnel with optional config
        """
        if not self.binary:
            raise RuntimeError("cloudflared binary not found")

        if mode == "quick":
            return [self.binary, "tunnel", "--url", f"http://localhost:{port}"]

        # Custom / named tunnel
        cmd = [self.binary]

        if config_path:
            if os.path.exists(config_path):
                cmd += ["--config", config_path]
            else:
                log.warning(
                    "Config file not found at %s — using cloudflared defaults", config_path
                )
        else:
            log.warning(
                "No config file specified — using default cloudflared config (~/.cloudflared/)"
            )

        if not tunnel_name:
            raise ValueError("tunnel_name is required for custom mode")

        cmd += ["tunnel", "run", tunnel_name]
        return cmd

    def run_once(
        self,
        args: list[str],
        label: str,
        timeout: int = 60,
    ) -> tuple[bool, str]:
        """
        Run a one-shot cloudflared command (e.g. login, create, route dns).
        Returns (success, combined_output).
        """
        if not self.binary:
            return False, "cloudflared not found"
        try:
            result = subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            out = (result.stdout + result.stderr).strip()
            if result.returncode == 0:
                log.info("%s succeeded", label)
            else:
                log.error("%s failed (rc=%d): %s", label, result.returncode, out)
            return result.returncode == 0, out
        except subprocess.TimeoutExpired:
            log.error("%s timed out after %ds", label, timeout)
            return False, "timed out"
        except Exception as exc:
            log.error("%s raised: %s", label, exc)
            return False, str(exc)


class TunnelManager:
    """
    High-level tunnel lifecycle manager.
    Owns the CloudflaredRunner and exposes retry-with-backoff logic.
    Intended for CLI use; GUI uses WorkerThread instead.
    """

    def __init__(self) -> None:
        self.runner = CloudflaredRunner()

    def check_ready(self, port: int) -> tuple[bool, str]:
        """Pre-flight checks before launching a tunnel."""
        if not self.runner.is_available():
            return False, "cloudflared binary not found. Install it first."
        from core.network import is_service_running
        if not is_service_running(port):
            return False, f"No application on port {port}. Start your server first."
        return True, ""

    def build_command(
        self,
        mode: str,
        port: int | str,
        tunnel_name: Optional[str] = None,
        config_path: Optional[str] = None,
    ) -> list[str]:
        return self.runner.build_command(mode, port, tunnel_name, config_path)
