# ─────────────────────────────────────────────────────────────────────────────
#  TunnelForge — Makefile
#  Targets: all · build · install · uninstall · clean · help
# ─────────────────────────────────────────────────────────────────────────────

APP     := tunnel-forge
SRC     := main.py
ICON    := assets/tunnel-forge.png

CLI_APP := tunnel-forge-cli
CLI_SRC := cli.py

BIN_DIR   := ./bin
BINARY    := $(BIN_DIR)/$(APP)
CLI_BINARY := $(BIN_DIR)/$(CLI_APP)

VENV      := .venv
VENV_BIN  := $(VENV)/bin

BUILD_DIR := .build
SPEC_DIR  := .spec

PYTHON := $(shell command -v python3 2>/dev/null || command -v python 2>/dev/null)

# Resolve absolute paths at make-time so PyInstaller always gets correct paths
# regardless of where specpath points.
CURDIR_ABS := $(shell pwd)
ICON_ABS   := $(shell [ -f $(ICON) ] && \
	(realpath $(ICON) 2>/dev/null || readlink -f $(ICON) 2>/dev/null || echo $(CURDIR_ABS)/$(ICON)))
CORE_ABS   := $(CURDIR_ABS)/core
GUI_ABS    := $(CURDIR_ABS)/gui
UTILS_ABS  := $(CURDIR_ABS)/utils
SRC_ABS    := $(CURDIR_ABS)/$(SRC)
CLI_SRC_ABS := $(CURDIR_ABS)/$(CLI_SRC)

# PyInstaller path separator (: on Linux/macOS, ; on Windows)
SEP := :

# Pass DEBUG=1 for verbose PyInstaller output
DEBUG ?= 0

# Install locations
PREFIX      ?= $(HOME)/.local
BIN_INSTALL := $(PREFIX)/bin
DESKTOP_DIR := $(HOME)/.local/share/applications

.PHONY: all build clean install uninstall check-python check-venv-pkg help

all: build

# ─── Help ────────────────────────────────────────────────────────────────────

help:
	@echo ""
	@echo "  TunnelForge — available targets"
	@echo ""
	@echo "  make build      Build the binaries → $(BINARY) & $(CLI_BINARY)"
	@echo "  make install    Install symlink + desktop entry (requires build first)"
	@echo "  make uninstall  Remove installed files"
	@echo "  make clean      Remove build artifacts"
	@echo "  make help       Show this message"
	@echo ""
	@echo "  Options:"
	@echo "  DEBUG=1         Verbose PyInstaller output (make build DEBUG=1)"
	@echo "  PREFIX=<path>   Install prefix (default: ~/.local)"
	@echo ""

# ─── Sanity checks ───────────────────────────────────────────────────────────

check-python:
	@if [ -z "$(PYTHON)" ]; then \
		echo "❌ python not found"; exit 1; \
	fi
	@echo "✅ Python: $(PYTHON) ($$($(PYTHON) --version 2>&1))"

check-venv-pkg: check-python
	@if ! $(PYTHON) -m venv --help > /dev/null 2>&1; then \
		echo "❌ python3-venv missing. Install it with:"; \
		echo "   sudo apt install python3-venv"; \
		exit 1; \
	fi
	@echo "✅ venv module OK"

# ─── Virtual environment ─────────────────────────────────────────────────────

$(VENV): check-venv-pkg
	@rm -rf $(VENV)
	@echo "📦 Creating virtualenv..."
	@$(PYTHON) -m venv $(VENV)
	@$(VENV_BIN)/pip install --quiet --upgrade pip pyinstaller
	@if [ -f requirements.txt ]; then \
		echo "📥 Installing dependencies..."; \
		$(VENV_BIN)/pip install --quiet -r requirements.txt; \
	else \
		echo "⚠️  No requirements.txt found — skipping"; \
	fi
	@echo "✅ venv ready"

# ─── Build ───────────────────────────────────────────────────────────────────

