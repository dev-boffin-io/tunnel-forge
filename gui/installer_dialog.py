# file: gui/installer_dialog.py
"""
InstallerDialog
===============
GUI dialog for first-time install and update of the cloudflared binary.
Also allows the user to set a custom path to an existing cloudflared binary.
All network/disk work runs on a background QThread — the window never freezes.
"""

from __future__ import annotations

from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtGui import QTextCursor
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)

from core.installer import (
    download_and_install,
    get_installed_version,
    get_latest_version,
    is_update_available,
)
from utils.logger import get_logger
from utils.paths import (
    get_cloudflared_path,
    get_custom_cloudflared_path,
    set_custom_cloudflared_path,
)

log = get_logger("installer_dialog")

_STYLE = (
    "QDialog,QWidget{background:#0D1117;color:#c9d1d9;font-size:17px;}"
    "QLabel{font-size:17px;color:#c9d1d9;}"
    "QProgressBar{background:#21262d;border:1px solid #30363d;border-radius:6px;"
    "height:22px;text-align:center;color:#c9d1d9;}"
    "QProgressBar::chunk{background:#238636;border-radius:5px;}"
    "QTextEdit{background:#010409;color:#8b949e;border:1px solid #21262d;"
    "border-radius:6px;font-family:'Consolas','Courier New',monospace;font-size:14px;}"
    "QPushButton{background:#21262d;color:white;border-radius:8px;"
    "padding:10px 22px;font-size:17px;}"
    "QPushButton:hover{background:#30363d;}"
    "QPushButton:disabled{color:#484f58;}"
    "QLineEdit{background:#010409;color:#c9d1d9;"
    "border:1px solid #30363d;border-radius:6px;padding:8px 12px;font-size:15px;}"
)


# ── Workers ───────────────────────────────────────────────────────────────────

class _InstallWorker(QThread):
    log_signal:      pyqtSignal = pyqtSignal(str, str)   # (message, colour)
    progress_signal: pyqtSignal = pyqtSignal(int, int)   # (downloaded, total)
    done_signal:     pyqtSignal = pyqtSignal(bool, str)  # (success, message)

    def run(self) -> None:
        try:
            path = download_and_install(
                progress_cb=lambda d, t: self.progress_signal.emit(d, t),
                log_cb=lambda m: self.log_signal.emit(m, "#c9d1d9"),
            )
            self.done_signal.emit(True, path)
        except Exception as exc:
            self.log_signal.emit(f"❌ {exc}", "#f85149")
            self.done_signal.emit(False, str(exc))


class _CheckWorker(QThread):
    """Checks installed/latest version off the GUI thread."""
    result_signal: pyqtSignal = pyqtSignal(bool, str, str)  # (available, installed, latest)

    def run(self) -> None:
        available, installed, latest = is_update_available()
        self.result_signal.emit(
            available,
            installed or "not installed",
            latest    or "unknown",
        )


# ── Dialog ────────────────────────────────────────────────────────────────────

