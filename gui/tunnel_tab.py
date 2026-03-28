# file: gui/tunnel_tab.py

from __future__ import annotations

import os
import webbrowser
from typing import Optional

from PyQt6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QStackedWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)
from PyQt6.QtWidgets import QApplication

from constants import URL_REGEX
from core.cloudflared import TunnelManager
from core.network import is_service_running
from core.parser import normalize_hostname
from gui.worker import WorkerThread
from utils.logger import get_logger
from utils.paths import get_cloudflared_path

log = get_logger("tunnel_tab")


class TunnelTab(QWidget):
    """
    A self-contained tunnel control panel rendered as a tab.
    Each tab manages its own WorkerThread independently.
    """

    def __init__(self, port: int, tab_index: int) -> None:
        super().__init__()
        self.worker:    Optional[WorkerThread] = None
        self.last_url:  Optional[str]          = None
        self.tab_index: int                    = tab_index
        self._all_log_lines: list[tuple[str, str]] = []

        self._manager = TunnelManager()
        self._build_ui(port)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self, port: int) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(18)
        root.setContentsMargins(24, 24, 24, 24)

        # ── Port row ──────────────────────────────────────────────────
        port_row = QHBoxLayout()
        port_row.setSpacing(14)
        port_lbl = QLabel("Port:")
        port_lbl.setStyleSheet("font-size:18px; font-weight:600; color:#c9d1d9;")
        self.port_input = QLineEdit(str(port))
        self.port_input.setFixedWidth(140)
        self.port_input.setFixedHeight(46)
        self.auto_open_check = QCheckBox("Auto Open")
        self.auto_open_check.setChecked(True)
        self.auto_open_check.setStyleSheet("font-size:17px;")
        port_row.addWidget(port_lbl)
        port_row.addWidget(self.port_input)
        port_row.addSpacing(16)
        port_row.addWidget(self.auto_open_check)
        port_row.addStretch()
        root.addLayout(port_row)

        # ── Mode selector ─────────────────────────────────────────────
        mode_box    = QGroupBox("Tunnel Mode")
        mode_layout = QHBoxLayout(mode_box)
        mode_layout.setSpacing(40)
        mode_layout.setContentsMargins(20, 16, 20, 16)
        self.radio_quick  = QRadioButton("🚀  Quick Tunnel")
        self.radio_custom = QRadioButton("🔑  Custom Domain")
        self.radio_quick.setStyleSheet("font-size:17px;")
        self.radio_custom.setStyleSheet("font-size:17px;")
        self.radio_quick.setChecked(True)
        self._mode_group = QButtonGroup()
        self._mode_group.addButton(self.radio_quick,  0)
        self._mode_group.addButton(self.radio_custom, 1)
        mode_layout.addWidget(self.radio_quick)
        mode_layout.addWidget(self.radio_custom)
        mode_layout.addStretch()
        root.addWidget(mode_box)

        # ── Stacked panels ────────────────────────────────────────────
        self.stack = QStackedWidget()

        quick_panel = QWidget()
        ql = QVBoxLayout(quick_panel)
        ql.setContentsMargins(4, 10, 4, 10)
        lbl = QLabel("Cloudflare assigns a random public URL. No account required.")
        lbl.setStyleSheet("color:#8b949e; font-size:16px; padding:8px 4px;")
        ql.addWidget(lbl)
        self.stack.addWidget(quick_panel)

        custom_panel = QWidget()
        cl = QVBoxLayout(custom_panel)
        cl.setSpacing(14)
        cl.setContentsMargins(4, 10, 4, 10)

        LABEL_W = 150

        def _field_row(label_text: str) -> tuple[QHBoxLayout, QLabel, QLineEdit]:
            row = QHBoxLayout()
            row.setSpacing(14)
            lbl = QLabel(label_text)
            lbl.setFixedWidth(LABEL_W)
            lbl.setStyleSheet("font-size:17px; color:#c9d1d9;")
            field = QLineEdit()
            field.setFixedHeight(46)
            row.addWidget(lbl)
            row.addWidget(field)
            return row, lbl, field

        r1, _, self.tunnel_name_input = _field_row("Tunnel name:")
        self.tunnel_name_input.setPlaceholderText("my-tunnel")
        cl.addLayout(r1)

        r2, _, self.hostname_input = _field_row("Hostname:")
        self.hostname_input.setPlaceholderText("app.yourdomain.com  (optional)")
        cl.addLayout(r2)

        r3 = QHBoxLayout()
        r3.setSpacing(14)
        cfg_lbl = QLabel("Config:")
        cfg_lbl.setFixedWidth(LABEL_W)
        cfg_lbl.setStyleSheet("font-size:17px; color:#c9d1d9;")
        self.config_path_input = QLineEdit()
        self.config_path_input.setFixedHeight(46)
        self.config_path_input.setPlaceholderText("~/.cloudflared/config.yml  (optional)")
        browse_btn = QPushButton("Browse")
        browse_btn.setFixedWidth(110)
        browse_btn.setFixedHeight(46)
        browse_btn.clicked.connect(self._browse_config)
        r3.addWidget(cfg_lbl)
        r3.addWidget(self.config_path_input)
        r3.addWidget(browse_btn)
        cl.addLayout(r3)

        hint = QLabel("ℹ️  Use 'Setup Custom Domain' button for one-click setup.")
        hint.setStyleSheet("color:#6e7681; font-size:15px; padding:6px 2px;")
        cl.addWidget(hint)
        self.stack.addWidget(custom_panel)

        self._mode_group.idToggled.connect(
            lambda id_, checked: self.stack.setCurrentIndex(id_) if checked else None
        )
        root.addWidget(self.stack)

        # ── Status label ──────────────────────────────────────────────
        self.status_label = QLabel("⚪  Idle")
        self.status_label.setStyleSheet(
            "color:#8b949e; font-size:17px; font-weight:600;"
            "padding:8px 12px; border:1px solid #21262d; border-radius:6px;"
        )
        root.addWidget(self.status_label)

        # ── Action buttons ────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.setSpacing(16)
        self.btn      = QPushButton("LAUNCH TUNNEL")
        self.copy_btn = QPushButton("COPY URL")
        self.btn.setFixedHeight(56)
        self.copy_btn.setFixedHeight(56)
        self.btn.setStyleSheet(
            "QPushButton{background:#238636;color:white;font-size:18px;"
            "font-weight:700;border-radius:8px;}"
            "QPushButton:hover{background:#2ea043;}"
            "QPushButton:disabled{background:#21262d;color:#484f58;}"
        )
        self.copy_btn.setStyleSheet(
            "QPushButton{background:#21262d;color:#c9d1d9;font-size:17px;border-radius:8px;}"
            "QPushButton:hover{background:#30363d;}"
            "QPushButton:disabled{color:#484f58;}"
        )
        self.copy_btn.setEnabled(False)
        btn_row.addWidget(self.btn, 3)
        btn_row.addWidget(self.copy_btn, 1)
        root.addLayout(btn_row)

        # ── Log filter ────────────────────────────────────────────────
        filter_row = QHBoxLayout()
        filter_row.setSpacing(12)
        filter_lbl = QLabel("Logs:")
        filter_lbl.setStyleSheet("font-size:17px; color:#8b949e;")
        self.log_filter = QComboBox()
        self.log_filter.setFixedHeight(42)
        self.log_filter.setFixedWidth(200)
        self.log_filter.addItems(["All", "URLs only", "Errors only"])
        self.log_filter.currentIndexChanged.connect(self._refilter_logs)
        filter_row.addWidget(filter_lbl)
        filter_row.addWidget(self.log_filter)
        filter_row.addStretch()
        root.addLayout(filter_row)

        self.console = QTextBrowser()
        self.console.setStyleSheet(
            "QTextBrowser{background:#010409;color:#8b949e;"
            "font-family:'Consolas','Courier New',monospace;font-size:14px;"
            "border:1px solid #21262d;border-radius:8px;padding:10px;}"
        )
        root.addWidget(self.console)

        self.btn.clicked.connect(self.toggle)
        self.copy_btn.clicked.connect(self.copy_url)

    # ------------------------------------------------------------------
    # Log management
    # ------------------------------------------------------------------

    def _append_log(self, html_line: str, raw_line: str) -> None:
        self._all_log_lines.append((html_line, raw_line))
        self._apply_filter(html_line, raw_line)

    def _apply_filter(self, html_line: str, raw_line: str) -> None:
        f = self.log_filter.currentText()
        if f == "All":
            self.console.append(html_line)
        elif f == "URLs only":
            if URL_REGEX.search(raw_line):
                self.console.append(html_line)
        elif f == "Errors only":
            if any(w in raw_line.upper() for w in ("ERR", "FAIL", "ERROR", "WARN")):
                self.console.append(html_line)

    def _refilter_logs(self) -> None:
        self.console.clear()
        for html_line, raw_line in self._all_log_lines:
            self._apply_filter(html_line, raw_line)

    # ------------------------------------------------------------------
    # UI helpers
    # ------------------------------------------------------------------

    def _browse_config(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select config.yml",
            os.path.expanduser("~/.cloudflared"),
            "YAML files (*.yml *.yaml);;All files (*)",
        )
        if path:
            self.config_path_input.setText(path)

    def _set_status(self, text: str, color: str = "#8b949e") -> None:
        self.status_label.setText(text)
        self.status_label.setStyleSheet(
            f"color:{color}; font-size:12px; padding:2px 4px;"
        )

    def _reset_url(self) -> None:
        self.last_url = None
        self.copy_btn.setEnabled(False)

    # ------------------------------------------------------------------
    # Tunnel toggle
    # ------------------------------------------------------------------

    def toggle(self) -> None:
        if self.worker and self.worker.isRunning():
            self.btn.setText("STOPPING...")
            self.btn.setEnabled(False)
            self.worker.stop()
            self.worker.wait(3000)
            return

        port_txt = self.port_input.text().strip()
        if not port_txt.isdigit() or not (1 <= int(port_txt) <= 65535):
            QMessageBox.warning(self, "Port Error", "Invalid port (1–65535)")
            return

        if not is_service_running(int(port_txt)):
            QMessageBox.warning(
                self,
                "Server Not Found",
                f"No application on port {port_txt}.\n\nStart your server first.",
            )
            self._append_log(
                f"<span style='color:#f85149'>[ERR] Port {port_txt} idle.</span>",
                f"[ERR] Port {port_txt} idle.",
            )
            return

        cf_bin = get_cloudflared_path()
        if not cf_bin:
            QMessageBox.critical(self, "Error", "cloudflared not found!")
            return

        static_url: Optional[str] = None
        mode_label  = ""

        try:
            if self.radio_custom.isChecked():
                tunnel_name = self.tunnel_name_input.text().strip()
                if not tunnel_name:
                    QMessageBox.warning(self, "Missing", "Enter a tunnel name.")
                    return

                config_path = self.config_path_input.text().strip() or None
                if config_path and not os.path.exists(config_path):
                    QMessageBox.warning(
                        self, "File Not Found", f"Config file not found:\n{config_path}"
                    )
                    return

                hostname = self.hostname_input.text().strip()
                if hostname:
                    static_url = f"https://{normalize_hostname(hostname)}"

                cmd = self._manager.build_command(
                    "custom", port_txt,
                    tunnel_name=tunnel_name,
                    config_path=config_path,
                )
                mode_label = f"custom domain via <b>{tunnel_name}</b>"
            else:
                cmd = self._manager.build_command("quick", port_txt)
                mode_label = "quick tunnel"

        except (ValueError, RuntimeError) as exc:
            QMessageBox.critical(self, "Error", str(exc))
            return

        self._reset_url()
        self._all_log_lines.clear()
        self.console.clear()
        self._append_log(
            f"<span style='color:#3fb950'>[OK] Starting {mode_label} on port {port_txt}...</span>",
            f"[OK] Starting on port {port_txt}",
        )
        self._set_status("🟡 Connecting...", "#e3b341")
        self.btn.setText("FORGING...")
        self.btn.setEnabled(False)

        self.worker = WorkerThread(cmd, static_url=static_url)
        self.worker.log_signal.connect(self._on_log)
        self.worker.url_signal.connect(self._on_url)
        self.worker.connected_signal.connect(self._on_connected)
        self.worker.stopped_signal.connect(self._on_stopped)
        self.worker.start()

    # ------------------------------------------------------------------
    # Worker signal handlers
    # ------------------------------------------------------------------

    def _on_log(self, line: str) -> None:
        html = f"<span style='color:#8b949e;'>{line}</span>"
        self._append_log(html, line)

    def _on_connected(self) -> None:
        self._set_status("🟢 Connected", "#3fb950")

    def _on_url(self, url: str) -> None:
        self.btn.setText("STOP TUNNEL")
        self.btn.setEnabled(True)
        self.last_url = url
        self.copy_btn.setEnabled(True)
        self._set_status(f"🟢 {url}", "#3fb950")

        html = (
            f"<span style='color:#3fb950;'><b>[URL]</b> "
            f"<a href='{url}' style='color:#58a6ff;'>{url}</a></span>"
        )
        self._append_log(html, f"[URL] {url}")

        if self.auto_open_check.isChecked():
            webbrowser.open(url)

    def _on_stopped(self) -> None:
        self._reset_url()
        self.btn.setText("LAUNCH TUNNEL")
        self.btn.setEnabled(True)
        self._set_status("⚪ Idle")
        self._append_log(
            "<span style='color:#8b949e;'>[INFO] Tunnel stopped.</span>",
            "[INFO] Tunnel stopped.",
        )

    # ------------------------------------------------------------------
    # Copy URL
    # ------------------------------------------------------------------

    def copy_url(self) -> None:
        if self.last_url:
            QApplication.clipboard().setText(self.last_url)
            self._append_log(
                "<span style='color:#58a6ff;'>[INFO] URL copied.</span>",
                "[INFO] URL copied.",
            )