build: $(VENV)
	@rm -f $(BINARY) $(CLI_BINARY)
	@mkdir -p $(BIN_DIR)
	@echo "🔨 Building $(APP) (GUI + CLI)..."
	@$(VENV_BIN)/pyinstaller \
		--onefile \
		--strip \
		$(if $(filter 1,$(DEBUG)),--log-level DEBUG,) \
		--name $(APP) \
		--distpath $(CURDIR_ABS)/$(BIN_DIR) \
		--workpath $(CURDIR_ABS)/$(BUILD_DIR) \
		--specpath $(CURDIR_ABS)/$(SPEC_DIR) \
		--hidden-import PyQt6.QtNetwork \
		--hidden-import PyQt6.sip \
		$(if $(ICON_ABS),--add-data "$(ICON_ABS)$(SEP)assets",) \
		--add-data "$(CORE_ABS)$(SEP)core" \
		--add-data "$(GUI_ABS)$(SEP)gui" \
		--add-data "$(UTILS_ABS)$(SEP)utils" \
		$(SRC_ABS)
	@echo "🔨 Building $(CLI_APP) (CLI-only, no PyQt6)..."
	@$(VENV_BIN)/pyinstaller \
		--onefile \
		--strip \
		$(if $(filter 1,$(DEBUG)),--log-level DEBUG,) \
		--name $(CLI_APP) \
		--distpath $(CURDIR_ABS)/$(BIN_DIR) \
		--workpath $(CURDIR_ABS)/$(BUILD_DIR) \
		--specpath $(CURDIR_ABS)/$(SPEC_DIR) \
		--hidden-import psutil \
		--hidden-import colorama \
		--add-data "$(CORE_ABS)$(SEP)core" \
		--add-data "$(UTILS_ABS)$(SEP)utils" \
		$(CLI_SRC_ABS)
	@rm -rf $(VENV) $(BUILD_DIR) $(SPEC_DIR) \
		__pycache__ core/__pycache__ gui/__pycache__ utils/__pycache__ \
		*.pyc *.pyo *.spec
	@echo "✅ Built → $(BINARY)"
	@echo "✅ Built → $(CLI_BINARY)"

# ─── Install (requires a built binary — does NOT rebuild) ────────────────────

install:
	@echo "📦 Installing $(APP)..."
	@if [ ! -f "$(BINARY)" ]; then \
		echo "❌ Binary not found at $(BINARY). Run 'make build' first."; \
		exit 1; \
	fi
	@if [ ! -f "$(CLI_BINARY)" ]; then \
		echo "❌ Binary not found at $(CLI_BINARY). Run 'make build' first."; \
		exit 1; \
	fi
	@mkdir -p $(BIN_INSTALL)
	@BINARY_ABS=$$(realpath $(BINARY) 2>/dev/null || readlink -f $(BINARY) 2>/dev/null || echo $(CURDIR_ABS)/$(BINARY)); \
		ln -sf "$$BINARY_ABS" $(BIN_INSTALL)/$(APP)
	@echo "✅ Symlink → $(BIN_INSTALL)/$(APP)"
	@CLI_BINARY_ABS=$$(realpath $(CLI_BINARY) 2>/dev/null || readlink -f $(CLI_BINARY) 2>/dev/null || echo $(CURDIR_ABS)/$(CLI_BINARY)); \
		ln -sf "$$CLI_BINARY_ABS" $(BIN_INSTALL)/$(CLI_APP)
	@echo "✅ Symlink → $(BIN_INSTALL)/$(CLI_APP)"
	@mkdir -p $(DESKTOP_DIR)
	@printf '[Desktop Entry]\nName=Tunnel Forge\nExec="%s"\nType=Application\nTerminal=false\nCategories=Network;Utility;\n%s\n' \
		"$(BIN_INSTALL)/$(APP)" \
		"$(if $(ICON_ABS),Icon=$(ICON_ABS),)" \
		> $(DESKTOP_DIR)/$(APP).desktop
	@chmod 644 $(DESKTOP_DIR)/$(APP).desktop
	@echo "✅ Desktop entry → $(DESKTOP_DIR)/$(APP).desktop"
	@if ! echo "$$PATH" | grep -q "$(BIN_INSTALL)"; then \
		echo "⚠️  $(BIN_INSTALL) is not in PATH."; \
		echo "   Add this to ~/.bashrc or ~/.profile:"; \
		echo '   export PATH="$$HOME/.local/bin:$$PATH"'; \
	fi
	@echo "🚀 Install complete. Run: $(APP)"

# ─── Uninstall ───────────────────────────────────────────────────────────────

uninstall:
	@echo "🗑️  Removing $(APP)..."
	@rm -f $(BIN_INSTALL)/$(APP)
	@rm -f $(BIN_INSTALL)/$(CLI_APP)
	@rm -f $(DESKTOP_DIR)/$(APP).desktop
	@echo "✅ Uninstalled"

# ─── Clean ───────────────────────────────────────────────────────────────────

clean:
	@rm -rf $(BIN_DIR) $(VENV) $(BUILD_DIR) $(SPEC_DIR) \
		__pycache__ core/__pycache__ gui/__pycache__ utils/__pycache__ \
		*.pyc *.pyo *.spec
	@echo "🧹 Clean done"
