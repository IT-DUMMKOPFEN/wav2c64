"""Main window of WAV2C64."""

import json
import math
import os
import time
from dataclasses import replace

from PySide6.QtCore import (Qt, QObject, QRunnable, QSettings, QThreadPool, QTimer,
                            QTemporaryDir, QUrl, Signal, Slot)
from PySide6.QtGui import QAction, QDesktopServices, QIcon, QKeySequence, QPixmap
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QFormLayout,
    QGroupBox, QHBoxLayout, QLabel, QMainWindow, QMessageBox, QProgressBar, QPushButton,
    QScrollArea, QScrollBar, QSlider, QSpinBox, QSplitter, QTabWidget, QTextBrowser,
    QVBoxLayout, QWidget,
)

from .. import APP_NAME, VERSION, AUTHOR
from ..core import (PRESETS, Settings, WavError, apply_preset, convert, load_wav,
                    output_length, preview_audio, write_wav16)
from ..export import build_project, player_info, write_project
from .dialogs import AboutDialog, ExportDialog, asset
from .theme import DAY, NIGHT, palette_for, stylesheet_for
from .waveform import WaveformView

try:
    from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
    HAVE_AUDIO = True
except Exception:  # pragma: no cover - Qt without multimedia
    HAVE_AUDIO = False


# ---------------------------------------------------------------------
class _Signals(QObject):
    done = Signal(int, object, object)     # request id, result, error


class _ConvertJob(QRunnable):
    def __init__(self, rid, mono, rate, s0, s1, settings, max_samples):
        super().__init__()
        self.args = (rid, mono, rate, s0, s1, settings, max_samples)
        self.signals = _Signals()

    def run(self):
        rid, mono, rate, s0, s1, st, mx = self.args
        try:
            r = convert(mono, rate, s0, s1, st, max_samples=mx)
            self.signals.done.emit(rid, r, None)
        except Exception as e:  # report to the GUI
            self.signals.done.emit(rid, None, e)


def _fmt_bytes(n):
    return "{:,}".format(int(n))