class InstallerDialog(QDialog):
    """
    Shows current / latest version and lets the user install or update
    cloudflared with a single click.
    Also allows setting a custom path to an existing cloudflared binary.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("cloudflared — Install / Update")
        self.setMinimumWidth(700)
        self.setMinimumHeight(560)
        self.setStyleSheet(_STYLE)

        self._install_worker: _InstallWorker | None = None
        self._check_worker:   _CheckWorker  | None = None

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(24, 24, 24, 24)

        # ── Version info row ──────────────────────────────────────────────────
        self.version_label = QLabel("Checking versions…")
        layout.addWidget(self.version_label)

        # ── Custom path row ───────────────────────────────────────────────────
        path_label = QLabel("cloudflared path:")
        layout.addWidget(path_label)

        path_row = QHBoxLayout()
        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText(
            "Leave blank for auto-detect  (set manually if auto-detect fails)"
        )
        # Pre-fill with whatever is already configured or detected
        existing = get_custom_cloudflared_path() or ""
        self.path_edit.setText(existing)
        path_row.addWidget(self.path_edit)

        self.browse_btn = QPushButton("Browse…")
        self.browse_btn.setFixedWidth(120)
        self.browse_btn.clicked.connect(self._browse_binary)
        path_row.addWidget(self.browse_btn)

        self.save_path_btn = QPushButton("Apply")
        self.save_path_btn.setFixedWidth(90)
        self.save_path_btn.clicked.connect(self._apply_custom_path)
        path_row.addWidget(self.save_path_btn)

        layout.addLayout(path_row)

        # ── Detected path + action buttons row ───────────────────────────────
        detect_row = QHBoxLayout()

        self.detected_label = QLabel()
        self.detected_label.setStyleSheet("font-size:14px;font-weight:bold;")
        self._refresh_detected_label()
        detect_row.addWidget(self.detected_label, stretch=1)

        self.detect_btn = QPushButton("🔍 Detect")
        self.detect_btn.setFixedWidth(110)
        self.detect_btn.setToolTip("Re-scan for cloudflared binary")
        self.detect_btn.clicked.connect(self._on_detect_clicked)
        detect_row.addWidget(self.detect_btn)

        self.check_ver_btn = QPushButton("⟳ Check Version")
        self.check_ver_btn.setFixedWidth(170)
        self.check_ver_btn.setToolTip("Fetch installed & latest version")
        self.check_ver_btn.clicked.connect(self._start_version_check)
        detect_row.addWidget(self.check_ver_btn)

        layout.addLayout(detect_row)

        # ── Progress bar (hidden until download starts) ───────────────────────
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        self.progress.setRange(0, 100)
        layout.addWidget(self.progress)

        # ── Log box ───────────────────────────────────────────────────────────
        self._log_box = QTextEdit()
        self._log_box.setReadOnly(True)
        layout.addWidget(self._log_box)

        # ── Buttons ───────────────────────────────────────────────────────────
        btns = QDialogButtonBox()
        self.install_btn = btns.addButton(
            "Install / Update", QDialogButtonBox.ButtonRole.AcceptRole
        )
        self.close_btn = btns.addButton(
            "Close", QDialogButtonBox.ButtonRole.RejectRole
        )
        self.install_btn.setEnabled(False)
        self.install_btn.clicked.connect(self._start_install)
        self.close_btn.clicked.connect(self.reject)
        layout.addWidget(btns)

        # Kick off version check immediately
        self._start_version_check()

    # ── Custom path helpers ───────────────────────────────────────────────────

    def _refresh_detected_label(self) -> None:
        p = get_cloudflared_path()
        if p:
            self.detected_label.setStyleSheet(
                "font-size:14px;font-weight:bold;color:#e3b341;"
            )
            self.detected_label.setText(f"✔ Detected: {p}")
        else:
            self.detected_label.setStyleSheet(
                "font-size:14px;font-weight:bold;color:#f85149;"
            )
            self.detected_label.setText("✗ Not found — install or set path manually")

    def _on_detect_clicked(self) -> None:
        self._refresh_detected_label()
        p = get_cloudflared_path()
        if p:
            self._log(f"🔍 Detected: {p}", "#e3b341")
        else:
            self._log("🔍 cloudflared not found on any known path.", "#f85149")

    def _browse_binary(self) -> None:
        import os
        if os.name == "nt":
            filt = "cloudflared binary (cloudflared.exe);;All files (*)"
        else:
            filt = "cloudflared binary (cloudflared);;All files (*)"

        path, _ = QFileDialog.getOpenFileName(
            self, "Select cloudflared binary", "", filt
        )
        if path:
            self.path_edit.setText(path)

    def _apply_custom_path(self) -> None:
        raw = self.path_edit.text().strip()
        if raw:
            import os
            if not os.path.isfile(raw):
                self._log(f"⚠️  File not found: {raw}", "#e3b341")
                return
            set_custom_cloudflared_path(raw)
            self._log(f"✅ Custom path saved: {raw}", "#3fb950")
        else:
            set_custom_cloudflared_path(None)
            self._log("ℹ️  Custom path cleared — using auto-detect.", "#58a6ff")

        self._refresh_detected_label()
        # Re-check version with new path
        self._start_version_check()

    # ── Logging helper ────────────────────────────────────────────────────────

    def _log(self, msg: str, color: str = "#c9d1d9") -> None:
        self._log_box.append(f"<span style='color:{color};'>{msg}</span>")
        self._log_box.moveCursor(QTextCursor.MoveOperation.End)

    # ── Version check ─────────────────────────────────────────────────────────

    def _start_version_check(self) -> None:
        self._log("🔍 Checking versions…", "#e3b341")
        self._check_worker = _CheckWorker()
        self._check_worker.result_signal.connect(self._on_version_checked)
        self._check_worker.start()

    def _on_version_checked(self, available: bool, installed: str, latest: str) -> None:
        self.version_label.setText(
            f"Installed: <b>{installed}</b>    Latest: <b>{latest}</b>"
        )
        if available:
            self._log(
                f"⬆️  Update available: {installed} → {latest}", "#3fb950"
            )
            self.install_btn.setText("Update Now")
        elif installed == "not installed":
            self._log("cloudflared is not installed.", "#e3b341")
            self.install_btn.setText("Install Now")
        else:
            self._log(f"✅ cloudflared {installed} is up to date.", "#3fb950")
            self.install_btn.setText("Re-install")

        self.install_btn.setEnabled(True)
        self._check_worker = None

    # ── Install / update ──────────────────────────────────────────────────────

    def _start_install(self) -> None:
        self.install_btn.setEnabled(False)
        self.progress.setValue(0)
        self.progress.setVisible(True)
        self._log_box.clear()
        self._log("⬇️  Starting download…", "#58a6ff")

        self._install_worker = _InstallWorker()
        self._install_worker.log_signal.connect(self._log)
        self._install_worker.progress_signal.connect(self._on_progress)
        self._install_worker.done_signal.connect(self._on_done)
        self._install_worker.start()

    def _on_progress(self, downloaded: int, total: int) -> None:
        if total > 0:
            pct = int(downloaded * 100 / total)
            self.progress.setValue(pct)
            mb_done  = downloaded / 1_048_576
            mb_total = total      / 1_048_576
            self.progress.setFormat(f"{mb_done:.1f} / {mb_total:.1f} MB  ({pct}%)")

    def _on_done(self, success: bool, message: str) -> None:
        self.progress.setVisible(False)
        self.install_btn.setEnabled(True)
        if success:
            self._log(f"🎉 Done! Binary installed at:\n{message}", "#3fb950")
            self.install_btn.setText("Re-install")
            self._refresh_detected_label()
            self._start_version_check()
        else:
            self._log(f"❌ Installation failed: {message}", "#f85149")
        self._install_worker = None

    # ── Prevent closing while installing ─────────────────────────────────────

    def reject(self) -> None:
        if self._install_worker and self._install_worker.isRunning():
            self._log("⚠️  Download in progress, please wait…", "#e3b341")
            return
        super().reject()
