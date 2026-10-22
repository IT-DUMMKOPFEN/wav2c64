"""Export dialog and About dialog (sources and licenses)."""

import os

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices, QPixmap
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QHBoxLayout, QLabel,
    QLineEdit, QPlainTextEdit, QPushButton, QTableWidget, QTableWidgetItem,
    QTabWidget, QVBoxLayout, QWidget, QHeaderView, QAbstractItemView, QMessageBox,
)

from .. import APP_NAME, VERSION, AUTHOR, HOMEPAGE
from ..export import valid_name

ASSETS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets")


def asset(*parts):
    return os.path.join(ASSETS, *parts)


# ---------------------------------------------------------------------
class ExportDialog(QDialog):
    """Ask for the target folder and the project name."""

    def __init__(self, parent, folder, name):
        super().__init__(parent)
        self.setWindowTitle("Export C64 project")
        self.setMinimumWidth(560)
        lay = QVBoxLayout(self)
        title = QLabel("EXPORT")
        title.setObjectName("h1")
        lay.addWidget(title)
        info = QLabel("Choose a folder and a project name. Three files are written:")
        info.setWordWrap(True)
        lay.addWidget(info)

        form = QFormLayout()
        row = QHBoxLayout()
        self.folder = QLineEdit(folder)
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse)
        row.addWidget(self.folder, 1)
        row.addWidget(browse)
        form.addRow("Folder:", row)
        self.name = QLineEdit(name)
        self.name.setMaxLength(16)
        self.name.setPlaceholderText("e.g. mysound")
        form.addRow("Project name:", self.name)
        lay.addLayout(form)

        self.files = QLabel()
        self.files.setObjectName("muted")
        self.files.setTextFormat(Qt.RichText)
        self.files.setWordWrap(True)
        lay.addWidget(self.files)

        self.buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        self.buttons.accepted.connect(self._accept)
        self.buttons.rejected.connect(self.reject)
        lay.addWidget(self.buttons)
        self.name.textChanged.connect(self._update)
        self.folder.textChanged.connect(self._update)
        self._update()

    def _browse(self):
        d = QFileDialog.getExistingDirectory(self, "Choose folder", self.folder.text())
        if d:
            self.folder.setText(d)

    def _update(self):
        n = self.name.text().strip()
        ok = valid_name(n) and os.path.isdir(self.folder.text())
        if valid_name(n):
            self.files.setText(
                "<b>%s.prg</b> – ready to run program for the C64 / VICE<br>"
                "<b>%s.asm</b> – player source code for the ACME assembler<br>"
                "<b>%s.txt</b> – sample data as <tt>!byte</tt> lines (included by the .asm)"
                % (n, n, n))
        else:
            self.files.setText("<span style='color:#c43c3c'>Name: 1–16 characters, "
                               "only A–Z, 0–9, _ and -.</span>")
        self.buttons.button(QDialogButtonBox.Save).setEnabled(ok)

    def _accept(self):
        folder, n = self.folder.text(), self.name.text().strip()
        existing = [f for f in (n + ".prg", n + ".asm", n + ".txt")
                    if os.path.exists(os.path.join(folder, f))]
        if existing:
            r = QMessageBox.question(
                self, "Overwrite?",
                "These files already exist:\n\n%s\n\nOverwrite them?" % "\n".join(existing))
            if r != QMessageBox.Yes:
                return
        self.accept()

    def result_values(self):
        return self.folder.text(), self.name.text().strip()


# ---------------------------------------------------------------------
CREDITS = [
    # component, used for, license, file, included in the app
    ("WAV2C64", "This app, by %s" % AUTHOR, "MIT", "WAV2C64-MIT.txt", "yes",
     HOMEPAGE),
    ("Python", "Programming language and runtime", "PSF License", "Python-PSF.txt", "yes",
     "https://www.python.org"),
    ("Qt 6 / PySide6 (Qt for Python)", "User interface, audio playback", "LGPL v3",
     "LGPL-3.0.txt", "yes (unmodified, dynamically loaded)", "https://www.qt.io/qt-for-python"),
    ("FFmpeg (via Qt Multimedia)", "Audio output backend of Qt", "LGPL v2.1+",
     "LGPL-2.1.txt", "yes, where Qt ships it", "https://ffmpeg.org"),
    ("NumPy", "Signal processing", "BSD 3-Clause", "NumPy-BSD-3-Clause.txt", "yes",
     "https://numpy.org"),
    ("Press Start 2P font", "Pixel font (by CodeMan38)", "SIL Open Font License 1.1",
     "PressStart2P-OFL-1.1.txt", "yes", "https://fonts.google.com/specimen/Press+Start+2P"),
    ("PyInstaller", "Builds the executable (bootloader)", "GPL v2 with bootloader exception",
     "PyInstaller-GPL-2.0-bootloader-exception.txt", "bootloader only", "https://pyinstaller.org"),
    ("AppImage runtime / appimagetool", "Linux AppImage package", "MIT",
     "AppImage-MIT.txt", "Linux AppImage only", "https://appimage.org"),
    ("ACME cross assembler", "The generated .asm is written for ACME", "GPL v2",
     "GPL-2.0.txt", "no (compatible output only)", "https://sourceforge.net/projects/acme-crossass/"),
    ("py65", "6502 emulator for the automatic tests", "BSD 3-Clause",
     "py65-BSD-3-Clause.txt", "no (development only)", "https://github.com/mnaberez/py65"),
    ("C64 colours", "“Colodore”/“Pepto” palette values by Philip “Pepto” Timmermann",
     "colour values (credit)", None, "colours only", "https://www.pepto.de/projects/colorvic/"),
    ("C64 techniques", "SID 6581/8580 detection, 8580 digi boost, NMI sample playback "
     "– public knowledge of the C64 scene (e.g. codebase64.org)", "credit", None, "ideas only",
     "https://codebase64.org"),
]


class AboutDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("About %s" % APP_NAME)
        self.resize(820, 600)
        lay = QVBoxLayout(self)
        tabs = QTabWidget()
        lay.addWidget(tabs)

        # --- about
        w = QWidget()
        v = QVBoxLayout(w)
        logo = QLabel()
        pm = QPixmap(asset("banner.png"))
        if not pm.isNull():
            logo.setPixmap(pm.scaledToWidth(700, Qt.SmoothTransformation))
        logo.setAlignment(Qt.AlignCenter)
        v.addWidget(logo)
        t = QLabel(
            "<h2>%s %s</h2>"
            "<p>Converts WAV files into 4-bit samples for the Commodore 64 and creates "
            "a ready-to-run PRG, the matching ACME assembler source and the sample data "
            "as <tt>!byte</tt> text file.</p>"
            "<p>Author: <b>%s</b><br>License: <b>MIT</b><br>"
            "<a href='%s'>%s</a></p>" % (APP_NAME, VERSION, AUTHOR, HOMEPAGE, HOMEPAGE))
        t.setWordWrap(True)
        t.setOpenExternalLinks(True)
        t.setAlignment(Qt.AlignCenter)
        v.addWidget(t)
        v.addStretch(1)
        tabs.addTab(w, "About")

        # --- sources & licenses
        w2 = QWidget()
        v2 = QVBoxLayout(w2)
        v2.addWidget(QLabel("All sources, components and their licenses. "
                            "Select a row to read the license text."))
        self.table = QTableWidget(len(CREDITS), 4)
        self.table.setHorizontalHeaderLabels(["Component", "Used for", "License", "Included"])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        for r, (name, use, lic, _f, inc, _url) in enumerate(CREDITS):
            for c, txt in enumerate((name, use, lic, inc)):
                it = QTableWidgetItem(txt)
                it.setToolTip(txt)
                self.table.setItem(r, c, it)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(1, QHeaderView.Stretch)
        hh.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        v2.addWidget(self.table, 2)
        row = QHBoxLayout()
        self.link = QPushButton("Open website")
        self.link.clicked.connect(self._open_link)
        row.addStretch(1)
        row.addWidget(self.link)
        v2.addLayout(row)
        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        v2.addWidget(self.text, 3)
        self.table.currentCellChanged.connect(lambda r, *_: self._show(r))
        tabs.addTab(w2, "Sources && licenses")
        self.table.selectRow(0)
        self._show(0)

        bb = QDialogButtonBox(QDialogButtonBox.Close)
        bb.rejected.connect(self.reject)
        bb.accepted.connect(self.accept)
        bb.button(QDialogButtonBox.Close).clicked.connect(self.accept)
        lay.addWidget(bb)

    def _show(self, r):
        if not 0 <= r < len(CREDITS):
            return
        name, use, lic, fname, inc, url = CREDITS[r]
        head = "%s\n%s\nLicense: %s\nIncluded in the app: %s\n%s\n\n" % (
            name, use, lic, inc, url)
        body = ""
        if fname:
            try:
                with open(asset("licenses", fname), encoding="utf-8", errors="replace") as f:
                    body = f.read()
            except OSError:
                body = "(license file not found)"
        self.text.setPlainText(head + body)
        self.link.setEnabled(bool(url))

    def _open_link(self):
        r = self.table.currentRow()
        if 0 <= r < len(CREDITS) and CREDITS[r][5]:
            QDesktopServices.openUrl(QUrl(CREDITS[r][5]))