# ---------------------------------------------------------------------
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("%s %s" % (APP_NAME, VERSION))
        self.setWindowIcon(QIcon(asset("icon.png")))
        self.setAcceptDrops(True)
        self.qs = QSettings(AUTHOR, APP_NAME)
        try:
            self.settings = Settings.from_dict(json.loads(self.qs.value("settings", "{}")))
        except (ValueError, TypeError):
            self.settings = Settings()
        self.theme = NIGHT if self.qs.value("theme", "night") == "night" else DAY
        self.wav = None
        self.mono = None
        self.result = None
        self.result_key = None
        self.req_id = 0
        self.busy = False
        self.play_mode = None
        self._updating = False
        self.tmp = QTemporaryDir()
        self.pool = QThreadPool.globalInstance()
        self.jobs = []
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(250)
        self.timer.timeout.connect(self._start_convert)

        self._build_ui()
        self._build_audio()
        self._settings_to_widgets()
        self.apply_theme(self.theme)
        self._update_state()
        geo = self.qs.value("geometry")
        if geo is not None:
            self.restoreGeometry(geo)
        else:
            self.resize(1280, 820)
        sp = self.qs.value("splitter")
        if sp is not None:
            self.splitter.restoreState(sp)

    # ================================================================ UI
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(12, 10, 12, 10)
        root.setSpacing(8)

        # header
        head = QHBoxLayout()
        self.banner = QLabel()
        pm = QPixmap(asset("banner.png"))
        if not pm.isNull():
            self.banner.setPixmap(pm.scaledToHeight(70, Qt.SmoothTransformation))
        head.addWidget(self.banner)
        head.addStretch(1)
        self.btn_theme = QPushButton()
        self.btn_theme.setToolTip("Switch between day and night mode")
        self.btn_theme.clicked.connect(self.toggle_theme)
        self.btn_about = QPushButton("About")
        self.btn_about.setToolTip("Version, author, sources and licenses")
        self.btn_about.clicked.connect(lambda: AboutDialog(self).exec())
        head.addWidget(self.btn_theme)
        head.addWidget(self.btn_about)
        root.addLayout(head)

        self.splitter = QSplitter(Qt.Horizontal)
        root.addWidget(self.splitter, 1)

        # ---------------- left side
        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 6, 0)

        frow = QHBoxLayout()
        self.btn_open = QPushButton("Open WAV…")
        self.btn_open.setToolTip("Load a WAV file (Ctrl+O). You can also drop a file on the window.")
        self.btn_open.clicked.connect(self.open_dialog)
        self.lbl_file = QLabel("No file loaded.")
        self.lbl_file.setObjectName("muted")
        frow.addWidget(self.btn_open)
        frow.addWidget(self.lbl_file, 1)
        lv.addLayout(frow)

        wgrp = QGroupBox("1  TRIM")
        wl = QVBoxLayout(wgrp)
        hint = QLabel("Drag in the wave to select the part to convert, drag the edges to fine-tune. "
                      "Mouse wheel = zoom, Shift + wheel = scroll, double click = select all.")
        hint.setObjectName("muted")
        hint.setWordWrap(True)
        wl.addWidget(hint)
        self.wave = WaveformView()
        self.wave.selectionChanged.connect(self._on_selection)
        self.wave.viewChanged.connect(self._on_view)
        wl.addWidget(self.wave, 1)
        self.hscroll = QScrollBar(Qt.Horizontal)
        self.hscroll.valueChanged.connect(lambda v: self.wave.scroll_to(v))
        wl.addWidget(self.hscroll)

        zrow = QHBoxLayout()
        for text, tip, fn in (("−", "Zoom out", lambda: self.wave.zoom(0.5)),
                              ("+", "Zoom in", lambda: self.wave.zoom(2.0)),
                              ("Fit", "Show the whole file", self.wave.zoom_fit),
                              ("Zoom to selection", "Show only the selection", self.wave.zoom_selection)):
            b = QPushButton(text)
            b.setToolTip(tip)
            b.clicked.connect(fn)
            zrow.addWidget(b)
        zrow.addStretch(1)
        zrow.addWidget(QLabel("Start"))
        self.sp_start = QDoubleSpinBox()
        self.sp_start.setDecimals(3)
        self.sp_start.setSuffix(" s")
        self.sp_start.setSingleStep(0.01)
        self.sp_start.valueChanged.connect(self._on_sel_spin)
        zrow.addWidget(self.sp_start)
        zrow.addWidget(QLabel("End"))
        self.sp_end = QDoubleSpinBox()
        self.sp_end.setDecimals(3)
        self.sp_end.setSuffix(" s")
        self.sp_end.setSingleStep(0.01)
        self.sp_end.valueChanged.connect(self._on_sel_spin)
        zrow.addWidget(self.sp_end)
        self.lbl_len = QLabel("")
        self.lbl_len.setObjectName("muted")
        zrow.addWidget(self.lbl_len)
        b = QPushButton("All")
        b.setToolTip("Select the whole file")
        b.clicked.connect(lambda: self.wave.set_selection(0, self.wave.total()))
        zrow.addWidget(b)
        wl.addLayout(zrow)
        lv.addWidget(wgrp, 1)

        # listen
        pgrp = QGroupBox("2  LISTEN")
        pl = QHBoxLayout(pgrp)
        self.btn_play_orig = QPushButton("▶  Original")
        self.btn_play_orig.setToolTip("Play the selected part of the original file")
        self.btn_play_orig.clicked.connect(lambda: self.toggle_play("orig"))
        self.btn_play_c64 = QPushButton("▶  C64 4-bit")
        self.btn_play_c64.setToolTip("Play the converted 4-bit sample as the C64 will play it (Space)")
        self.btn_play_c64.clicked.connect(lambda: self.toggle_play("c64"))
        self.chk_overlay = QCheckBox("Show 4-bit result in the wave")
        self.chk_overlay.setChecked(self.qs.value("overlay", "true") == "true")
        self.chk_overlay.toggled.connect(self._on_overlay)
        pl.addWidget(self.btn_play_orig)
        pl.addWidget(self.btn_play_c64)
        pl.addSpacing(12)
        pl.addWidget(self.chk_overlay)
        pl.addStretch(1)
        self.lbl_audio = QLabel("" if HAVE_AUDIO else "Audio playback not available on this system.")
        self.lbl_audio.setObjectName("muted")
        pl.addWidget(self.lbl_audio)
        lv.addWidget(pgrp)

        # memory + export
        mgrp = QGroupBox("3  C64 MEMORY")
        ml = QVBoxLayout(mgrp)
        self.mem_bar = QProgressBar()
        self.mem_bar.setTextVisible(True)
        ml.addWidget(self.mem_bar)
        self.lbl_mem = QLabel("")
        self.lbl_mem.setObjectName("muted")
        self.lbl_mem.setWordWrap(True)
        ml.addWidget(self.lbl_mem)
        lv.addWidget(mgrp)

        erow = QHBoxLayout()
        self.lbl_result = QLabel("")
        self.lbl_result.setWordWrap(True)
        erow.addWidget(self.lbl_result, 1)
        self.btn_export = QPushButton("4  EXPORT…")
        self.btn_export.setObjectName("primary")
        self.btn_export.setToolTip("Write .prg, .asm and .txt into a folder (Ctrl+E)")
        self.btn_export.clicked.connect(self.export)
        erow.addWidget(self.btn_export)
        lv.addLayout(erow)

        self.splitter.addWidget(left)

        # ---------------- right side
        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_settings(), "Settings")
        self.info = QTextBrowser()
        self.info.setOpenExternalLinks(True)
        self.tabs.addTab(self.info, "How it works")
        self.splitter.addWidget(self.tabs)
        self.splitter.setStretchFactor(0, 3)
        self.splitter.setStretchFactor(1, 2)
        self.splitter.setSizes([820, 440])

        # shortcuts
        for seq, fn in ((QKeySequence.Open, self.open_dialog),
                        (QKeySequence("Ctrl+E"), self.export),
                        (QKeySequence("Space"), lambda: self.toggle_play("c64")),
                        (QKeySequence.Quit, self.close)):
            a = QAction(self)
            a.setShortcut(seq)
            a.triggered.connect(fn)
            self.addAction(a)

    def _build_settings(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        host = QWidget()
        v = QVBoxLayout(host)
        v.setSpacing(10)

        def spin(cls, lo, hi, step, suffix="", dec=1, special=None, tip=""):
            w = cls()
            w.setRange(lo, hi)
            w.setSingleStep(step)
            if cls is QDoubleSpinBox:
                w.setDecimals(dec)
            if suffix:
                w.setSuffix(suffix)
            if special:
                w.setSpecialValueText(special)
            w.setToolTip(tip)
            w.valueChanged.connect(self._on_setting)
            return w

        # sample
        g = QGroupBox("SAMPLE")
        f = QFormLayout(g)
        self.w_rate = spin(QSpinBox, 2000, 12000, 100, " Hz",
                           tip="Samples per second on the C64. Higher = brighter sound but more "
                               "memory. 8000 Hz is a good default.")
        f.addRow("Sample rate:", self.w_rate)
        rr = QHBoxLayout()
        for r in (4000, 6000, 8000, 10000, 11025):
            b = QPushButton(str(r))
            b.setToolTip("Set %d Hz" % r)
            b.clicked.connect(lambda _=False, r=r: self.w_rate.setValue(r))
            rr.addWidget(b)
        f.addRow("", rr)
        self.lbl_rate = QLabel()
        self.lbl_rate.setObjectName("muted")
        self.lbl_rate.setWordWrap(True)
        f.addRow("", self.lbl_rate)
        v.addWidget(g)

        # sound processing
        g = QGroupBox("SOUND / NOISE")
        f = QFormLayout(g)
        self.w_preset = QComboBox()
        self.w_preset.addItem("Quality (recommended)", "quality")
        self.w_preset.addItem("Clean (no processing)", "clean")
        self.w_preset.addItem("Custom", "custom")
        self.w_preset.setToolTip("Quality: high-pass, compressor, limiter and noise gate make "
                                 "the most of the 16 volume levels - much less noise.")
        self.w_preset.currentIndexChanged.connect(self._on_preset)
        f.addRow("Preset:", self.w_preset)
        self.w_norm = QCheckBox("Normalize to full level")
        self.w_norm.setToolTip("Use the full range of the 16 levels.")
        self.w_norm.toggled.connect(self._on_setting)
        f.addRow("", self.w_norm)
        self.w_gain = spin(QDoubleSpinBox, -12, 12, 0.5, " dB",
                           tip="Extra gain after all other steps (values above 0 clip).")
        f.addRow("Gain:", self.w_gain)
        self.w_hpf = spin(QSpinBox, 0, 500, 10, " Hz", special="Off",
                          tip="High-pass: removes rumble and deep bass that waste levels.")
        f.addRow("High-pass:", self.w_hpf)
        self.w_comp = spin(QDoubleSpinBox, 1, 10, 0.5, ":1", special="Off",
                           tip="Compressor ratio: makes quiet parts louder, so they are not "
                               "lost in the noise.")
        f.addRow("Compressor:", self.w_comp)
        self.w_thr = spin(QDoubleSpinBox, -40, -1, 1, " dB", dec=0,
                          tip="The compressor works above this level.")
        f.addRow("Comp. threshold:", self.w_thr)
        self.w_lim = spin(QDoubleSpinBox, 0, 12, 1, " dB", dec=0, special="Off",
                          tip="Limiter: raises the level and softly rounds off peaks.")
        f.addRow("Limiter boost:", self.w_lim)
        self.w_gate = spin(QSpinBox, 0, 60, 1, " dB", special="Off",
                           tip="Noise gate: parts quieter than -X dB become complete silence "
                               "(no hiss in pauses).")
        self.w_gate.setPrefix("below -")
        f.addRow("Noise gate:", self.w_gate)
        srow = QHBoxLayout()
        self.w_shape = QSlider(Qt.Horizontal)
        self.w_shape.setRange(0, 100)
        self.w_shape.setToolTip("Noise shaping: moves the 4-bit noise to high frequencies. "
                                "Try 40-60 %, listen with the C64 play button.")
        self.w_shape.valueChanged.connect(self._on_setting)
        self.lbl_shape = QLabel()
        self.lbl_shape.setMinimumWidth(40)
        srow.addWidget(self.w_shape, 1)
        srow.addWidget(self.lbl_shape)
        f.addRow("Noise shaping:", srow)
        self.w_dither = QCheckBox("Dither")
        self.w_dither.setToolTip("Adds a little noise to break up distortion of very quiet sounds.")
        self.w_dither.toggled.connect(self._on_setting)
        f.addRow("", self.w_dither)
        v.addWidget(g)

        # C64
        g = QGroupBox("C64 PLAYER")
        f = QFormLayout(g)
        self.w_machine = QComboBox()
        self.w_machine.addItems(["Auto detect", "PAL", "NTSC"])
        self.w_machine.setToolTip("PAL and NTSC machines have different clocks. Auto detect "
                                  "measures the raster lines when the program starts.")
        self.w_machine.currentIndexChanged.connect(self._on_setting)
        f.addRow("Machine:", self.w_machine)
        self.w_sid = QComboBox()
        self.w_sid.addItems(["Auto detect", "6581 (old)", "8580 (new, digi boost)"])
        self.w_sid.setToolTip("The 8580 SID is nearly silent with $D418 samples - the player "
                              "switches on a digi boost for it.")
        self.w_sid.currentIndexChanged.connect(self._on_setting)
        f.addRow("SID chip:", self.w_sid)
        self.w_loop = QComboBox()
        self.w_loop.addItems(["Play once", "Loop"])
        self.w_loop.currentIndexChanged.connect(self._on_setting)
        f.addRow("Playback:", self.w_loop)
        keys = QLabel("On the C64: SPACE = play again, Q = quit to BASIC.")
        keys.setObjectName("muted")
        keys.setWordWrap(True)
        f.addRow("", keys)
        v.addWidget(g)

        b = QPushButton("Reset all settings")
        b.clicked.connect(self._reset_settings)
        v.addWidget(b)
        v.addStretch(1)
        scroll.setWidget(host)
        return scroll

    # ============================================================ theme
    def apply_theme(self, t):
        self.theme = t
        app = QApplication.instance()
        app.setPalette(palette_for(t))
        app.setStyleSheet(stylesheet_for(t))
        self.wave.set_theme(t)
        self.btn_theme.setText("☀  Day" if t["name"] == "night" else "☾  Night")
        self.qs.setValue("theme", t["name"])
        self._update_mem_style()
        self._update_info()

    def toggle_theme(self):
        self.apply_theme(DAY if self.theme["name"] == "night" else NIGHT)

    # ============================================================ audio
    def _build_audio(self):
        self.player = None
        if not HAVE_AUDIO:
            for b in (self.btn_play_orig, self.btn_play_c64):
                b.setEnabled(False)
            return
        try:
            self.audio_out = QAudioOutput(self)
            self.audio_out.setVolume(0.9)
            self.player = QMediaPlayer(self)
            self.player.setAudioOutput(self.audio_out)
            self.player.positionChanged.connect(self._on_position)
            self.player.playbackStateChanged.connect(self._on_play_state)
            self.player.errorOccurred.connect(
                lambda *_: self.statusBar().showMessage("Audio error: " + self.player.errorString(), 6000))
        except Exception as e:  # pragma: no cover
            self.player = None
            self.lbl_audio.setText("Audio playback not available: %s" % e)

    def toggle_play(self, mode):
        if self.player is None or self.wav is None:
            return
        if self.play_mode == mode:
            self.stop_play()
            return
        self.stop_play()
        s0, s1 = self.wave.s0, self.wave.s1
        if s1 <= s0:
            return
        path = os.path.join(self.tmp.path(), "play_%s_%d.wav" % (mode, int(time.time() * 1000)))
        if mode == "orig":
            write_wav16(path, self.wav.data[s0:s1], self.wav.rate)
        else:
            r = self._current_result_sync()
            if r is None or r.samples == 0:
                return
            write_wav16(path, preview_audio(r, 44100), 44100)
        self.play_mode = mode
        self.player.setSource(QUrl.fromLocalFile(path))
        self.player.play()
        self._update_play_buttons()

    def stop_play(self):
        if self.player is not None:
            self.player.stop()
        self.play_mode = None
        self.wave.set_playhead(None)
        self._update_play_buttons()

    def _on_position(self, ms):
        if self.play_mode and self.wav is not None:
            self.wave.set_playhead(self.wave.s0 + ms / 1000.0 * self.wav.rate)

    def _on_play_state(self, state):
        if state == QMediaPlayer.StoppedState and self.play_mode:
            self.play_mode = None
            self.wave.set_playhead(None)
            self._update_play_buttons()

    def _update_play_buttons(self):
        self.btn_play_orig.setText("■  Stop" if self.play_mode == "orig" else "▶  Original")
        self.btn_play_c64.setText("■  Stop" if self.play_mode == "c64" else "▶  C64 4-bit")

    # ============================================================ files
    def open_dialog(self):
        d = self.qs.value("open_dir", os.path.expanduser("~"))
        path, _ = QFileDialog.getOpenFileName(self, "Open WAV file", d, "WAV files (*.wav *.WAV)")
        if path:
            self.load(path)

    def load(self, path):
        try:
            w = load_wav(path)
        except (WavError, OSError) as e:
            QMessageBox.warning(self, "Cannot open file", "%s\n\n%s" % (path, e))
            return
        if w.frames == 0:
            QMessageBox.warning(self, "Cannot open file", "The file contains no audio.")
            return
        self.stop_play()
        self.wav = w
        self.mono = w.mono()
        self.qs.setValue("open_dir", os.path.dirname(path))
        self.lbl_file.setText("%s   –   %d Hz, %d bit%s, %s, %.2f s" % (
            os.path.basename(path), w.rate, w.bits, " float" if w.is_float else "",
            "mono" if w.channels == 1 else "%d channels" % w.channels, w.duration))
        self.result = None
        for sp in (self.sp_start, self.sp_end):
            sp.blockSignals(True)
            sp.setRange(0, w.duration)
            sp.blockSignals(False)
        self.wave.set_data(self.mono, w.rate)
        name = "".join(c for c in os.path.splitext(os.path.basename(path))[0]
                       if c.isalnum() or c in "_-")[:16]
        self.suggested_name = name or "sample"
        self._schedule()

    def dragEnterEvent(self, ev):
        if any(u.toLocalFile().lower().endswith(".wav") for u in ev.mimeData().urls()):
            ev.acceptProposedAction()

    def dropEvent(self, ev):
        for u in ev.mimeData().urls():
            if u.toLocalFile().lower().endswith(".wav"):
                self.load(u.toLocalFile())
                break

    # ============================================================ settings
    def _settings_to_widgets(self):
        s = self.settings
        self._updating = True
        self.w_rate.setValue(s.sample_rate)
        idx = self.w_preset.findData(s.preset)
        self.w_preset.setCurrentIndex(max(0, idx))
        self.w_norm.setChecked(s.normalize)
        self.w_gain.setValue(s.gain_db)
        self.w_hpf.setValue(int(s.highpass_hz))
        self.w_comp.setValue(max(1.0, s.comp_ratio))
        self.w_thr.setValue(s.comp_threshold_db)
        self.w_lim.setValue(s.limiter_db)
        self.w_gate.setValue(int(abs(s.gate_db)))
        self.w_shape.setValue(int(round(s.noise_shaping * 100)))
        self.w_dither.setChecked(s.dither)
        self.w_machine.setCurrentIndex(s.machine)
        self.w_sid.setCurrentIndex(s.sid)
        self.w_loop.setCurrentIndex(1 if s.loop else 0)
        self.lbl_shape.setText("%d %%" % self.w_shape.value())
        self._updating = False

    def _widgets_to_settings(self):
        s = self.settings
        s.sample_rate = self.w_rate.value()
        s.normalize = self.w_norm.isChecked()
        s.gain_db = self.w_gain.value()
        s.highpass_hz = float(self.w_hpf.value())
        s.comp_ratio = self.w_comp.value()
        s.comp_threshold_db = self.w_thr.value()
        s.limiter_db = self.w_lim.value()
        s.gate_db = -float(self.w_gate.value())
        s.noise_shaping = self.w_shape.value() / 100.0
        s.dither = self.w_dither.isChecked()
        s.machine = self.w_machine.currentIndex()
        s.sid = self.w_sid.currentIndex()
        s.loop = self.w_loop.currentIndex() == 1
        s.preset = self.w_preset.currentData()

    def _on_setting(self, *_):
        if self._updating:
            return
        self.lbl_shape.setText("%d %%" % self.w_shape.value())
        sender = self.sender()
        processing = (self.w_norm, self.w_gain, self.w_hpf, self.w_comp, self.w_thr,
                      self.w_lim, self.w_gate, self.w_shape, self.w_dither)
        if sender in processing and self.w_preset.currentData() != "custom":
            self._updating = True
            self.w_preset.setCurrentIndex(self.w_preset.findData("custom"))
            self._updating = False
        self._widgets_to_settings()
        self._save_settings()
        self._schedule()

    def _on_preset(self, *_):
        if self._updating:
            return
        name = self.w_preset.currentData()
        if name in PRESETS:
            apply_preset(self.settings, name)
            self._settings_to_widgets()
        self._widgets_to_settings()
        self._save_settings()
        self._schedule()

    def _reset_settings(self):
        self.settings = Settings()
        self._settings_to_widgets()
        self._save_settings()
        self._schedule()

    def _save_settings(self):
        self.qs.setValue("settings", json.dumps(self.settings.to_dict()))

    # ============================================================ selection
    def _on_selection(self, s0, s1):
        if self.wav is None:
            return
        for sp, v in ((self.sp_start, s0), (self.sp_end, s1)):
            sp.blockSignals(True)
            sp.setValue(v / float(self.wav.rate))
            sp.blockSignals(False)
        self.lbl_len.setText("= %.3f s" % ((s1 - s0) / float(self.wav.rate)))
        if self.play_mode:
            self.stop_play()
        self._schedule()

    def _on_sel_spin(self, *_):
        if self.wav is None:
            return
        r = self.wav.rate
        self.wave.set_selection(int(round(self.sp_start.value() * r)),
                                int(round(self.sp_end.value() * r)))

    def _on_view(self, v0, v1, total):
        self.hscroll.blockSignals(True)
        self.hscroll.setRange(0, max(0, total - (v1 - v0)))
        self.hscroll.setPageStep(max(1, v1 - v0))
        self.hscroll.setSingleStep(max(1, (v1 - v0) // 20))
        self.hscroll.setValue(v0)
        self.hscroll.blockSignals(False)

    def _on_overlay(self, on):
        self.wave.show_overlay = on
        self.wave.update()
        self.qs.setValue("overlay", "true" if on else "false")

    # ============================================================ conversion
    def _key(self):
        return (self.wave.s0, self.wave.s1, json.dumps(self.settings.to_dict(), sort_keys=True),
                id(self.wav))

    def _max_samples(self):
        return 2 * player_info(self.settings.sample_rate)[1]

    def _schedule(self):
        self._update_state()
        if self.wav is not None:
            self.timer.start()

    def _start_convert(self):
        if self.wav is None:
            return
        self.req_id += 1
        self.busy = True
        job = _ConvertJob(self.req_id, self.mono, self.wav.rate, self.wave.s0, self.wave.s1,
                          replace(self.settings), self._max_samples())
        job.signals.done.connect(self._on_converted)
        self.jobs.append(job)
        job.setAutoDelete(False)
        self._pending_key = self._key()
        self.pool.start(job)
        self._update_state()

    @Slot(int, object, object)
    def _on_converted(self, rid, result, err):
        self.jobs = [j for j in self.jobs if j.args[0] > rid]
        if rid != self.req_id:
            return
        self.busy = False
        if err is not None:
            self.statusBar().showMessage("Conversion failed: %s" % err, 8000)
            return
        self.result = result
        self.result_key = self._pending_key
        self.wave.set_overlay(result.nibbles[:result.samples], result.rate)
        self._update_state()

    def _current_result_sync(self):
        """Up to date result - converts right now if settings changed."""
        if self.wav is None:
            return None
        if self.result is not None and self.result_key == self._key():
            return self.result
        self.timer.stop()
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            self.req_id += 1
            r = convert(self.mono, self.wav.rate, self.wave.s0, self.wave.s1,
                        replace(self.settings), max_samples=self._max_samples())
        finally:
            QApplication.restoreOverrideCursor()
        self.busy = False
        self.result, self.result_key = r, self._key()
        self.wave.set_overlay(r.nibbles[:r.samples], r.rate)
        self._update_state()
        return r

    # ============================================================ state
    def _needed(self):
        """(needed bytes, free bytes) for the current selection."""
        start, free = player_info(self.settings.sample_rate)
        if self.wav is None:
            return 0, free
        n = output_length(self.wave.s1 - self.wave.s0, self.wav.rate, self.settings.sample_rate)
        return (n + 1) // 2, free

    def _update_mem_style(self):
        level = self.mem_bar.property("level") or "ok"
        self.mem_bar.setProperty("level", level)
        self.mem_bar.style().unpolish(self.mem_bar)
        self.mem_bar.style().polish(self.mem_bar)

    def _update_state(self):
        rate = self.settings.sample_rate
        need, free = self._needed()
        max_s = free * 2 / float(rate)
        self.lbl_rate.setText("Frequencies up to %.1f kHz. Max. length at %d Hz: %.1f s." % (
            rate / 2000.0 * 0.95, rate, max_s))
        too_big = need > free
        self.mem_bar.setRange(0, free)
        self.mem_bar.setValue(min(need, free))
        pct = 100.0 * need / free if free else 0
        self.mem_bar.setFormat("%s / %s BYTES  (%d%%)" % (_fmt_bytes(need), _fmt_bytes(free), pct))
        level = "bad" if too_big else ("warn" if pct > 85 else "ok")
        if self.mem_bar.property("level") != level:
            self.mem_bar.setProperty("level", level)
            self._update_mem_style()
        if self.wav is None:
            self.lbl_mem.setText("The C64 has room for %s bytes of sample data ($%04X–$CFFF). "
                                 "At %d Hz that is %.1f seconds." % (
                                     _fmt_bytes(free), 0xD000 - free, rate, max_s))
        elif too_big:
            over = (need - free) * 2 / float(rate)
            self.lbl_mem.setText("<b>Too big!</b> The selection needs %.2f s less – trim it "
                                 "or lower the sample rate (max. %.1f s at %d Hz)." % (over, max_s, rate))
        else:
            self.lbl_mem.setText("Fits. %s bytes left (%.1f s more possible)." % (
                _fmt_bytes(free - need), (free - need) * 2 / float(rate)))

        r = self.result
        fresh = r is not None and self.result_key == self._key()
        if self.wav is None:
            self.lbl_result.setText("")
        elif not fresh:
            self.lbl_result.setText("Converting…")
        else:
            snr = "%.1f dB" % r.snr_db if r.snr_db is not None else "–"
            self.lbl_result.setText("%s samples · %s bytes · %.2f s · noise distance %s" % (
                _fmt_bytes(r.samples), _fmt_bytes(r.data_bytes), r.duration, snr))
        can = (self.wav is not None and not too_big and self.wave.s1 > self.wave.s0)
        self.btn_export.setEnabled(can)
        self.btn_export.setToolTip("Write .prg, .asm and .txt into a folder (Ctrl+E)" if can else
                                   "Load a WAV file and make sure the selection fits into memory.")
        self.btn_play_c64.setEnabled(self.player is not None and self.wav is not None)
        self.btn_play_orig.setEnabled(self.player is not None and self.wav is not None)
        self._update_info()

    # ============================================================ info text
    def _update_info(self):
        t = self.theme
        s = self.settings
        w = self.wav
        acc = t["accent2"]
        h = ["<style>h3{color:%s;margin-top:14px} li{margin-bottom:4px} "
             "td{padding:2px 8px 2px 0}</style>" % acc]
        h.append("<h3>What WAV2C64 does</h3><p>The C64 has no sample hardware. A trick "
                 "plays sound anyway: the SID volume register <tt>$D418</tt> has 16 levels. "
                 "Changing it thousands of times per second turns it into a simple 4-bit "
                 "D/A converter. WAV2C64 prepares your WAV file for exactly that.</p>")
        h.append("<h3>Steps for your file</h3><ol>")
        if w is None:
            h.append("<li>Open a WAV file (8/16/24/32 bit or float, any rate, mono or stereo).</li>")
        else:
            sel = (self.wave.s1 - self.wave.s0) / float(w.rate)
            h.append("<li><b>Load:</b> %d Hz, %d bit, %s%s.</li>" % (
                w.rate, w.bits, "mono" if w.channels == 1 else "%d channels" % w.channels,
                " → mixed to mono" if w.channels > 1 else ""))
            h.append("<li><b>Trim:</b> %.3f s – %.3f s (%.3f s).</li>" % (
                self.wave.s0 / float(w.rate), self.wave.s1 / float(w.rate), sel))
            h.append("<li><b>Resample</b> %d → %d Hz with a band limited filter. Everything "
                     "above %.1f kHz is removed (it would only cause distortion).</li>" % (
                         w.rate, s.sample_rate, s.sample_rate / 2000.0 * 0.95))
            steps = ["remove DC offset"]
            if s.highpass_hz > 0:
                steps.append("high-pass %d Hz" % s.highpass_hz)
            if s.normalize:
                steps.append("normalize")
            if s.comp_ratio > 1:
                steps.append("compressor %.1f:1 above %d dB" % (s.comp_ratio, s.comp_threshold_db))
            if s.limiter_db > 0:
                steps.append("limiter +%d dB" % s.limiter_db)
            if s.gate_db < 0:
                steps.append("noise gate below %d dB" % s.gate_db)
            if s.gain_db:
                steps.append("gain %+.1f dB" % s.gain_db)
            h.append("<li><b>Shape the sound:</b> %s. Goal: use all 16 levels, so the "
                     "4-bit noise stays far below the signal.</li>" % ", ".join(steps))
            q = "<li><b>Quantize to 4 bit</b> (levels 0–15). Silence lands exactly on level 8 " \
                "so pauses are really quiet"
            if s.noise_shaping > 0:
                q += "; noise shaping %d %% moves the noise to high frequencies" % (s.noise_shaping * 100)
            if s.dither:
                q += "; dither on"
            h.append(q + ".</li>")
            r = self.result
            if r is not None and self.result_key == self._key():
                h.append("<li><b>Pack</b> 2 samples per byte: %s bytes. Noise distance about "
                         "%s.</li>" % (_fmt_bytes(r.data_bytes),
                                       "%.1f dB" % r.snr_db if r.snr_db else "–"))
            h.append("<li><b>Export:</b> <tt>name.txt</tt> (data as <tt>!byte</tt> lines), "
                     "<tt>name.asm</tt> (player for ACME, includes the .txt) and "
                     "<tt>name.prg</tt> (already assembled - ACME is not needed).</li>")
        h.append("</ol>")
        timer_pal = 985248 // s.sample_rate - 1
        h.append("<h3>What happens on the C64</h3><ul>"
                 "<li>The program detects <b>PAL or NTSC</b> (raster lines) and the <b>SID "
                 "chip</b> (oscillator 3 read-back)%s.</li>"
                 "<li>On an <b>8580</b> SID it switches on the <b>digi boost</b> - otherwise "
                 "the new SID is almost silent.</li>"
                 "<li>BASIC and KERNAL ROM are switched off, so the sample can use RAM up to "
                 "<tt>$CFFF</tt>.</li>"
                 "<li>CIA 2 timer A fires an <b>NMI</b> every %d cycles (PAL) = exactly %d Hz. "
                 "Each NMI writes the next 4-bit value to <tt>$D418</tt>.</li>"
                 "<li>Keys: <b>SPACE</b> = play again, <b>Q</b> = quit to BASIC. "
                 "<tt>RUN</tt> works again afterwards.</li></ul>" % (
                     "" if s.machine == 0 and s.sid == 0 else " (or uses your fixed choice)",
                     timer_pal + 1, s.sample_rate))
        h.append("<h3>Tips</h3><ul>"
                 "<li>Listen with <b>▶ C64 4-bit</b> before exporting - it simulates the 16 "
                 "volume steps.</li>"
                 "<li>Speech: 6000–8000 Hz is fine. Music: 8000–11025 Hz.</li>"
                 "<li>Too big? Trim the selection or lower the sample rate.</li>"
                 "<li>Load the PRG in VICE or on a real C64: <tt>LOAD\"NAME\",8</tt> and "
                 "<tt>RUN</tt>.</li></ul>")
        self.info.setHtml("".join(h))

    # ============================================================ export
    def export(self):
        if not self.btn_export.isEnabled():
            return
        self.stop_play()
        folder = self.qs.value("export_dir", os.path.expanduser("~"))
        name = getattr(self, "suggested_name", None) or self.qs.value("project_name", "sample")
        dlg = ExportDialog(self, folder, name)
        if dlg.exec() != ExportDialog.Accepted:
            return
        folder, name = dlg.result_values()
        r = self._current_result_sync()
        if r is None or r.truncated or r.samples == 0:
            QMessageBox.warning(self, "Export", "The selection does not fit into the C64 memory.")
            return
        sel = (self.wave.s0 / float(self.wav.rate), self.wave.s1 / float(self.wav.rate))
        try:
            files = build_project(name, r, self.settings,
                                  os.path.basename(self.wav.path), sel)
            written = write_project(folder, files)
        except Exception as e:
            QMessageBox.critical(self, "Export failed", str(e))
            return
        self.qs.setValue("export_dir", folder)
        self.qs.setValue("project_name", name)
        self.suggested_name = name
        box = QMessageBox(self)
        box.setWindowTitle("Export finished")
        box.setText("Written to %s:\n\n%s\n\nOn the C64: LOAD\"%s\",8 and RUN" % (
            folder, "\n".join(os.path.basename(p) for p in written), name.upper()))
        open_btn = box.addButton("Open folder", QMessageBox.ActionRole)
        box.addButton(QMessageBox.Ok)
        box.exec()
        if box.clickedButton() == open_btn:
            QDesktopServices.openUrl(QUrl.fromLocalFile(folder))

    # ============================================================ close
    def closeEvent(self, ev):
        self.stop_play()
        self.qs.setValue("geometry", self.saveGeometry())
        self.qs.setValue("splitter", self.splitter.saveState())
        self._save_settings()
        self.pool.waitForDone(3000)
        super().closeEvent(ev)
