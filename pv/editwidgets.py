"""Widgets used by the editor: sliders, histogram, levels, curves, collapsible sections."""
from __future__ import annotations

import colorsys
import math

import numpy as np
from PySide6.QtCore import Qt, Signal, QEvent, QPointF, QRectF, QSize
from PySide6.QtGui import QPainter, QColor, QPen, QPainterPath, QLinearGradient, QPolygonF, QBrush
from PySide6.QtWidgets import (QWidget, QLabel, QSlider, QDoubleSpinBox, QGridLayout, QVBoxLayout,
                               QHBoxLayout, QToolButton, QSizePolicy, QAbstractSpinBox)

from .imageops import curve_eval, ID_LEVELS, ID_CURVE, CHANNELS


def hex_hsv(h, s=1.0, v=1.0):
    r, g, b = colorsys.hsv_to_rgb((h % 360) / 360.0, s, v)
    return '#%02x%02x%02x' % (int(r * 255), int(g * 255), int(b * 255))


def gradient_css(stops):
    n = len(stops)
    s = ', '.join(f'stop:{i / (n - 1):.3f} {c}' for i, c in enumerate(stops))
    return ("QSlider::groove:horizontal { height: 6px; border-radius: 3px; "
            "background: qlineargradient(x1:0, y1:0, x2:1, y2:0, %s); }"
            "QSlider::sub-page:horizontal { background: transparent; }"
            "QSlider::handle:horizontal { background: #f2f2f2; border: 1px solid #1c1c1e; width: 12px; "
            "height: 12px; margin: -4px 0; border-radius: 7px; }") % s


class _Slider(QSlider):
    def wheelEvent(self, ev):
        if self.hasFocus():
            super().wheelEvent(ev)
        else:
            ev.ignore()


class _Spin(QDoubleSpinBox):
    def wheelEvent(self, ev):
        if self.hasFocus():
            super().wheelEvent(ev)
        else:
            ev.ignore()


class ParamSlider(QWidget):
    """Label + numeric box + slider. Double-click the label or slider to reset."""
    valueChanged = Signal(object)
    pressed = Signal()
    released = Signal()

    def __init__(self, label, vmin, vmax, default=0.0, decimals=0, gradient=None, suffix='', parent=None):
        super().__init__(parent)
        self._f = 10 ** decimals
        self._dec = decimals
        self._default = default
        self.lbl = QLabel(label)
        self.spin = _Spin()
        self.spin.setDecimals(decimals)
        self.spin.setRange(vmin, vmax)
        self.spin.setSingleStep(1.0 / self._f if decimals else 1.0)
        self.spin.setAlignment(Qt.AlignRight)
        self.spin.setKeyboardTracking(False)
        self.spin.setObjectName('ParamSpin')  # width follows the font size (theme: 4.6em)
        self.spin.setFocusPolicy(Qt.ClickFocus)
        if suffix:
            self.spin.setSuffix(suffix)
        self.slider = _Slider(Qt.Horizontal)
        self.slider.setRange(int(round(vmin * self._f)), int(round(vmax * self._f)))
        self.slider.setFocusPolicy(Qt.StrongFocus)
        self.slider.setPageStep(max(1, int((vmax - vmin) * self._f / 20)))
        if gradient:
            self.slider.setStyleSheet(gradient_css(gradient))
        g = QGridLayout(self)
        g.setContentsMargins(2, 2, 2, 2)
        g.setVerticalSpacing(1)
        g.addWidget(self.lbl, 0, 0)
        g.addWidget(self.spin, 0, 1, Qt.AlignRight)
        g.addWidget(self.slider, 1, 0, 1, 2)
        self.slider.valueChanged.connect(self._on_slider)
        self.spin.valueChanged.connect(self._on_spin)
        self.slider.sliderPressed.connect(self.pressed)
        self.slider.sliderReleased.connect(self.released)
        self.slider.installEventFilter(self)
        self.lbl.installEventFilter(self)
        self.setToolTip('雙擊可重設為預設值')
        self.setValue(default)

    def _norm(self, v):
        return round(float(v), self._dec) if self._dec else int(round(v))

    def _on_slider(self, iv):
        v = iv / self._f
        self.spin.blockSignals(True)
        self.spin.setValue(v)
        self.spin.blockSignals(False)
        self.valueChanged.emit(self._norm(v))

    def _on_spin(self, v):
        self.slider.blockSignals(True)
        self.slider.setValue(int(round(v * self._f)))
        self.slider.blockSignals(False)
        self.valueChanged.emit(self._norm(v))

    def value(self):
        return self._norm(self.spin.value())

    def setValue(self, v):
        self.slider.blockSignals(True)
        self.spin.blockSignals(True)
        self.spin.setValue(float(v))
        self.slider.setValue(int(round(float(v) * self._f)))
        self.spin.blockSignals(False)
        self.slider.blockSignals(False)

    def reset(self):
        self.setValue(self._default)
        self.valueChanged.emit(self._norm(self._default))

    def eventFilter(self, obj, ev):
        if ev.type() == QEvent.MouseButtonDblClick:
            self.reset()
            return True
        return False


