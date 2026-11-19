"""High quality zoom / pan image canvas (shared by viewer and editor)."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal, QPointF, QRectF
from PySide6.QtGui import QImage, QPixmap, QPainter, QColor, QPen, QPainterPath, QFont
from PySide6.QtWidgets import QWidget

ZOOM_STEPS = [0.02, 0.05, 0.08, 0.1, 0.125, 0.167, 0.25, 0.333, 0.5, 0.667, 0.75, 1.0,
              1.25, 1.5, 2.0, 3.0, 4.0, 6.0, 8.0, 12.0, 16.0, 24.0, 32.0]


class ImageCanvas(QWidget):
    doubleClicked = Signal()
    zoomChanged = Signal(float)
    wheelStep = Signal(int)
    clicked = Signal(QPointF)   # image pixel coordinates

    def __init__(self, parent=None, wheel_navigates=False):
        super().__init__(parent)
        self.wheel_navigates = wheel_navigates
        self._img = QImage()
        self._lsize = None        # logical image size (when a low-res stand-in is displayed)
        self._hint = None
        self._zoom = 1.0          # image pixels -> device pixels
        self._fit = True
        self._off = QPointF(0, 0)
        self._cache = None
        self._cache_key = None
        self._press = None
        self._last = None
        self._dragged = False
        self._wheel_acc = 0
        self.shrink_only = True
        self.bg = QColor(30, 30, 32)
        self.overlay_text = ''
        self.message = ''
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMouseTracking(True)
        self.setAttribute(Qt.WA_OpaquePaintEvent)
        self.setMinimumSize(80, 80)

    # ------------------------------------------------------------------ public API
    def image(self) -> QImage:
        return self._img

    def has_image(self) -> bool:
        return not self._img.isNull()

    def _iw(self) -> int:
        return self._lsize[0] if self._lsize else self._img.width()

    def _ih(self) -> int:
        return self._lsize[1] if self._lsize else self._img.height()

    def logical_size(self):
        return self._iw(), self._ih()

    def set_image(self, img: QImage, keep_view=False, hint: QImage | None = None, logical=None):
        """Show an image. ``logical`` (w, h) lets a low-resolution frame stand in for a larger image."""
        had = not self._img.isNull()
        ow, oh = (self._iw(), self._ih()) if had else (0, 0)
        self._img = img if img is not None else QImage()
        self._lsize = tuple(logical) if logical and not self._img.isNull() else None
        self._hint = hint if (hint is not None and not hint.isNull()) else None
        self._cache = None
        self.message = ''
        nw, nh = self._iw(), self._ih()
        same = had and not self._img.isNull() and abs(nw - ow) <= 2 and abs(nh - oh) <= 2
        if keep_view and same:
            if not self._fit and nw != ow and nw > 0:
                self._zoom *= ow / float(nw)
        else:
            self._fit = True
            self._off = QPointF(0, 0)
        self._recalc()
        self._update_cursor()
        self.update()
        self.zoomChanged.emit(self._zoom)

    def clear(self, message=''):
        self._img = QImage()
        self._lsize = None
        self._hint = None
        self._cache = None
        self.message = message
        self.update()

    def zoom(self) -> float:
        return self._zoom

    def is_fit(self) -> bool:
        return self._fit

    def fit(self):
        self._fit = True
        self._off = QPointF(0, 0)
        self._cache = None
        self._recalc()
        self._update_cursor()
        self.update()
        self.zoomChanged.emit(self._zoom)

    def actual_size(self):
        self.set_zoom(1.0)

    def zoom_in(self):
        self.set_zoom(next((s for s in ZOOM_STEPS if s > self._zoom * 1.001), ZOOM_STEPS[-1]))

    def zoom_out(self):
        self.set_zoom(next((s for s in reversed(ZOOM_STEPS) if s < self._zoom / 1.001), ZOOM_STEPS[0]))

    def set_zoom(self, z: float, anchor: QPointF | None = None):
        if self._img.isNull():
            return
        z = max(0.01, min(32.0, z))
        if anchor is None:
            anchor = QPointF(self.width() / 2.0, self.height() / 2.0)
        ip = self.widget_to_image(anchor)
        self._fit = False
        self._zoom = z
        self._cache = None
        s = self._scale()
        iw, ih = self._iw(), self._ih()
        cx, cy = self.width() / 2.0, self.height() / 2.0
        self._off = QPointF(anchor.x() - cx - (ip.x() - iw / 2.0) * s,
                            anchor.y() - cy - (ip.y() - ih / 2.0) * s)
        self._clamp()
        self._update_cursor()
        self.update()
        self.zoomChanged.emit(z)

    def pannable(self) -> bool:
        if self._img.isNull():
            return False
        r = self.image_rect()
        return r.width() > self.width() + 0.5 or r.height() > self.height() + 0.5

    def pan(self, dx: float, dy: float):
        self._off += QPointF(dx, dy)
        self._clamp()
        self.update()

    # ------------------------------------------------------------------ geometry
    def _dpr(self) -> float:
        return self.devicePixelRatioF() or 1.0

    def _scale(self) -> float:
        return self._zoom / self._dpr()

    def fit_zoom(self) -> float:
        if self._img.isNull():
            return 1.0
        d = self._dpr()
        W, H = max(1, self.width()) * d, max(1, self.height()) * d
        z = min(W / self._iw(), H / self._ih())
        return min(z, 1.0) if self.shrink_only else z

    def _recalc(self):
        if self._fit:
            self._zoom = self.fit_zoom()
            self._off = QPointF(0, 0)
        self._clamp()

    def image_rect(self) -> QRectF:
        s = self._scale()
        w, h = self._iw() * s, self._ih() * s
        return QRectF(self.width() / 2.0 + self._off.x() - w / 2.0,
                      self.height() / 2.0 + self._off.y() - h / 2.0, w, h)

    def _clamp(self):
        if self._img.isNull():
            return
        s = self._scale()
        w, h = self._iw() * s, self._ih() * s
        ox, oy = self._off.x(), self._off.y()
        lx = max(0.0, (w - self.width()) / 2.0)
        ly = max(0.0, (h - self.height()) / 2.0)
        self._off = QPointF(max(-lx, min(lx, ox)), max(-ly, min(ly, oy)))

    def widget_to_image(self, pt: QPointF) -> QPointF:
        r = self.image_rect()
        s = self._scale()
        return QPointF((pt.x() - r.x()) / s, (pt.y() - r.y()) / s)

    def image_to_widget(self, pt: QPointF) -> QPointF:
        r = self.image_rect()
        s = self._scale()
        return QPointF(r.x() + pt.x() * s, r.y() + pt.y() * s)

    # ------------------------------------------------------------------ painting
    def _scaled_pixmap(self) -> QPixmap:
        d = self._dpr()
        w = max(1, round(self._iw() * self._zoom))
        h = max(1, round(self._ih() * self._zoom))
        key = (w, h, d)
        if self._cache is not None and self._cache_key == key:
            return self._cache
        if w == self._img.width() and h == self._img.height():
            img = self._img
        elif self._hint is not None and abs(self._hint.width() - w) <= 1 and abs(self._hint.height() - h) <= 1:
            img = self._hint
        else:
            img = self._img.scaled(w, h, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
        pm = QPixmap.fromImage(img)
        pm.setDevicePixelRatio(d)
        self._cache, self._cache_key = pm, key
        return pm

    def paintEvent(self, ev):
        p = QPainter(self)
        p.fillRect(self.rect(), self.bg)
        if self._img.isNull():
            if self.message:
                p.setPen(QColor(150, 150, 156))
                p.drawText(self.rect(), Qt.AlignCenter, self.message)
            p.end()
            return
        r = self.image_rect()
        if self._zoom <= 1.0 + 1e-6:
            pm = self._scaled_pixmap()
            d = self._dpr()
            p.drawPixmap(QPointF(round(r.x() * d) / d, round(r.y() * d) / d), pm)
        else:
            vis = r.intersected(QRectF(self.rect()))
            if not vis.isEmpty():
                s = self._scale()
                kx = self._img.width() / float(self._iw())
                ky = self._img.height() / float(self._ih())
                src = QRectF((vis.x() - r.x()) / s * kx, (vis.y() - r.y()) / s * ky,
                             vis.width() / s * kx, vis.height() / s * ky)
                p.setRenderHint(QPainter.SmoothPixmapTransform, self._zoom < 3.0 or kx < 0.99)
                p.drawImage(vis, self._img, src)
        self.paint_overlay(p)
        if self.overlay_text:
            self._draw_overlay_text(p)
        p.end()

    def paint_overlay(self, p: QPainter):
        pass

    def _draw_overlay_text(self, p: QPainter):
        p.save()
        f = QFont(self.font())
        f.setPointSizeF(max(8.0, self.font().pointSizeF() * 1.05))
        p.setFont(f)
        fm = p.fontMetrics()
        lines = self.overlay_text.split('\n')
        w = max(fm.horizontalAdvance(t) for t in lines) + 20
        h = fm.height() * len(lines) + 14
        box = QRectF(14, 14, w, h)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0, 0, 0, 165))
        p.drawRoundedRect(box, 6, 6)
        p.setPen(QColor(240, 240, 240))
        y = box.y() + 7 + fm.ascent()
        for t in lines:
            p.drawText(QPointF(box.x() + 10, y), t)
            y += fm.height()
        p.restore()

    # ------------------------------------------------------------------ events
    def resizeEvent(self, ev):
        self._cache = None
        self._recalc()
        self._update_cursor()
        super().resizeEvent(ev)
        self.zoomChanged.emit(self._zoom)

    def _update_cursor(self):
        self.setCursor(Qt.OpenHandCursor if self.pannable() else Qt.ArrowCursor)

    def mousePressEvent(self, ev):
        if ev.button() == Qt.LeftButton:
            self._press = ev.position()
            self._last = ev.position()
            self._dragged = False
            if self.pannable():
                self.setCursor(Qt.ClosedHandCursor)
        super().mousePressEvent(ev)

    def mouseMoveEvent(self, ev):
        if self._last is not None and (ev.buttons() & Qt.LeftButton):
            d = ev.position() - self._last
            if (ev.position() - self._press).manhattanLength() > 3:
                self._dragged = True
            if self.pannable():
                self.pan(d.x(), d.y())
            self._last = ev.position()
        super().mouseMoveEvent(ev)

    def mouseReleaseEvent(self, ev):
        if ev.button() == Qt.LeftButton and self._last is not None:
            if not self._dragged and self.has_image():
                self.clicked.emit(self.widget_to_image(ev.position()))
            self._last = None
            self._press = None
            self._update_cursor()
        super().mouseReleaseEvent(ev)

    def mouseDoubleClickEvent(self, ev):
        if ev.button() == Qt.LeftButton:
            self.doubleClicked.emit()
        else:
            super().mouseDoubleClickEvent(ev)

    def wheelEvent(self, ev):
        dy = ev.angleDelta().y()
        if dy == 0:
            return
        if self.wheel_navigates and not (ev.modifiers() & Qt.ControlModifier):
            self._wheel_acc += dy
            while abs(self._wheel_acc) >= 120:
                step = -1 if self._wheel_acc > 0 else 1
                self._wheel_acc += 120 * step
                self.wheelStep.emit(step)
            return
        self.set_zoom(self._zoom * (1.25 ** (dy / 120.0)), ev.position())


class EditCanvas(ImageCanvas):
    """Canvas with crop overlay and click-to-pick support."""
    cropChanged = Signal()

    HANDLE = 7

    def __init__(self, parent=None):
        super().__init__(parent, wheel_navigates=False)
        self.crop_mode = False
        self.crop = [0.0, 0.0, 1.0, 1.0]
        self.aspect = None
        self.pick_mode = False
        self.px_scale = 1.0          # full-resolution pixels per displayed pixel
        self._handle = None
        self._start_rect = None
        self._start_pt = None

    # -------------------------------------------------------------- crop API
    def set_crop_mode(self, on: bool, rect=None):
        self.crop_mode = on
        if rect:
            self.crop = list(rect)
        elif on:
            self.crop = [0.0, 0.0, 1.0, 1.0]
        self._handle = None
        self._update_cursor()
        self.update()

    def set_aspect(self, aspect):
        self.aspect = aspect
        if aspect and self.has_image():
            iw, ih = self._iw(), self._ih()
            x0, y0, x1, y1 = self._crop_px()
            cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
            w = min(iw, ih * aspect)
            h = w / aspect
            w *= 0.96
            h *= 0.96
            cx = min(max(cx, w / 2), iw - w / 2)
            cy = min(max(cy, h / 2), ih - h / 2)
            self._set_crop_px(cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)
            self.cropChanged.emit()
        self.update()

    def _crop_px(self):
        iw, ih = self._iw(), self._ih()
        x0, y0, x1, y1 = self.crop
        return x0 * iw, y0 * ih, x1 * iw, y1 * ih

    def _set_crop_px(self, x0, y0, x1, y1):
        iw, ih = max(1, self._iw()), max(1, self._ih())
        x0, x1 = sorted((max(0.0, min(iw, x0)), max(0.0, min(iw, x1))))
        y0, y1 = sorted((max(0.0, min(ih, y0)), max(0.0, min(ih, y1))))
        self.crop = [x0 / iw, y0 / ih, x1 / iw, y1 / ih]

    def _crop_widget_rect(self) -> QRectF:
        x0, y0, x1, y1 = self._crop_px()
        a = self.image_to_widget(QPointF(x0, y0))
        b = self.image_to_widget(QPointF(x1, y1))
        return QRectF(a, b).normalized()

    def _handles(self):
        r = self._crop_widget_rect()
        cx, cy = r.center().x(), r.center().y()
        return {'tl': QPointF(r.left(), r.top()), 't': QPointF(cx, r.top()), 'tr': QPointF(r.right(), r.top()),
                'r': QPointF(r.right(), cy), 'br': QPointF(r.right(), r.bottom()), 'b': QPointF(cx, r.bottom()),
                'bl': QPointF(r.left(), r.bottom()), 'l': QPointF(r.left(), cy)}

    def _hit(self, pos: QPointF):
        for name, pt in self._handles().items():
            if abs(pos.x() - pt.x()) <= self.HANDLE + 2 and abs(pos.y() - pt.y()) <= self.HANDLE + 2:
                return name
        if self._crop_widget_rect().contains(pos):
            return 'move'
        return None

    # -------------------------------------------------------------- painting
    def paint_overlay(self, p: QPainter):
        if not self.crop_mode or self._img.isNull():
            return
        p.save()
        p.setRenderHint(QPainter.Antialiasing, False)
        ir = self.image_rect()
        cr = self._crop_widget_rect()
        path = QPainterPath()
        path.setFillRule(Qt.OddEvenFill)
        path.addRect(ir)
        path.addRect(cr)
        p.fillPath(path, QColor(0, 0, 0, 155))
        p.setPen(QPen(QColor(255, 255, 255, 80), 1))
        for i in (1, 2):
            x = cr.left() + cr.width() * i / 3.0
            y = cr.top() + cr.height() * i / 3.0
            p.drawLine(QPointF(x, cr.top()), QPointF(x, cr.bottom()))
            p.drawLine(QPointF(cr.left(), y), QPointF(cr.right(), y))
        p.setPen(QPen(QColor(255, 255, 255), 1))
        p.setBrush(Qt.NoBrush)
        p.drawRect(cr)
        p.setBrush(QColor(255, 255, 255))
        p.setPen(QPen(QColor(20, 20, 20), 1))
        hs = self.HANDLE
        for pt in self._handles().values():
            p.drawRect(QRectF(pt.x() - hs / 2.0, pt.y() - hs / 2.0, hs, hs))
        x0, y0, x1, y1 = self._crop_px()
        txt = f"{round((x1 - x0) * self.px_scale)} × {round((y1 - y0) * self.px_scale)}"
        p.setRenderHint(QPainter.Antialiasing)
        fm = p.fontMetrics()
        tw = fm.horizontalAdvance(txt) + 14
        tb = QRectF(cr.left(), max(ir.top(), cr.top() - 24), tw, 20)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0, 0, 0, 180))
        p.drawRoundedRect(tb, 4, 4)
        p.setPen(QColor(255, 255, 255))
        p.drawText(tb, Qt.AlignCenter, txt)
        p.restore()

    # -------------------------------------------------------------- interaction
    def _update_cursor(self):
        if getattr(self, 'pick_mode', False):
            self.setCursor(Qt.CrossCursor)
        elif getattr(self, 'crop_mode', False):
            self.setCursor(Qt.CrossCursor)
        else:
            super()._update_cursor()

    _CURSORS = {'tl': Qt.SizeFDiagCursor, 'br': Qt.SizeFDiagCursor, 'tr': Qt.SizeBDiagCursor,
                'bl': Qt.SizeBDiagCursor, 't': Qt.SizeVerCursor, 'b': Qt.SizeVerCursor,
                'l': Qt.SizeHorCursor, 'r': Qt.SizeHorCursor, 'move': Qt.SizeAllCursor}

    def _clamped_img_pt(self, pos):
        ip = self.widget_to_image(pos)
        return QPointF(max(0.0, min(self._iw(), ip.x())), max(0.0, min(self._ih(), ip.y())))

    def mousePressEvent(self, ev):
        if self.crop_mode and ev.button() == Qt.LeftButton and self.has_image():
            self._handle = self._hit(ev.position()) or 'new'
            self._start_rect = self._crop_px()
            self._start_pt = self._clamped_img_pt(ev.position())
            return
        super().mousePressEvent(ev)

    def mouseMoveEvent(self, ev):
        if self.crop_mode and self.has_image():
            if self._handle and (ev.buttons() & Qt.LeftButton):
                self._drag_crop(self._clamped_img_pt(ev.position()))
                self.update()
            else:
                h = self._hit(ev.position())
                self.setCursor(self._CURSORS.get(h, Qt.CrossCursor))
            return
        super().mouseMoveEvent(ev)

    def mouseReleaseEvent(self, ev):
        if self.crop_mode and self._handle and ev.button() == Qt.LeftButton:
            x0, y0, x1, y1 = self._crop_px()
            if (x1 - x0) < 4 or (y1 - y0) < 4:
                self._set_crop_px(*self._start_rect)
            self._handle = None
            self.cropChanged.emit()
            self.update()
            return
        super().mouseReleaseEvent(ev)

    def mouseDoubleClickEvent(self, ev):
        if self.crop_mode:
            return
        super().mouseDoubleClickEvent(ev)

    def _drag_crop(self, pt: QPointF):
        iw, ih = float(self._iw()), float(self._ih())
        x0, y0, x1, y1 = self._start_rect
        h = self._handle
        a = self.aspect
        if h == 'move':
            dx = pt.x() - self._start_pt.x()
            dy = pt.y() - self._start_pt.y()
            w, hh = x1 - x0, y1 - y0
            nx0 = max(0.0, min(iw - w, x0 + dx))
            ny0 = max(0.0, min(ih - hh, y0 + dy))
            self._set_crop_px(nx0, ny0, nx0 + w, ny0 + hh)
            return
        if h == 'new':
            fx, fy = self._start_pt.x(), self._start_pt.y()
            h = ('t' if pt.y() < fy else 'b') + ('l' if pt.x() < fx else 'r')
            x0, y0, x1, y1 = fx, fy, fx, fy
        if h in ('tl', 'tr', 'bl', 'br', 'lt', 'rt', 'lb', 'rb'):
            left = 'l' in h
            top = 't' in h
            fx = x1 if left else x0
            fy = y1 if top else y0
            w = abs(pt.x() - fx)
            hh = abs(pt.y() - fy)
            aw = fx if left else iw - fx
            ah = fy if top else ih - fy
            if a:
                if hh == 0 or w / max(hh, 1e-6) > a:
                    hh = w / a
                else:
                    w = hh * a
                if w > aw:
                    w = aw
                    hh = w / a
                if hh > ah:
                    hh = ah
                    w = hh * a
            else:
                w, hh = min(w, aw), min(hh, ah)
            nx0, nx1 = (fx - w, fx) if left else (fx, fx + w)
            ny0, ny1 = (fy - hh, fy) if top else (fy, fy + hh)
            self._set_crop_px(nx0, ny0, nx1, ny1)
            return
        nx0, ny0, nx1, ny1 = x0, y0, x1, y1
        if h == 'l':
            nx0 = min(pt.x(), x1 - 4)
        elif h == 'r':
            nx1 = max(pt.x(), x0 + 4)
        elif h == 't':
            ny0 = min(pt.y(), y1 - 4)
        elif h == 'b':
            ny1 = max(pt.y(), y0 + 4)
        if a:
            if h in ('l', 'r'):
                w = nx1 - nx0
                cy = (y0 + y1) / 2.0
                maxh = 2 * min(cy, ih - cy)
                w = min(w, maxh * a)
                if h == 'l':
                    nx0 = nx1 - w
                else:
                    nx1 = nx0 + w
                hh = w / a
                ny0, ny1 = cy - hh / 2, cy + hh / 2
            else:
                hh = ny1 - ny0
                cx = (x0 + x1) / 2.0
                maxw = 2 * min(cx, iw - cx)
                hh = min(hh, maxw / a)
                if h == 't':
                    ny0 = ny1 - hh
                else:
                    ny1 = ny0 + hh
                w = hh * a
                nx0, nx1 = cx - w / 2, cx + w / 2
        self._set_crop_px(nx0, ny0, nx1, ny1)

    def keyPressEvent(self, ev):
        super().keyPressEvent(ev)
