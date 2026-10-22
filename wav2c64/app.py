"""Start the WAV2C64 desktop app."""

import os
import sys


def main(argv=None):
    argv = sys.argv if argv is None else argv
    from PySide6.QtGui import QFontDatabase, QIcon
    from PySide6.QtWidgets import QApplication

    from . import APP_NAME, AUTHOR, VERSION
    from .gui.dialogs import asset
    from .gui.main_window import MainWindow

    QApplication.setApplicationName(APP_NAME)
    QApplication.setOrganizationName(AUTHOR)
    QApplication.setApplicationVersion(VERSION)
    app = QApplication(argv)
    app.setStyle("Fusion")
    app.setWindowIcon(QIcon(asset("icon.png")))
    QFontDatabase.addApplicationFont(asset("fonts", "PressStart2P-Regular.ttf"))
    win = MainWindow()
    win.show()
    files = [a for a in argv[1:] if a.lower().endswith(".wav") and os.path.isfile(a)]
    if files:
        win.load(files[0])
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