class Section(QWidget):
    """Collapsible panel section with a header button and optional reset button."""

    def __init__(self, title, content: QWidget, expanded=False, on_reset=None, parent=None):
        super().__init__(parent)
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 1)
        v.setSpacing(0)
        hdr = QWidget()
        h = QHBoxLayout(hdr)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)
        self.btn = QToolButton()
        self.btn.setObjectName('SectionHeader')
        self.btn.setText(' ' + title)
        self.btn.setCheckable(True)
        self.btn.setChecked(expanded)
        self.btn.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.btn.setArrowType(Qt.DownArrow if expanded else Qt.RightArrow)
        self.btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        h.addWidget(self.btn, 1)
        if on_reset:
            rb = QToolButton()
            rb.setObjectName('SectionReset')
            rb.setText('重設')
            rb.setToolTip('將此區塊恢復為預設值')
            rb.clicked.connect(on_reset)
            h.addWidget(rb)
        v.addWidget(hdr)
        self.content = content
        content.setContentsMargins(8, 6, 8, 8)
        v.addWidget(content)
        content.setVisible(expanded)
        self.btn.toggled.connect(self._toggle)

    def _toggle(self, on):
        self.content.setVisible(on)
        self.btn.setArrowType(Qt.DownArrow if on else Qt.RightArrow)

    def set_expanded(self, on):
        self.btn.setChecked(on)


# --------------------------------------------------------------------------- histogram
class HistogramWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.data = None
        self.setMinimumHeight(96)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setFixedHeight(104)

    def set_data(self, hist):
        self.data = hist
        self.update()

    def paintEvent(self, ev):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(22, 22, 24))
        r = QRectF(self.rect()).adjusted(6, 6, -6, -6)
        p.setPen(QPen(QColor(48, 48, 52), 1))
        for i in range(1, 4):
            x = r.left() + r.width() * i / 4.0
            p.drawLine(QPointF(x, r.top()), QPointF(x, r.bottom()))
        if self.data is None:
            p.end()
            return
        rr, gg, bb, ll = self.data
        m = float(max(rr[2:254].max(), gg[2:254].max(), bb[2:254].max(), 1))
        p.setRenderHint(QPainter.Antialiasing)

        def path_for(arr):
            path = QPainterPath()
            path.moveTo(r.left(), r.bottom())
            for i in range(256):
                x = r.left() + r.width() * i / 255.0
                y = r.bottom() - min(1.0, arr[i] / m) * r.height()
                path.lineTo(x, y)
            path.lineTo(r.right(), r.bottom())
            path.closeSubpath()
            return path

        p.setCompositionMode(QPainter.CompositionMode_Plus)
        p.setPen(Qt.NoPen)
        for arr, col in ((rr, QColor(190, 40, 40, 200)), (gg, QColor(40, 170, 50, 200)), (bb, QColor(40, 80, 220, 200))):
            p.setBrush(col)
            p.drawPath(path_for(arr))
        p.setCompositionMode(QPainter.CompositionMode_SourceOver)
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QColor(220, 220, 220, 140), 1))
        p.drawPath(path_for(ll))
        p.end()


