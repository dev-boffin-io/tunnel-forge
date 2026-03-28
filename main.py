# file: main.py

import os
import sys

from cli import build_arg_parser, run_cli


def main() -> None:
    parser = build_arg_parser()
    args   = parser.parse_args()

    # Decide: CLI or GUI
    force_cli = args.cli or (os.name != "nt" and os.environ.get("DISPLAY") is None)

    if force_cli:
        sys.exit(run_cli(args))
    else:
        _run_gui(args.port)


def _run_gui(port: int) -> None:
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtNetwork import QLocalSocket

    from constants import APP_ID
    from gui.app import TunnelForgeGUI
    from utils.paths import get_icon_path
    from PyQt6.QtGui import QIcon

    app = QApplication(sys.argv)

    p = get_icon_path()
    if p:
        app.setWindowIcon(QIcon(p))

    # Single-instance guard: if another window is running, raise it.
    sock = QLocalSocket()
    sock.connectToServer(APP_ID)
    if sock.waitForConnected(300):
        sock.write(b"show")
        sock.flush()
        sock.waitForBytesWritten(300)
        sock.disconnectFromServer()
        sys.exit(0)
    sock.abort()

    win = TunnelForgeGUI(port)
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
