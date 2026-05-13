# file: gui/app.py

from __future__ import annotations

import os

from PyQt6.QtNetwork import QLocalServer, QLocalSocket
from PyQt6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QMainWindow,
    QMenu,
    QPushButton,
    QSystemTrayIcon,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from constants import APP_ID, VERSION
from gui.installer_dialog import InstallerDialog
from gui.setup_dialog import SetupDialog
from gui.tunnel_tab import TunnelTab
from utils.logger import get_logger
from utils.paths import get_icon_path

log = get_logger("app")

_STYLESHEET = (
    "QMainWindow,QWidget{background-color:#0D1117;color:#c9d1d9;font-size:17px;}"
    "QLabel{font-size:17px;color:#c9d1d9;}"
    "QTabWidget::pane{border:1px solid #30363d;}"
    "QTabBar::tab{background:#161b22;color:#8b949e;padding:10px 28px;"
    "border:1px solid #30363d;border-bottom:none;"
    "border-top-left-radius:4px;border-top-right-radius:4px;font-size:17px;}"
    "QTabBar::tab:selected{background:#0D1117;color:#c9d1d9;}"
    "QGroupBox{border:1px solid #30363d;border-radius:8px;"
    "margin-top:12px;padding-top:12px;color:#8b949e;font-size:17px;}"
    "QGroupBox::title{subcontrol-origin:margin;left:12px;padding:0 6px;font-size:17px;}"
    "QPushButton{background:#21262d;color:white;"
    "border-radius:8px;padding:10px 22px;font-size:17px;}"
    "QPushButton:hover{background:#30363d;}"
    "QLineEdit{background:#010409;color:#c9d1d9;"
    "border:1px solid #30363d;border-radius:6px;padding:8px 12px;font-size:17px;}"
    "QComboBox{background:#21262d;color:#c9d1d9;"
    "border:1px solid #30363d;border-radius:6px;padding:6px 12px;font-size:17px;}"
    "QComboBox QAbstractItemView{font-size:17px;background:#21262d;color:#c9d1d9;}"
    "QRadioButton,QCheckBox{color:#c9d1d9;font-size:17px;spacing:8px;}"
    "QTextBrowser{background:#010409;color:#8B949E;"
    "font-family:'Consolas','Courier New',monospace;font-size:14px;border:none;}"
    "QScrollBar:vertical{background:#0D1117;width:10px;}"
    "QScrollBar::handle:vertical{background:#30363d;border-radius:5px;}"
)


def _make_icon():
    """Fixed icon path handler for both dev and PyInstaller build."""
    from PyQt6.QtGui import QIcon
    from PyQt6.QtWidgets import QApplication

    p = get_icon_path()

    # পাথ ফিক্স + existence চেক
    if p and os.path.exists(p):
        log.debug("✅ Using custom tray/window icon: %s", p)
        return QIcon(p)

    # যদি পাথ পেলেও ফাইল না থাকে
    if p:
        log.warning("⚠️ Icon path returned but file not found: %s", p)
    else:
        log.warning("⚠️ get_icon_path() returned None")

    log.warning("Using default system icon (SP_ComputerIcon)")
    return QApplication.style().standardIcon(
        QApplication.style().StandardPixmap.SP_ComputerIcon
    )


class TunnelForgeGUI(QMainWindow):
    """Main application window with tabbed tunnel management."""

    def __init__(self, initial_port: int) -> None:
        super().__init__()
        self.setWindowTitle(f"TunnelForge Pro v{VERSION}")
        self.setMinimumSize(1280, 800)

        icon = _make_icon()
        self.setWindowIcon(icon)
        self._build_tray(icon)
        self._build_ui(initial_port)
        self.setStyleSheet(_STYLESHEET)
        self._register_single_instance()
        # Auto-prompt installer if cloudflared is missing
        from utils.paths import get_cloudflared_path
        from PyQt6.QtCore import QTimer
        if not get_cloudflared_path():
            QTimer.singleShot(500, self._open_installer)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_tray(self, icon) -> None:
        from PyQt6.QtWidgets import QSystemTrayIcon, QMenu
        self.tray_icon = QSystemTrayIcon(icon, self)
        menu = QMenu()
        menu.addAction("Show", self._bring_to_front)
        menu.addSeparator()
        menu.addAction("Exit", QApplication.quit)
        self.tray_icon.setContextMenu(menu)
        self.tray_icon.activated.connect(self._tray_activated)
        self.tray_icon.show()

    def _build_ui(self, initial_port: int) -> None:
        container = QWidget()
        self.setCentralWidget(container)
        root = QVBoxLayout(container)
        root.setSpacing(6)

        # Top bar
        top_row = QHBoxLayout()
        top_row.setContentsMargins(16, 12, 16, 0)
        install_btn = QPushButton("⬇️  Install / Update cloudflared")
        install_btn.setFixedHeight(48)
        install_btn.clicked.connect(self._open_installer)
        setup_btn = QPushButton("⚙️  Setup Custom Domain")
        setup_btn.setFixedHeight(48)
        setup_btn.clicked.connect(self._open_setup)
        top_row.addStretch()
        top_row.addWidget(install_btn)
        top_row.addSpacing(10)
        top_row.addWidget(setup_btn)
        root.addLayout(top_row)

        # Tabbed tunnels
        self.tabs = QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.tabCloseRequested.connect(self._close_tab)

        self._add_tab(initial_port)

        add_tab_btn = QPushButton("＋ New Tunnel")
        add_tab_btn.clicked.connect(lambda: self._add_tab(3000))
        self.tabs.setCornerWidget(add_tab_btn)

        root.addWidget(self.tabs)

    def _register_single_instance(self) -> None:
        from PyQt6.QtNetwork import QLocalServer
        self._server = QLocalServer(self)
        QLocalServer.removeServer(APP_ID)
        self._server.listen(APP_ID)
        self._server.newConnection.connect(self._on_new_instance)

    # ------------------------------------------------------------------
    # Tab management
    # ------------------------------------------------------------------

    def _add_tab(self, port: int) -> None:
        idx = self.tabs.count() + 1
        tab = TunnelTab(port, idx)
        self.tabs.addTab(tab, f"Tunnel {idx}")
        self.tabs.setCurrentWidget(tab)

    def _close_tab(self, index: int) -> None:
        if self.tabs.count() == 1:
            return  # keep at least one tab
        widget = self.tabs.widget(index)
        if hasattr(widget, "worker") and widget.worker and widget.worker.isRunning():
            widget.worker.stop()
            widget.worker.wait(2000)
        self.tabs.removeTab(index)

    # ------------------------------------------------------------------
    # Dialogs / actions
    # ------------------------------------------------------------------

    def _open_setup(self) -> None:
        dlg = SetupDialog(self)
        dlg.exec()

    def _open_installer(self) -> None:
        dlg = InstallerDialog(self)
        dlg.exec()

    # ------------------------------------------------------------------
    # Single-instance / tray
    # ------------------------------------------------------------------

    def _on_new_instance(self) -> None:
        conn = self._server.nextPendingConnection()
        if conn:
            conn.waitForReadyRead(200)
            conn.disconnectFromServer()
        self._bring_to_front()

    def _bring_to_front(self) -> None:
        self.show()
        self.raise_()
        self.activateWindow()

    def _tray_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._bring_to_front()

    def closeEvent(self, event) -> None:
        if self.tray_icon.isVisible():
            self.hide()
            event.ignore()