# --------------------------------------------------------------------------- curves
CH_COLORS = {'rgb': QColor(235, 235, 235), 'r': QColor(235, 85, 85), 'g': QColor(85, 200, 95), 'b': QColor(90, 140, 245)}


class CurvesWidget(QWidget):
    curvesChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.curves = {c: [list(p) for p in ID_CURVE] for c in CHANNELS}
        self.ch = 'rgb'
        self.hist = None
        self.drag = None
        self.setMinimumSize(220, 220)
        sp = QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        sp.setHeightForWidth(True)
        self.setSizePolicy(sp)
        self.setMouseTracking(True)
        self.setToolTip('點擊新增控制點，拖曳調整；右鍵或拖出範圍可刪除控制點')

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, w):
        return w

    def sizeHint(self):
        return QSize(260, 260)

    def set_channel(self, ch):
        self.ch = ch
        self.drag = None
        self.update()

    def set_curves(self, curves):
        self.curves = {c: [list(p) for p in curves[c]] for c in CHANNELS}
        self.update()

    def get_curves(self):
        return {c: [list(p) for p in self.curves[c]] for c in CHANNELS}

    def set_histogram(self, hist):
        self.hist = hist
        self.update()

    def _rect(self):
        m = 8
        side = min(self.width(), self.height()) - 2 * m
        x = (self.width() - side) / 2.0
        return QRectF(x, m, side, side)

    def _to_px(self, x, y):
        r = self._rect()
        return QPointF(r.left() + x / 255.0 * r.width(), r.bottom() - y / 255.0 * r.height())

    def _from_px(self, pt):
        r = self._rect()
        x = (pt.x() - r.left()) / r.width() * 255.0
        y = (r.bottom() - pt.y()) / r.height() * 255.0
        return x, y

    def paintEvent(self, ev):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(37, 37, 39))
        r = self._rect()
        p.fillRect(r, QColor(22, 22, 24))
        if self.hist is not None:
            idx = {'rgb': 3, 'r': 0, 'g': 1, 'b': 2}[self.ch]
            arr = self.hist[idx]
            m = float(max(arr[2:254].max(), 1))
            path = QPainterPath()
            path.moveTo(r.left(), r.bottom())
            for i in range(256):
                path.lineTo(r.left() + r.width() * i / 255.0, r.bottom() - min(1.0, arr[i] / m) * r.height() * 0.9)
            path.lineTo(r.right(), r.bottom())
            c = QColor(CH_COLORS[self.ch])
            c.setAlpha(45)
            p.fillPath(path, c)
        p.setPen(QPen(QColor(55, 55, 60), 1))
        for i in range(1, 4):
            x = r.left() + r.width() * i / 4.0
            y = r.top() + r.height() * i / 4.0
            p.drawLine(QPointF(x, r.top()), QPointF(x, r.bottom()))
            p.drawLine(QPointF(r.left(), y), QPointF(r.right(), y))
        p.setPen(QPen(QColor(85, 85, 90), 1, Qt.DashLine))
        p.drawLine(r.bottomLeft(), r.topRight())
        p.setRenderHint(QPainter.Antialiasing)
        xs = np.linspace(0, 1, 129, dtype=np.float32)
        for ch in CHANNELS:
            pts = self.curves[ch]
            if ch != self.ch and pts == [list(q) for q in ID_CURVE]:
                continue
            ys = curve_eval(pts, xs)
            path = QPainterPath()
            for i, (x, y) in enumerate(zip(xs, ys)):
                pt = QPointF(r.left() + x * r.width(), r.bottom() - y * r.height())
                path.moveTo(pt) if i == 0 else path.lineTo(pt)
            c = QColor(CH_COLORS[ch])
            if ch != self.ch:
                c.setAlpha(90)
            p.setPen(QPen(c, 2 if ch == self.ch else 1))
            p.setBrush(Qt.NoBrush)
            p.drawPath(path)
        p.setPen(QPen(QColor(20, 20, 20), 1))
        for i, (x, y) in enumerate(self.curves[self.ch]):
            pt = self._to_px(x, y)
            p.setBrush(QColor(255, 255, 255) if i == self.drag else QColor(200, 200, 205))
            p.drawRect(QRectF(pt.x() - 4, pt.y() - 4, 8, 8))
        p.end()

    def _hit(self, pos):
        best, bd = None, 10.0
        for i, (x, y) in enumerate(self.curves[self.ch]):
            pt = self._to_px(x, y)
            d = math.hypot(pt.x() - pos.x(), pt.y() - pos.y())
            if d < bd:
                best, bd = i, d
        return best

    def mousePressEvent(self, ev):
        pts = self.curves[self.ch]
        pos = ev.position()
        hit = self._hit(pos)
        if ev.button() == Qt.RightButton:
            if hit is not None and 0 < hit < len(pts) - 1:
                del pts[hit]
                self.drag = None
                self.curvesChanged.emit()
                self.update()
            return
        if ev.button() != Qt.LeftButton:
            return
        if hit is None:
            x, y = self._from_px(pos)
            x = int(round(max(0, min(255, x))))
            y = int(round(max(0, min(255, y))))
            if any(abs(q[0] - x) < 3 for q in pts):
                return
            i = next((k for k, q in enumerate(pts) if q[0] > x), len(pts))
            pts.insert(i, [x, y])
            hit = i
            self.curvesChanged.emit()
        self.drag = hit
        self.update()

    def mouseMoveEvent(self, ev):
        if self.drag is None or not (ev.buttons() & Qt.LeftButton):
            return
        pts = self.curves[self.ch]
        i = self.drag
        pos = ev.position()
        r = self._rect()
        if 0 < i < len(pts) - 1 and (pos.y() < r.top() - 25 or pos.y() > r.bottom() + 25):
            del pts[i]
            self.drag = None
            self.curvesChanged.emit()
            self.update()
            return
        x, y = self._from_px(pos)
        lo = pts[i - 1][0] + 1 if i > 0 else 0
        hi = pts[i + 1][0] - 1 if i < len(pts) - 1 else 255
        x = int(round(max(lo, min(hi, x))))
        y = int(round(max(0, min(255, y))))
        if pts[i] != [x, y]:
            pts[i] = [x, y]
            self.curvesChanged.emit()
            self.update()

    def mouseReleaseEvent(self, ev):
        self.drag = None
        self.update()


