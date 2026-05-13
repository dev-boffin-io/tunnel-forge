# file: gui/setup_dialog.py

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtGui import QTextCursor
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QLineEdit,
    QTextEdit,
    QVBoxLayout,
)

from core.cloudflared import CloudflaredRunner
from core.config import ConfigManager
from core.parser import extract_tunnel_id
from utils.logger import get_logger
from utils.paths import get_cloudflared_path

log = get_logger("setup_dialog")

_STYLE = (
    "QDialog,QWidget{background:#0D1117;color:#c9d1d9;font-size:17px;}"
    "QLabel{font-size:17px;color:#c9d1d9;}"
    "QLineEdit{background:#010409;color:#c9d1d9;border:1px solid #30363d;"
    "border-radius:6px;padding:8px 12px;font-size:17px;}"
    "QTextEdit{background:#010409;color:#8b949e;border:1px solid #21262d;"
    "border-radius:6px;font-family:'Consolas','Courier New',monospace;font-size:14px;}"
    "QPushButton{background:#21262d;color:white;border-radius:8px;"
    "padding:10px 22px;font-size:17px;}"
    "QPushButton:hover{background:#30363d;}"
)


class _SetupWorker(QThread):
    """
    Runs the cloudflared setup steps off the GUI thread so the window
    never freezes during login / tunnel create / route DNS.

    Signals
    -------
    log_signal  — (message, colour) to append to the log box
    done_signal — emitted when the workflow finishes (success or failure)
    """

    log_signal:  pyqtSignal = pyqtSignal(str, str)
    done_signal: pyqtSignal = pyqtSignal(bool)   # True = success

    def __init__(
        self,
        runner: CloudflaredRunner,
        binary: str,
        domain: str,
        name: str,
        port: str,
    ) -> None:
        super().__init__()
        self._runner = runner
        self._binary = binary
        self.domain  = domain
        self.name    = name
        self.port    = port

    def _log(self, msg: str, color: str = "#c9d1d9") -> None:
        self.log_signal.emit(msg, color)

    def _step(self, args: list[str], label: str) -> tuple[bool, str]:
        self._log(f"▶ {label}...", "#e3b341")
        ok, out = self._runner.run_once(args, label)
        if ok:
            self._log(f"✅ {label} OK", "#3fb950")
            if out:
                self._log(out, "#8b949e")
        else:
            self._log(f"❌ {label} failed:\n{out}", "#f85149")
        return ok, out

    def run(self) -> None:
        binary = self._binary

        # Step 1: login
        ok, _ = self._step([binary, "tunnel", "login"], "Login")
        if not ok:
            self.done_signal.emit(False)
            return

        # Step 2: create tunnel
        ok, out = self._step(
            [binary, "tunnel", "create", self.name],
            f"Create tunnel '{self.name}'",
        )
        if not ok:
            self.done_signal.emit(False)
            return

        tunnel_id = extract_tunnel_id(out) or self.name

        # Step 3: route DNS
        ok, _ = self._step(
            [binary, "tunnel", "route", "dns", self.name, self.domain],
            f"Route DNS {self.domain} → {self.name}",
        )
        if not ok:
            self.done_signal.emit(False)
            return

        # Step 4: generate config.yml
        try:
            cfg_path, cfg_str = ConfigManager.generate(
                tunnel_id, self.name, self.domain, self.port
            )
            self._log(f"📝 Config generated → {cfg_path}", "#58a6ff")
            self._log(cfg_str, "#8b949e")
        except Exception as exc:
            self._log(f"⚠️  Config generation failed: {exc}", "#e3b341")

        self._log("✅ Setup complete! Switch to Custom Domain mode to launch.", "#3fb950")
        self.done_signal.emit(True)


class SetupDialog(QDialog):
    """
    One-click custom domain setup:
      login → create tunnel → route DNS → generate config.yml

    All blocking cloudflared calls run on a background QThread so the
    dialog (and the rest of the GUI) stays responsive throughout.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Setup Custom Domain")
        self.setMinimumWidth(700)
        self.setMinimumHeight(560)
        self.setStyleSheet(_STYLE)

        self._runner = CloudflaredRunner()
        self._worker: Optional[_SetupWorker] = None

        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(24, 24, 24, 24)

        layout.addWidget(QLabel("Domain (e.g. app.yourdomain.com):"))
        self.domain_input = QLineEdit()
        self.domain_input.setFixedHeight(46)
        self.domain_input.setPlaceholderText("app.yourdomain.com")
        layout.addWidget(self.domain_input)

        layout.addWidget(QLabel("Tunnel name:"))
        self.name_input = QLineEdit()
        self.name_input.setFixedHeight(46)
        self.name_input.setPlaceholderText("my-tunnel")
        layout.addWidget(self.name_input)

        layout.addWidget(QLabel("Port:"))
        self.port_input = QLineEdit("3000")
        self.port_input.setFixedHeight(46)
        layout.addWidget(self.port_input)

        self._log_box = QTextEdit()
        self._log_box.setReadOnly(True)
        self._log_box.setStyleSheet(
            "background:#010409; color:#8b949e; font-family:'Consolas'; font-size:12px;"
        )
        layout.addWidget(self._log_box)

        btns = QDialogButtonBox()
        self.run_btn   = btns.addButton("Run Setup", QDialogButtonBox.ButtonRole.AcceptRole)
        self.close_btn = btns.addButton("Close",     QDialogButtonBox.ButtonRole.RejectRole)
        self.run_btn.clicked.connect(self._run_setup)
        self.close_btn.clicked.connect(self.reject)
        layout.addWidget(btns)

    def _log(self, msg: str, color: str = "#c9d1d9") -> None:
        self._log_box.append(f"<span style='color:{color};'>{msg}</span>")
        self._log_box.moveCursor(QTextCursor.MoveOperation.End)

    def _run_setup(self) -> None:
        domain = self.domain_input.text().strip()
        name   = self.name_input.text().strip()
        port   = self.port_input.text().strip()

        if not domain or not name or not port.isdigit():
            self._log("❌ Fill all fields correctly.", "#f85149")
            return

        self._log_box.clear()
        self.run_btn.setEnabled(False)

        if not self._runner.is_available():
            self._log("❌ cloudflared not found!", "#f85149")
            self.run_btn.setEnabled(True)
            return

        self._worker = _SetupWorker(
            runner=self._runner,
            binary=self._runner.binary,
            domain=domain,
            name=name,
            port=port,
        )
        self._worker.log_signal.connect(self._log)
        self._worker.done_signal.connect(self._on_done)
        self._worker.start()

    def _on_done(self, _success: bool) -> None:
        self.run_btn.setEnabled(True)
        self._worker = None

    def reject(self) -> None:
        if self._worker and self._worker.isRunning():
            self._log("⚠️  Setup is running, please wait...", "#e3b341")
            return
        super().reject()
