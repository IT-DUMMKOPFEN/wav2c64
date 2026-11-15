"""Render screenshots of the GUI (works headless with QT_QPA_PLATFORM=offscreen).

    python tools/screenshots.py [output_dir]
"""

import os
import sys
import tempfile
import time

import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSettings  # noqa: E402
from PySide6.QtGui import QFontDatabase  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from wav2c64.core import write_wav16  # noqa: E402


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "screenshots")
    os.makedirs(out, exist_ok=True)
    tmp = tempfile.mkdtemp()
    QSettings.setPath(QSettings.NativeFormat, QSettings.UserScope, tmp)
    QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, tmp)
    app = QApplication([])
    app.setStyle("Fusion")
    from wav2c64.gui.dialogs import AboutDialog, ExportDialog, asset
    from wav2c64.gui.main_window import MainWindow
    from wav2c64.gui.theme import DAY, NIGHT
    QFontDatabase.addApplicationFont(asset("fonts", "PressStart2P-Regular.ttf"))

    rate = 44100
    t = np.arange(int(rate * 3.0)) / rate
    env = np.exp(-((t % 0.75) * 4.0))
    sig = 0.7 * env * np.sin(2 * np.pi * (220 + 80 * np.sin(t * 3)) * t)
    sig[int(rate * 2.4):] *= 0.05
    wav = os.path.join(tmp, "demo_sound.wav")
    write_wav16(wav, np.stack([sig, sig * 0.8], 1), rate)

    win = MainWindow()
    win.resize(1360, 880)
    win.show()
    win.load(wav)
    win.wave.set_selection(int(rate * 0.2), int(rate * 2.3))

    def settle():
        t0 = time.time()
        while time.time() - t0 < 15:
            app.processEvents()
            if win.result is not None and win.result_key == win._key():
                break
            time.sleep(0.02)
        for _ in range(20):
            app.processEvents()

    for theme in (NIGHT, DAY):
        win.apply_theme(theme)
        settle()
        win.grab().save(os.path.join(out, "main_%s.png" % theme["name"]))
        win.wave.zoom_selection()
        win.wave.zoom(8.0)
        settle()
        win.grab().save(os.path.join(out, "zoom_%s.png" % theme["name"]))
        win.wave.zoom_fit()
        win.tabs.setCurrentIndex(1)
        settle()
        win.grab().save(os.path.join(out, "info_%s.png" % theme["name"]))
        win.tabs.setCurrentIndex(0)
    # fade in + fade out
    win.w_fin.setChecked(True)
    win.w_fin_len.setValue(6)
    win.w_fout.setChecked(True)
    win.w_fout_len.setValue(4)
    for theme in (NIGHT, DAY):
        win.apply_theme(theme)
        settle()
        win.grab().save(os.path.join(out, "fade_%s.png" % theme["name"]))
    win.w_fin.setChecked(False)
    win.w_fout.setChecked(False)
    win.apply_theme(NIGHT)
    a = AboutDialog(win)
    a.show()
    settle()
    a.grab().save(os.path.join(out, "about.png"))
    a.findChild(type(win.tabs)).setCurrentIndex(1)
    settle()
    a.grab().save(os.path.join(out, "licenses.png"))
    e = ExportDialog(win, tmp, "demo_sound")
    e.show()
    settle()
    e.grab().save(os.path.join(out, "export.png"))
    print("screenshots in", out)


if __name__ == "__main__":
    main()
