# file: core/config.py

import os
from pathlib import Path
from typing import Optional

import yaml

from constants import CF_DIR
from utils.logger import get_logger

log = get_logger("config")


class ConfigManager:
    """
    Manages cloudflared config.yml files.
    Generates, validates, and resolves config paths.
    """

    @staticmethod
    def find_credentials_file(tunnel_id: str) -> str:
        """Return path to the credentials JSON for a tunnel ID."""
        p = CF_DIR / f"{tunnel_id}.json"
        return str(p)

    @staticmethod
    def generate(
        tunnel_id: str,
        tunnel_name: str,
        hostname: str,
        port: int | str,
        config_path: Optional[str] = None,
    ) -> tuple[str, str]:
        """
        Generate a cloudflared config.yml.
        Returns (file_path, yaml_string).
        Raises ValueError for invalid inputs, OSError for write failures.
        """
        if not tunnel_id:
            raise ValueError("tunnel_id cannot be empty")
        if not hostname:
            raise ValueError("hostname cannot be empty")

        creds = ConfigManager.find_credentials_file(tunnel_id)
        data = {
            "tunnel": tunnel_id,
            "credentials-file": creds,
            "ingress": [
                {"hostname": hostname, "service": f"http://localhost:{port}"},
                {"service": "http_status:404"},
            ],
        }

        out_path = config_path or str(CF_DIR / f"{tunnel_name}-config.yml")
        os.makedirs(os.path.dirname(out_path), exist_ok=True)

        try:
            with open(out_path, "w") as f:
                yaml.dump(data, f, default_flow_style=False)
        except OSError as exc:
            log.error("Failed to write config to %s: %s", out_path, exc)
            raise

        content = yaml.dump(data, default_flow_style=False)
        log.info("Config written to %s", out_path)
        return out_path, content

    @staticmethod
    def validate_file(config_path: str) -> tuple[bool, str]:
        """
        Validate a YAML config file.
        Returns (is_valid, error_message).
        """
        if not os.path.exists(config_path):
            return False, f"File not found: {config_path}"
        try:
            with open(config_path) as f:
                data = yaml.safe_load(f)
            if not isinstance(data, dict):
                return False, "Config must be a YAML mapping"
            if "tunnel" not in data:
                return False, "Config missing 'tunnel' key"
            if "ingress" not in data:
                return False, "Config missing 'ingress' key"
            return True, ""
        except yaml.YAMLError as exc:
            return False, f"Invalid YAML: {exc}"