# --------------------------------------------------------------------------- levels
class LevelsWidget(QWidget):
    levelsChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.levels = {c: list(ID_LEVELS) for c in CHANNELS}
        self.ch = 'rgb'
        self.hist = None
        self.drag = None
        self.setMinimumHeight(170)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setToolTip('拖曳三角形調整黑點、中間調與白點；下方為輸出範圍')

    def set_channel(self, ch):
        self.ch = ch
        self.update()

    def set_levels(self, levels):
        self.levels = {c: list(levels[c]) for c in CHANNELS}
        self.update()

    def get_levels(self):
        return {c: list(self.levels[c]) for c in CHANNELS}

    def set_histogram(self, hist):
        self.hist = hist
        self.update()

    def _geo(self):
        m = 10
        hist = QRectF(m, 4, self.width() - 2 * m, self.height() - 74)
        in_y = hist.bottom() + 2
        out_bar = QRectF(m, hist.bottom() + 26, hist.width(), 10)
        out_y = out_bar.bottom() + 2
        return hist, in_y, out_bar, out_y

    def _x(self, v):
        hist = self._geo()[0]
        return hist.left() + v / 255.0 * hist.width()

    def _gray_val(self):
        ib, gm, iw = self.levels[self.ch][:3]
        return ib + (iw - ib) * (0.5 ** gm)

    def _tri(self, p, x, y, fill):
        poly = QPolygonF([QPointF(x, y), QPointF(x - 6, y + 11), QPointF(x + 6, y + 11)])
        p.setBrush(fill)
        p.setPen(QPen(QColor(150, 150, 155), 1))
        p.drawPolygon(poly)

    def paintEvent(self, ev):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(37, 37, 39))
        hist, in_y, out_bar, out_y = self._geo()
        p.fillRect(hist, QColor(22, 22, 24))
        if self.hist is not None:
            idx = {'rgb': 3, 'r': 0, 'g': 1, 'b': 2}[self.ch]
            arr = self.hist[idx]
            m = float(max(arr[2:254].max(), 1))
            c = QColor(CH_COLORS[self.ch])
            c.setAlpha(170)
            p.setPen(Qt.NoPen)
            p.setBrush(c)
            bw = hist.width() / 256.0
            for i in range(256):
                hgt = min(1.0, arr[i] / m) * hist.height()
                if hgt > 0.3:
                    p.drawRect(QRectF(hist.left() + i * bw, hist.bottom() - hgt, bw + 0.6, hgt))
        ib, gm, iw, ob, ow = self.levels[self.ch]
        p.setPen(QPen(QColor(255, 255, 255, 60), 1, Qt.DashLine))
        for v in (ib, iw):
            x = self._x(v)
            p.drawLine(QPointF(x, hist.top()), QPointF(x, hist.bottom()))
        p.setRenderHint(QPainter.Antialiasing)
        self._tri(p, self._x(ib), in_y, QColor(15, 15, 15))
        self._tri(p, self._x(self._gray_val()), in_y, QColor(128, 128, 128))
        self._tri(p, self._x(iw), in_y, QColor(250, 250, 250))
        grad = QLinearGradient(out_bar.topLeft(), out_bar.topRight())
        end = QColor(255, 255, 255) if self.ch == 'rgb' else CH_COLORS[self.ch]
        grad.setColorAt(0, QColor(0, 0, 0))
        grad.setColorAt(1, end)
        p.setPen(QPen(QColor(70, 70, 75), 1))
        p.setBrush(QBrush(grad))
        p.drawRect(out_bar)
        self._tri(p, self._x(ob), out_y, QColor(15, 15, 15))
        self._tri(p, self._x(ow), out_y, QColor(250, 250, 250))
        p.end()

    def mousePressEvent(self, ev):
        if ev.button() != Qt.LeftButton:
            return
        hist, in_y, out_bar, out_y = self._geo()
        pos = ev.position()
        ib, gm, iw, ob, ow = self.levels[self.ch]
        if pos.y() >= out_bar.top() - 2:
            cands = {'ob': ob, 'ow': ow}
        else:
            cands = {'ib': ib, 'gm': self._gray_val(), 'iw': iw}
        best, bd = None, 12.0
        for k, v in cands.items():
            d = abs(self._x(v) - pos.x())
            if d < bd:
                best, bd = k, d
        self.drag = best

    def mouseMoveEvent(self, ev):
        if not self.drag or not (ev.buttons() & Qt.LeftButton):
            return
        hist = self._geo()[0]
        v = (ev.position().x() - hist.left()) / hist.width() * 255.0
        v = max(0.0, min(255.0, v))
        lv = self.levels[self.ch]
        ib, gm, iw, ob, ow = lv
        if self.drag == 'ib':
            lv[0] = int(round(min(v, iw - 2)))
        elif self.drag == 'iw':
            lv[2] = int(round(max(v, ib + 2)))
        elif self.drag == 'gm':
            t = (v - ib) / max(1e-6, (iw - ib))
            t = max(0.01, min(0.99, t))
            lv[1] = round(max(0.1, min(9.99, math.log(t) / math.log(0.5))), 2)
        elif self.drag == 'ob':
            lv[3] = int(round(min(v, ow - 1)))
        elif self.drag == 'ow':
            lv[4] = int(round(max(v, ob + 1)))
        self.levelsChanged.emit()
        self.update()

    def mouseReleaseEvent(self, ev):
        self.drag = None
