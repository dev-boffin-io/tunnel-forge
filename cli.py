# file: cli.py

import argparse
import json
import sys
import time
import webbrowser
from queue import Empty

# ── Windows: enable ANSI colour output ────────────────────────────────────────
if sys.platform == "win32":
    try:
        import colorama          # preferred: pip install colorama
        colorama.init()
    except ImportError:
        try:                     # fallback: enable VT processing via ctypes (Win10+)
            import ctypes
            ctypes.windll.kernel32.SetConsoleMode(
                ctypes.windll.kernel32.GetStdHandle(-11), 7
            )
        except Exception:
            pass                 # give up silently — colours just won't render

from constants import MAX_RESTARTS, RESTART_DELAY_S
from core.cloudflared import TunnelManager
from core.network import is_service_running
from core.parser import extract_url, is_connected_signal
from core.process import drain_queue, safe_terminate, start_subprocess, terminate_pid
from utils.logger import get_logger
from utils.paths import read_pid_file, remove_pid_file, write_pid_file

log = get_logger("cli")


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="tunnelforge",
        description="TunnelForge — cloudflared tunnel manager",
    )
    p.add_argument("--port", type=int, default=3000, help="Local port to expose")
    p.add_argument("--cli", action="store_true", help="Force CLI mode")
    p.add_argument("--no-open", action="store_true", help="Do not auto-open browser")
    p.add_argument("--json", action="store_true", help="JSON output mode")
    p.add_argument("--tunnel-name", help="Named tunnel (custom domain)")
    p.add_argument("--hostname", help="Custom hostname — displayed immediately")
    p.add_argument("--config", help="Path to cloudflared config.yml")
    p.add_argument("--silent", action="store_true", help="Suppress log output")
    p.add_argument(
        "--stop", action="store_true",
        help="Stop the running tunnel on --port (started via CLI or GUI) and exit",
    )
    return p


def stop_tunnel(port: int, as_json: bool = False) -> int:
    """Stop a tunnel previously started (from any TunnelForge process) on `port`."""
    pid = read_pid_file(port)
    if pid is None:
        msg = f"No running tunnel found on port {port}"
        if as_json:
            print(json.dumps({"status": "not_running", "port": port, "message": msg}), flush=True)
        else:
            log.warning(msg)
        return 1

    ok, err = terminate_pid(pid)
    remove_pid_file(port)

    if ok:
        msg = f"Stopped tunnel on port {port} (PID {pid})"
        if as_json:
            print(json.dumps({"status": "stopped", "port": port, "pid": pid}), flush=True)
        else:
            print(f"\033[92m[STOPPED] {msg}\033[0m", flush=True)
        return 0
    else:
        msg = f"Could not stop tunnel on port {port} (PID {pid}): {err}"
        if as_json:
            print(json.dumps({"status": "error", "port": port, "pid": pid, "message": err}), flush=True)
        else:
            log.error(msg)
        return 1


def run_cli(args: argparse.Namespace) -> int:
    if args.stop:
        return stop_tunnel(args.port, as_json=args.json)

    manager = TunnelManager()

    ok, msg = manager.check_ready(args.port)
    if not ok:
        log.error(msg)
        return 1

    mode = "custom" if args.tunnel_name else "quick"
    try:
        cmd = manager.build_command(
            mode,
            args.port,
            tunnel_name=args.tunnel_name,
            config_path=args.config,
        )
    except (ValueError, RuntimeError) as exc:
        log.error("Command build failed: %s", exc)
        return 1

    # Show custom domain URL immediately (it's predictable)
    if mode == "custom" and args.hostname:
        from core.parser import normalize_hostname
        url = f"https://{normalize_hostname(args.hostname)}"
        if args.json:
            print(json.dumps({"status": "connected", "url": url}), flush=True)
        else:
            print(f"\n\033[92m[CUSTOM DOMAIN] {url}\033[0m", flush=True)

    for attempt in range(1, MAX_RESTARTS + 1):
        process = None
        q = None  # initialise here so finally block is always safe
        current_url: str | None = None

        try:
            process, q = start_subprocess(cmd)
            write_pid_file(args.port, process.pid)

            while process.poll() is None:
                try:
                    line = q.get(timeout=0.1).strip()
                except Empty:
                    continue

                if not args.silent and not args.json:
                    log.info(line)

                if is_connected_signal(line):
                    if not args.json:
                        print("\n\033[92m[CONNECTED] Tunnel is active\033[0m", flush=True)

                    url = extract_url(line)
                    if url and url != current_url:
                        current_url = url
                        if args.json:
                            print(json.dumps({"status": "connected", "url": url}), flush=True)
                        else:
                            print(f"\n\033[92m[URL] {url}\033[0m", flush=True)
                        if not args.no_open and not args.json:
                            webbrowser.open(url)

        except KeyboardInterrupt:
            log.info("Interrupted by user")
            break

        except Exception as exc:
            log.error("Unexpected error: %s", exc)

        finally:
            safe_terminate(process)
            remove_pid_file(args.port)
            if q is not None:
                drain_queue(q)
            current_url = None

        if attempt < MAX_RESTARTS:
            log.warning("Restarting tunnel (%d/%d)...", attempt, MAX_RESTARTS)
            time.sleep(RESTART_DELAY_S)

    return 0


if __name__ == "__main__":
    # Standalone entry point for the tunnel-forge-cli binary — no GUI/PyQt6
    # dependency involved. Always runs in CLI mode regardless of --cli.
    sys.exit(run_cli(build_arg_parser().parse_args()))
