"""GUI smoke test (runs headless with QT_QPA_PLATFORM=offscreen)."""

import os
import tempfile
import time

import numpy as np
import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSettings  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from wav2c64.core import write_wav16  # noqa: E402


@pytest.fixture(scope="module")
def app():
    QSettings.setDefaultFormat(QSettings.IniFormat)
    tmp = tempfile.mkdtemp()
    QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, tmp)
    a = QApplication.instance() or QApplication([])
    yield a


def _wait(app, cond, timeout=20):
    t = time.time()
    while not cond():
        app.processEvents()
        time.sleep(0.01)
        if time.time() - t > timeout:
            raise AssertionError("timeout")


def test_main_window_flow(app, monkeypatch):
    from wav2c64.gui import main_window as mw
    from wav2c64.gui.dialogs import AboutDialog, ExportDialog

    with tempfile.TemporaryDirectory() as d:
        t = np.arange(22050) / 22050.0
        sig = np.stack([0.6 * np.sin(2 * np.pi * 330 * t), 0.4 * np.sin(2 * np.pi * 220 * t)], 1)
        wav = os.path.join(d, "test sound.wav")
        write_wav16(wav, sig, 22050)

        win = mw.MainWindow()
        win.show()
        win.load(wav)
        assert win.wav is not None and win.wave.total() == 22050
        _wait(app, lambda: win.result is not None and win.result_key == win._key())
        assert win.result.samples == 8000
        assert win.btn_export.isEnabled()

        # trim + settings change -> new result
        win.wave.set_selection(2205, 11025)
        win.w_rate.setValue(6000)
        _wait(app, lambda: win.result is not None and win.result_key == win._key())
        assert win.result.rate == 6000
        assert win.w_preset.currentData() == "quality"
        win.w_gain.setValue(1.0)
        assert win.w_preset.currentData() == "custom"

        # fade in / fade out, independent, with their own length
        win.wave.set_selection(0, 22050)          # 1 s
        assert not win.w_fin_len.isEnabled()
        win.w_fin.setChecked(True)
        win.w_fin_len.setValue(5)                 # 0.5 s
        assert win.w_fin_len.isEnabled() and win.lbl_fin.text() == "0.5 s"
        assert win.settings.fade_in and win.settings.fade_in_s == 0.5
        assert not win.settings.fade_out
        assert win.wave.fades == (11025, 0)
        win.w_fout.setChecked(True)
        win.w_fout_len.setValue(100)              # 10 s > selection -> shortened
        assert sum(win.wave.fades) == win.wave.s1 - win.wave.s0
        assert "shortened" in win.lbl_fade.text()
        win.w_fout_len.setValue(2)
        _wait(app, lambda: win.result is not None and win.result_key == win._key())
        n = win.result.nibbles[:win.result.samples]
        assert n[0] == 8 and n[-1] == 8
        assert win.w_preset.currentData() == "quality"   # fades are not a sound preset
        win.w_fin.setChecked(False)
        win.w_fout.setChecked(False)
        assert win.wave.fades == (0, 0)

        # zoom
        win.wave.zoom(4.0)
        assert win.wave.v1 - win.wave.v0 < 22050
        win.wave.zoom_fit()

        # themes
        win.toggle_theme()
        win.toggle_theme()

        # memory too big -> export disabled
        big = os.path.join(d, "long.wav")
        write_wav16(big, 0.3 * np.sin(np.arange(8000 * 20) * 0.05), 8000)
        win.load(big)
        assert not win.btn_export.isEnabled()
        assert win.mem_bar.property("level") == "bad"
        win.wave.set_selection(0, 8000 * 5)
        assert win.btn_export.isEnabled()

        # export via dialog (dialog answered automatically)
        out = os.path.join(d, "out")
        os.mkdir(out)
        monkeypatch.setattr(ExportDialog, "exec", lambda self: ExportDialog.Accepted)
        monkeypatch.setattr(ExportDialog, "result_values", lambda self: (out, "demo"))
        monkeypatch.setattr(mw.QMessageBox, "exec", lambda self: 0)
        win.export()
        assert sorted(os.listdir(out)) == ["demo.asm", "demo.prg", "demo.txt"]
        with open(os.path.join(out, "demo.prg"), "rb") as f:
            assert f.read(2) == b"\x01\x08"

        AboutDialog(win)
        win.close()
