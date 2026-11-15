"""Waveform view with zoom, scrolling and a trim selection."""

import math

import numpy as np
from PySide6.QtCore import Qt, Signal, QRectF, QPointF
from PySide6.QtGui import QColor, QPainter, QPen, QPolygonF, QFont
from PySide6.QtWidgets import QWidget, QSizePolicy

HANDLE_PX = 7


class WaveformView(QWidget):
    """Shows a mono signal. Mouse:
       drag the yellow handles or the selection edges -> trim
       drag in the wave -> new selection,  double click -> select all
       wheel -> zoom at the mouse,  Shift + wheel -> scroll"""

    selectionChanged = Signal(int, int)   # frames
    viewChanged = Signal(int, int, int)   # view start, view end, total

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(170)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.data = None
        self.rate = 1
        self.v0 = self.v1 = 0
        self.s0 = self.s1 = 0
        self.overlay = None           # (nibbles, rate) of the converted signal
        self.show_overlay = True
        self.fades = (0, 0)           # fade in / fade out length in frames
        self.playhead = None          # frame or None
        self.theme = None
        self._drag = None
        self._press_frame = 0
        self._peak_cache = (None, 1.0)

    # ---------------- data ----------------------------------------------
    def set_theme(self, theme):
        self.theme = theme
        self.update()

    def set_data(self, mono, rate):
        self.data = np.asarray(mono, dtype=np.float32)
        self.rate = rate
        n = len(self.data)
        self.v0, self.v1 = 0, max(1, n)
        self.s0, self.s1 = 0, n
        self.overlay = None
        self.playhead = None
        self._emit_view()
        self.selectionChanged.emit(self.s0, self.s1)
        self.update()

    def total(self):
        return 0 if self.data is None else len(self.data)

    def set_selection(self, s0, s1, emit=True):
        n = self.total()
        s0, s1 = int(max(0, min(n, s0))), int(max(0, min(n, s1)))
        if s1 < s0:
            s0, s1 = s1, s0
        if (s0, s1) != (self.s0, self.s1):
            self.s0, self.s1 = s0, s1
            if emit:
                self.selectionChanged.emit(s0, s1)
            self.update()

    def set_overlay(self, nibbles, rate):
        self.overlay = None if nibbles is None else (nibbles, rate)
        self.update()

    def set_fades(self, fade_in, fade_out):
        f = (int(fade_in), int(fade_out))
        if f != self.fades:
            self.fades = f
            self.update()

    def set_playhead(self, frame):
        self.playhead = frame
        self.update()

    # ---------------- view ----------------------------------------------
    def _emit_view(self):
        self.viewChanged.emit(int(self.v0), int(self.v1), self.total())

    def set_view(self, v0, v1):
        n = self.total()
        if n == 0:
            return
        span = max(32, min(n, int(v1 - v0)))
        v0 = int(max(0, min(n - span, v0)))
        self.v0, self.v1 = v0, v0 + span
        self._emit_view()
        self.update()

    def zoom(self, factor, center=None):
        if self.data is None:
            return
        c = (self.v0 + self.v1) / 2.0 if center is None else center
        span = (self.v1 - self.v0) / factor
        rel = (c - self.v0) / float(max(1, self.v1 - self.v0))
        self.set_view(c - rel * span, c - rel * span + span)

    def zoom_fit(self):
        self.set_view(0, self.total())

    def zoom_selection(self):
        if self.s1 > self.s0:
            pad = (self.s1 - self.s0) * 0.05
            self.set_view(self.s0 - pad, self.s1 + pad)

    def scroll_to(self, v0):
        self.set_view(v0, v0 + (self.v1 - self.v0))

    # ---------------- coordinates ---------------------------------------
    def _x(self, frame):
        w = max(1, self.width())
        return (frame - self.v0) / float(max(1, self.v1 - self.v0)) * w

    def _frame(self, x):
        w = max(1, self.width())
        return self.v0 + x / float(w) * (self.v1 - self.v0)

    # ---------------- painting ------------------------------------------
    def paintEvent(self, ev):
        t = self.theme
        p = QPainter(self)
        w, h = self.width(), self.height()
        if t is None:
            return
        p.fillRect(self.rect(), QColor(t["wave_bg"]))
        ruler = 18
        mid = ruler + (h - ruler) / 2.0
        amp = (h - ruler) / 2.0 - 6
        if self.data is None or self.total() == 0:
            p.setPen(QColor(t["muted"]))
            f = QFont(p.font())
            f.setFamily("Press Start 2P")
            f.setPointSize(8)
            p.setFont(f)
            p.drawText(self.rect(), Qt.AlignCenter,
                       "OPEN A WAV FILE\nOR DROP IT HERE")
            return
        # grid + ruler
        self._draw_ruler(p, w, ruler, t)
        p.setPen(QPen(QColor(t["grid"]), 1))
        p.drawLine(0, int(mid), w, int(mid))
        # waveform
        self._draw_wave(p, w, mid, amp, QColor(t["wave"]))
        # converted 4 bit signal
        if self.show_overlay and self.overlay is not None:
            self._draw_overlay(p, mid, amp, QColor(t["overlay"]))
        # dim outside the selection
        dim = QColor(t["wave_bg"])
        dim.setAlpha(t["dim_alpha"])
        x0, x1 = self._x(self.s0), self._x(self.s1)
        if x0 > 0:
            p.fillRect(QRectF(0, ruler, min(w, x0), h - ruler), dim)
        if x1 < w:
            p.fillRect(QRectF(max(0, x1), ruler, w - max(0, x1), h - ruler), dim)
        sel = QColor(t["sel"])
        sel.setAlpha(t["sel_alpha"])
        p.fillRect(QRectF(max(0, x0), ruler, max(0, min(w, x1) - max(0, x0)), h - ruler), sel)
        # fade envelope
        self._draw_fades(p, mid, amp, t)
        # handles
        hc = QColor(t["playhead"] if t["name"] == "night" else t["accent2"])
        for x in (x0, x1):
            if -HANDLE_PX <= x <= w + HANDLE_PX:
                p.setPen(QPen(hc, 2))
                p.drawLine(QPointF(x, ruler), QPointF(x, h))
                p.fillRect(QRectF(x - HANDLE_PX, ruler, 2 * HANDLE_PX, 10), hc)
        # play head
        if self.playhead is not None:
            x = self._x(self.playhead)
            p.setPen(QPen(QColor(t["playhead"]), 2))
            p.drawLine(QPointF(x, ruler), QPointF(x, h))

    def _draw_fades(self, p, mid, amp, t):
        fi, fo = self.fades
        if not (fi or fo) or self.s1 <= self.s0:
            return
        shade = QColor(t["wave_bg"])
        shade.setAlpha(150)
        line = QColor(t["playhead"] if t["name"] == "night" else t["accent2"])
        pen = QPen(line, 1.5, Qt.DashLine)
        top, bot = mid - amp, mid + amp
        for a, b, rising in ((self.s0, self.s0 + fi, True), (self.s1 - fo, self.s1, False)):
            if b <= a:
                continue
            xa, xb = self._x(a), self._x(b)
            if xb < 0 or xa > self.width():
                continue
            x0 = xa if rising else xb           # the point where the volume is 0
            x1 = xb if rising else xa           # full volume
            # area outside the envelope is shaded
            p.setPen(Qt.NoPen)
            p.setBrush(shade)
            p.drawPolygon(QPolygonF([QPointF(x0, top), QPointF(x1, top), QPointF(x0, mid)]))
            p.drawPolygon(QPolygonF([QPointF(x0, bot), QPointF(x1, bot), QPointF(x0, mid)]))
            p.setBrush(Qt.NoBrush)
            p.setPen(pen)
            p.drawLine(QPointF(x0, mid), QPointF(x1, top))
            p.drawLine(QPointF(x0, mid), QPointF(x1, bot))

    def _draw_ruler(self, p, w, ruler, t):
        p.fillRect(0, 0, w, ruler, QColor(t["panel"]))
        span_s = (self.v1 - self.v0) / float(self.rate)
        target = span_s / max(1, w / 90.0)
        steps = [0.001, 0.002, 0.005, 0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1, 2, 5, 10, 20, 30, 60]
        step = next((s for s in steps if s >= target), 60)
        f = QFont(p.font())
        f.setPointSize(7)
        p.setFont(f)
        p.setPen(QColor(t["muted"]))
        first = math.ceil(self.v0 / float(self.rate) / step) * step
        tt = first
        while tt <= self.v1 / float(self.rate):
            x = self._x(tt * self.rate)
            p.drawLine(int(x), ruler - 5, int(x), ruler)
            label = ("%.3f" % tt) if step < 0.01 else ("%.2f" % tt) if step < 0.1 else ("%.1f" % tt)
            p.drawText(int(x) + 3, ruler - 6, label + "s")
            tt += step
        p.setPen(QPen(QColor(t["border"]), 1))
        p.drawLine(0, ruler, w, ruler)

    def _draw_wave(self, p, w, mid, amp, color):
        v0, v1 = int(self.v0), int(self.v1)
        seg = self.data[v0:v1]
        if len(seg) == 0:
            return
        spp = len(seg) / float(w)
        p.setPen(QPen(color, 1))
        if spp > 2:
            edges = (np.arange(w + 1) * spp).astype(np.int64)
            edges = np.clip(edges, 0, len(seg) - 1)
            starts = edges[:-1]
            mins = np.minimum.reduceat(seg, starts)
            maxs = np.maximum.reduceat(seg, starts)
            for x in range(w):
                y0 = mid - maxs[x] * amp
                y1 = mid - mins[x] * amp
                p.drawLine(QPointF(x + 0.5, y0), QPointF(x + 0.5, max(y1, y0 + 1)))
        else:
            xs = (np.arange(len(seg)) / max(1e-9, spp))
            poly = QPolygonF([QPointF(float(x), float(mid - v * amp)) for x, v in zip(xs, seg)])
            p.drawPolyline(poly)
            if spp < 0.12:
                for pt in poly:
                    p.drawEllipse(pt, 1.5, 1.5)

    def _selection_peak(self):
        key = (self.s0, self.s1, id(self.data))
        if self._peak_cache[0] != key:
            seg = self.data[self.s0:self.s1]
            pk = float(np.max(np.abs(seg))) if len(seg) else 1.0
            self._peak_cache = (key, pk if pk > 1e-6 else 1.0)
        return self._peak_cache[1]

    def _draw_overlay(self, p, mid, amp, color):
        nib, rate = self.overlay
        n = len(nib)
        if n == 0:
            return
        # full 4-bit range = peak of the original selection, so both curves
        # can be compared directly
        amp = amp * self._selection_peak()
        # nibble i covers source frames s0 + i*ratio ... s0 + (i+1)*ratio
        ratio = self.rate / float(rate)
        i0 = max(0, int((self.v0 - self.s0) / ratio) - 1)
        i1 = min(n, int((self.v1 - self.s0) / ratio) + 2)
        if i1 <= i0:
            return
        w = self.width()
        count = i1 - i0
        pen = QPen(color, 2.0)
        p.setPen(pen)
        levels = (nib[i0:i1].astype(np.float32) - 7.5) / 7.5
        if count > 2 * w:
            # too dense for steps: draw min/max per pixel, half transparent
            c = QColor(color)
            c.setAlpha(110)
            p.setPen(QPen(c, 1))
            spp = count / float(w)
            edges = np.clip((np.arange(w + 1) * spp).astype(np.int64), 0, count - 1)
            mins = np.minimum.reduceat(levels, edges[:-1])
            maxs = np.maximum.reduceat(levels, edges[:-1])
            x_start = self._x(self.s0 + i0 * ratio)
            x_end = self._x(self.s0 + i1 * ratio)
            scale = (x_end - x_start) / float(w)
            for x in range(w):
                xx = x_start + x * scale
                p.drawLine(QPointF(xx, mid - maxs[x] * amp), QPointF(xx, mid - mins[x] * amp))
            return
        pts = []
        for k in range(count):
            xa = self._x(self.s0 + (i0 + k) * ratio)
            xb = self._x(self.s0 + (i0 + k + 1) * ratio)
            y = mid - float(levels[k]) * amp
            pts.append(QPointF(xa, y))
            pts.append(QPointF(xb, y))
        p.drawPolyline(QPolygonF(pts))

    # ---------------- mouse ---------------------------------------------
    def _hit_handle(self, x):
        for name, f in (("s0", self.s0), ("s1", self.s1)):
            if abs(self._x(f) - x) <= HANDLE_PX:
                return name
        return None

    def mousePressEvent(self, ev):
        if self.data is None or ev.button() != Qt.LeftButton:
            return
        x = ev.position().x()
        h = self._hit_handle(x)
        if h:
            self._drag = h
        else:
            self._drag = "new"
            self._press_frame = int(self._frame(x))
        self.setCursor(Qt.SizeHorCursor)

    def mouseMoveEvent(self, ev):
        if self.data is None:
            return
        x = ev.position().x()
        f = int(round(self._frame(x)))
        if self._drag == "s0":
            if f > self.s1:
                self._drag = "s1"
                self.set_selection(self.s1, f)
            else:
                self.set_selection(f, self.s1)
        elif self._drag == "s1":
            if f < self.s0:
                self._drag = "s0"
                self.set_selection(f, self.s0)
            else:
                self.set_selection(self.s0, f)
        elif self._drag == "new":
            if abs(f - self._press_frame) * self.width() / max(1, self.v1 - self.v0) > 3:
                self.set_selection(min(f, self._press_frame), max(f, self._press_frame))
        else:
            self.setCursor(Qt.SizeHorCursor if self._hit_handle(x) else Qt.IBeamCursor)

    def mouseReleaseEvent(self, ev):
        self._drag = None
        self.setCursor(Qt.IBeamCursor)

    def mouseDoubleClickEvent(self, ev):
        if self.data is not None:
            self.set_selection(0, self.total())

    def wheelEvent(self, ev):
        if self.data is None:
            return
        d = ev.angleDelta().y() or ev.angleDelta().x()
        if d == 0:
            return
        if ev.modifiers() & Qt.ShiftModifier or abs(ev.angleDelta().x()) > abs(ev.angleDelta().y()):
            span = self.v1 - self.v0
            self.scroll_to(self.v0 - d / 120.0 * span * 0.1)
        else:
            self.zoom(1.25 if d > 0 else 0.8, self._frame(ev.position().x()))
        ev.accept()
