# 🔥 tunnel-forge

> A `cloudflared` tunnel manager with a dark-themed PyQt6 GUI and a fully-featured CLI — part of the [Forge Suite](https://github.com/dev-boffin-io).

[![Version](https://img.shields.io/badge/version-3.0.0-blue?style=flat-square)](https://github.com/dev-boffin-io/tunnel-forge/releases)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue?style=flat-square&logo=python)](https://www.python.org/)
[![PyQt6](https://img.shields.io/badge/UI-PyQt6-green?style=flat-square)](https://pypi.org/project/PyQt6/)
[![License](https://img.shields.io/badge/license-MIT-lightgrey?style=flat-square)](LICENSE)

---

## Features

- **Dual-mode** — launches a PyQt6 GUI when a display is available, falls back to CLI automatically in headless / Termux environments
- **Quick tunnels** — zero-config `trycloudflare.com` URLs with auto-open in browser
- **Named / custom domain tunnels** — point `cloudflared` at an existing tunnel config
- **Auto-restart** — up to 3 restarts with configurable delay on unexpected exits
- **Single-instance guard** — raising an existing GUI window instead of opening a second one
- **JSON output mode** — machine-readable `{"status": "connected", "url": "..."}` for scripting and piping
- **Silent mode** — suppress all log noise when you only need the URL
- **PyInstaller build** — produces a single self-contained binary via `make build`
- **Desktop integration** — installs a `.desktop` entry and a `~/.local/bin` symlink via `make install`

---

## Requirements

| Dependency | Notes |
|---|---|
| `cloudflared` | Must be on `PATH`. [Install guide →](https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/install-and-setup/) |
| Python 3.10+ | `python3` or `python` |
| `PyQt6 >= 6.4.0` | GUI mode only |
| `PyYAML >= 6.0` | Config file parsing |
| `psutil >= 5.9.0` | Optional — enables PID-on-port detection in `core/network.py` |
| `python3-venv` | Required for `make build` |

> **Headless / Termux:** PyQt6 is not required if you always run with `--cli`.

---

## Installation

### Option A — run from source

```bash
git clone <repo-url>
cd tunnel-forge
pip install -r requirements.txt
python main.py --port 8080
```

### Option B — build a standalone binary

```bash
make build          # produces ./bin/tunnel-forge
make install        # symlinks to ~/.local/bin + writes .desktop entry
```

To uninstall:

```bash
make uninstall
```

---

## Usage

### GUI mode (default when `$DISPLAY` is set)

```bash
tunnel-forge
tunnel-forge --port 8080
```

### CLI mode

```bash
# Quick tunnel (random trycloudflare.com URL)
tunnel-forge --cli --port 3000

# Named tunnel with a custom domain
tunnel-forge --cli --tunnel-name my-tunnel --hostname myapp.example.com --config ~/.cloudflared/config.yml

# Machine-readable output
tunnel-forge --cli --port 3000 --json

# Headless / no browser open
tunnel-forge --cli --port 3000 --no-open --silent
```

### All flags

| Flag | Default | Description |
|---|---|---|
| `--port` | `3000` | Local port to expose |
| `--cli` | `false` | Force CLI mode (auto-set when `$DISPLAY` is absent) |
| `--no-open` | `false` | Do not auto-open the tunnel URL in the browser |
| `--json` | `false` | Emit structured JSON instead of human-readable log lines |
| `--tunnel-name` | — | Named tunnel identifier |
| `--hostname` | — | Custom hostname (displayed immediately for custom domain tunnels) |
| `--config` | — | Path to a `cloudflared` config YAML |
| `--silent` | `false` | Suppress `cloudflared` log output |

---

## Project Structure

```
tunnel-forge/
├── main.py            # Entry point — routes to GUI or CLI
├── cli.py             # CLI argument parser + run loop
├── constants.py       # Version, regex, restart / retry tuning
├── requirements.txt
├── Makefile
├── assets/
│   └── tunnel-forge.png
├── core/
│   ├── cloudflared.py # TunnelManager — binary detection, command builder
│   ├── config.py      # cloudflared YAML config helpers
│   ├── network.py     # Port-in-use checks, PID-on-port (psutil)
│   ├── parser.py      # URL extraction, connection signal detection
│   └── process.py     # Subprocess lifecycle, output queue drain
├── gui/
│   └── app.py         # TunnelForgeGUI (PyQt6, dark theme, single-instance)
└── utils/
    ├── logger.py      # Structured logger factory
    └── paths.py       # Asset path resolution (works inside PyInstaller bundle)
```

---

## Build targets

```
make build      Build the binary → ./bin/tunnel-forge
make install    Symlink + .desktop entry  (run after build)
make uninstall  Remove installed files
make clean      Remove build artefacts
make help       Show this message

Options:
  DEBUG=1        Verbose PyInstaller output   (make build DEBUG=1)
  PREFIX=<path>  Install prefix               (default: ~/.local)
```

---

## Part of the Forge Suite

| Tool | Description |
|---|---|
| **tunnel-forge** | Cloudflare tunnel manager (this project) |
| `qbit-forge` | qbittorrent-nox GUI manager |
| `cloud-forge` | rclone + SFTP GUI manager |
| `ollama-forge` | Ollama model manager |
| `virt-forge` | Virtualisation manager |

---

## License

MIT © [dev-boffin-io](https://github.com/dev-boffin-io)
