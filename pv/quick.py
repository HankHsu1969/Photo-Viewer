"""Quick Viewer: a lightweight, fast image viewer.

Only QtCore / QtGui are used (no QtWidgets, numpy or Pillow at startup), images are decoded at
screen size, and neighbours are prefetched so ←/→ is instant. Double-click / Enter hands the
current image over to the full manager (PhotoViewer.exe --manage), E opens it in the editor.
"""
from __future__ import annotations

import os
from collections import OrderedDict

from PySide6.QtCore import Qt, QObject, Signal, QRunnable, QThreadPool, QTimer, QPointF, QRectF, QRect, QEvent
from PySide6.QtGui import (QGuiApplication, QRasterWindow, QPainter, QImage, QPixmap, QColor, QFont,
                           QMovie, QFontMetrics)

from . import startup
from .common import (read_qimage, oriented_size, list_images, norm, human_size, fmt_time, app_icon,
                     Settings, RatingDB, rotate_file, move_to_trash)

TITLE = 'Quick Viewer'
ZOOM_STEPS = [0.02, 0.05, 0.08, 0.1, 0.125, 0.167, 0.25, 0.333, 0.5, 0.667, 0.75, 1.0,
              1.25, 1.5, 2.0, 3.0, 4.0, 6.0, 8.0, 12.0, 16.0, 24.0, 32.0]
BG = QColor(24, 24, 26)
BG_FULL = QColor(0, 0, 0)


# --------------------------------------------------------------------------- background loader
class _Sig(QObject):
    done = Signal(str, str, QImage)


class _Task(QRunnable):
    def __init__(self, kind, path, bw, bh, sig):
        super().__init__()
        self.kind, self.path, self.bw, self.bh, self.sig = kind, path, bw, bh, sig
        self.setAutoDelete(True)

    def run(self):
        try:
            img = read_qimage(self.path, self.bw, self.bh) if self.kind == 'fit' else read_qimage(self.path)
        except Exception:  # noqa: BLE001
            img = QImage()
        self.sig.done.emit(self.kind, self.path, img)


class Loader(QObject):
    """Caches screen-sized ('fit') decodes of neighbours and a couple of full-resolution decodes."""
    ready = Signal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(2)
        self.cache = {'fit': OrderedDict(), 'full': OrderedDict()}
        self.limits = {'fit': 7, 'full': 2}
        self.inflight = set()
        self._sig = _Sig()
        self._sig.done.connect(self._done)

    def get(self, kind, path):
        c = self.cache[kind]
        v = c.get(path)
        if v is not None:
            c.move_to_end(path)
        return v

    def put(self, kind, path, img):
        c = self.cache[kind]
        c[path] = img
        c.move_to_end(path)
        while len(c) > self.limits[kind]:
            c.popitem(last=False)

    def request(self, kind, path, bw=0, bh=0, priority=0):
        if path in self.cache[kind] or (kind, path) in self.inflight:
            return
        self.inflight.add((kind, path))
        self.pool.start(_Task(kind, path, bw, bh, self._sig), priority)

    def invalidate(self, path):
        for c in self.cache.values():
            c.pop(path, None)

    def _done(self, kind, path, img):
        self.inflight.discard((kind, path))
        self.put(kind, path, img)
        self.ready.emit(kind, path)


# --------------------------------------------------------------------------- window
class QuickWindow(QRasterWindow):
    def __init__(self, path):
        super().__init__()
        self.settings = Settings()
        self._ratings = None
        self.setTitle(TITLE)
        self.setIcon(app_icon())
        self.files = [os.path.abspath(path)]
        self.index = 0
        self._direction = 1
        self.loader = Loader(self)
        self.loader.ready.connect(self._on_ready)
        self.img = QImage()
        self.lsize = (0, 0)          # original (EXIF-oriented) pixel size of the current image
        self.shown = None            # path currently on screen
        self.error = ''
        self.zoom = 1.0              # device pixels per original image pixel
        self.fit = True
        self.off = QPointF(0, 0)
        self._pm = None
        self._pm_key = None
        self._press = None
        self._last = None
        self._dragged = False
        self._wheel = 0
        self._movie = None
        self._info = False
        self._flash = ''
        self._flash_timer = QTimer(self)
        self._flash_timer.setSingleShot(True)
        self._flash_timer.timeout.connect(self._clear_flash)
        self._fullscreen = False
        self._was_max = False
        self.font_ = QFont()
        self.font_.setFamilies(['Segoe UI', 'Microsoft JhengHei UI', 'Microsoft JhengHei'])
        self.font_.setPointSizeF(10)

    # ------------------------------------------------------------------ startup
    def _bound(self):
        scr = self.screen() or QGuiApplication.primaryScreen()
        if scr is None:
            return 2560, 1600
        g = scr.size()
        d = scr.devicePixelRatio()
        return max(800, int(g.width() * d)), max(600, int(g.height() * d))

    def start(self):
        """Decode the first image synchronously at screen size, show the window, then scan the folder."""
        path = self.files[0]
        self.loader.put('fit', path, read_qimage(path, *self._bound()))
        maximized = self._restore_geometry()
        self.show_index(0)
        if maximized:
            self.showMaximized()
        else:
            self.show()
        QTimer.singleShot(0, self._scan_folder)

    def _restore_geometry(self):
        g = self.settings.get('quick/geometry', None, list)
        maximized = self.settings.get('quick/maximized', True, bool)
        scr = QGuiApplication.primaryScreen()
        avail = scr.availableGeometry() if scr else QRect(0, 0, 1600, 1000)
        rect = None
        if g and len(g) == 4:
            try:
                rect = QRect(*[int(v) for v in g])
            except (TypeError, ValueError):
                rect = None
        if rect is None or not any(s.availableGeometry().intersects(rect) for s in QGuiApplication.screens()):
            w, h = int(avail.width() * 0.8), int(avail.height() * 0.85)
            rect = QRect(avail.x() + (avail.width() - w) // 2, avail.y() + (avail.height() - h) // 2, w, h)
        self.setGeometry(rect)
        return maximized

    def _save_geometry(self):
        if self._fullscreen:
            maximized = self._was_max
        else:
            maximized = bool(self.windowStates() & Qt.WindowMaximized)
            if not maximized:
                g = self.geometry()
                self.settings.set('quick/geometry', [g.x(), g.y(), g.width(), g.height()])
        self.settings.set('quick/maximized', maximized)
        self.settings.sync()

    def _scan_folder(self):
        path = self.files[self.index]
        files = list_images(os.path.dirname(path))
        n = norm(path)
        idx = next((i for i, f in enumerate(files) if norm(f) == n), -1)
        if idx < 0:
            files.insert(0, path)
            idx = 0
        self.files, self.index = files, idx
        self._update_title()
        self._prefetch()

    # ------------------------------------------------------------------ navigation
    def current(self):
        return self.files[self.index] if 0 <= self.index < len(self.files) else None

    def show_index(self, i, direction=1):
        if not self.files:
            return
        i = max(0, min(len(self.files) - 1, i))
        self.index, self._direction = i, direction
        path = self.files[i]
        self._stop_movie()
        img = self.loader.get('full', path)
        if img is None:
            img = self.loader.get('fit', path)
        if img is not None:
            self._display(path, img)
        else:
            self.loader.request('fit', path, *self._bound(), priority=10)
        self._prefetch()
        self._update_title()

    def _prefetch(self):
        bw, bh = self._bound()
        for k in ((1, 2, -1) if self._direction > 0 else (-1, -2, 1)):
            j = self.index + k
            if 0 <= j < len(self.files):
                self.loader.request('fit', self.files[j], bw, bh, priority=0)

    def _on_ready(self, kind, path):
        if path != self.current():
            return
        img = self.loader.get(kind, path)
        if img is None:
            return
        if kind == 'full' or self.shown != path:
            self._display(path, img)

    def _display(self, path, img):
        same = path == self.shown and not self.img.isNull()
        self.shown = path
        self._pm = None
        if img.isNull():
            self.img = QImage()
            self.lsize = (0, 0)
            self.error = f'無法開啟影像\n{os.path.basename(path)}'
            self.update()
            return
        self.error = ''
        if not same:
            s = oriented_size(path)
            self.lsize = (s.width(), s.height()) if s.isValid() else (img.width(), img.height())
        if img.width() > self.lsize[0] or img.height() > self.lsize[1]:
            self.lsize = (img.width(), img.height())
        self.img = img
        if not same:
            self.fit = True
            self.off = QPointF(0, 0)
            if path.lower().endswith('.gif'):
                self._start_movie(path)
            if self._fullscreen and not self._info:
                self.flash(f'{os.path.basename(path)}    {self.index + 1} / {len(self.files)}')
        self._recalc()
        self._update_cursor()
        self.update()

    def next(self):
        if self.index >= len(self.files) - 1:
            self.flash('已是最後一張')
            return
        self.show_index(self.index + 1, 1)

    def prev(self):
        if self.index <= 0:
            self.flash('已是第一張')
            return
        self.show_index(self.index - 1, -1)

    def _update_title(self):
        path = self.current()
        if path:
            self.setTitle(f'{os.path.basename(path)}  ({self.index + 1}/{len(self.files)}) - {TITLE}')
        if self._info:
            self.update()

    # ------------------------------------------------------------------ animated GIF
    def _start_movie(self, path):
        m = QMovie(path)
        if not m.isValid() or m.frameCount() == 1:
            return
        m.frameChanged.connect(lambda _f, m=m: self._movie_frame(m))
        self._movie = m
        m.start()

    def _movie_frame(self, m):
        if m is not self._movie:
            return
        self.img = m.currentImage()
        self.lsize = (self.img.width(), self.img.height())
        self._pm = None
        self.update()

    def _stop_movie(self):
        if self._movie is not None:
            self._movie.stop()
            self._movie.deleteLater()
            self._movie = None

    # ------------------------------------------------------------------ geometry
    def _dpr(self):
        return self.devicePixelRatio() or 1.0

    def _scale(self):
        return self.zoom / self._dpr()

    def _fit_zoom(self):
        lw, lh = self.lsize
        if not lw or not lh:
            return 1.0
        d = self._dpr()
        return min(max(1, self.width()) * d / lw, max(1, self.height()) * d / lh, 1.0)

    def _recalc(self):
        if self.fit:
            self.zoom = self._fit_zoom()
            self.off = QPointF(0, 0)
        self._clamp()

    def image_rect(self):
        s = self._scale()
        w, h = self.lsize[0] * s, self.lsize[1] * s
        return QRectF(self.width() / 2.0 + self.off.x() - w / 2.0, self.height() / 2.0 + self.off.y() - h / 2.0, w, h)

    def _clamp(self):
        s = self._scale()
        w, h = self.lsize[0] * s, self.lsize[1] * s
        lx = max(0.0, (w - self.width()) / 2.0)
        ly = max(0.0, (h - self.height()) / 2.0)
        self.off = QPointF(max(-lx, min(lx, self.off.x())), max(-ly, min(ly, self.off.y())))

    def pannable(self):
        if self.img.isNull():
            return False
        r = self.image_rect()
        return r.width() > self.width() + 0.5 or r.height() > self.height() + 0.5

    def set_zoom(self, z, anchor=None):
        if self.img.isNull():
            return
        z = max(0.01, min(32.0, z))
        if anchor is None:
            anchor = QPointF(self.width() / 2.0, self.height() / 2.0)
        r = self.image_rect()
        s0 = self._scale()
        ix, iy = (anchor.x() - r.x()) / s0, (anchor.y() - r.y()) / s0
        self.fit = False
        self.zoom = z
        s = self._scale()
        lw, lh = self.lsize
        self.off = QPointF(anchor.x() - self.width() / 2.0 - (ix - lw / 2.0) * s,
                           anchor.y() - self.height() / 2.0 - (iy - lh / 2.0) * s)
        self._clamp()
        self._pm = None
        self._need_full()
        self._update_cursor()
        self.update()
        self.flash(f'{self.zoom * 100:.0f}%', 700)

    def _need_full(self):
        path = self.shown
        if path and self.loader.get('full', path) is None and self.zoom * self.lsize[0] > self.img.width() * 1.01:
            self.loader.request('full', path, priority=5)

    def zoom_in(self):
        self.set_zoom(next((s for s in ZOOM_STEPS if s > self.zoom * 1.001), ZOOM_STEPS[-1]))

    def zoom_out(self):
        self.set_zoom(next((s for s in reversed(ZOOM_STEPS) if s < self.zoom / 1.001), ZOOM_STEPS[0]))

    def fit_view(self):
        self.fit = True
        self._pm = None
        self._recalc()
        self._update_cursor()
        self.update()

    # ------------------------------------------------------------------ painting
    def paintEvent(self, ev):
        p = QPainter(self)
        self.render(p)
        p.end()

    def render(self, p):
        W, H = self.width(), self.height()
        p.fillRect(QRect(0, 0, W, H), BG_FULL if self._fullscreen else BG)
        if self.img.isNull():
            if self.error:
                p.setFont(self.font_)
                p.setPen(QColor(160, 160, 166))
                p.drawText(QRect(0, 0, W, H), Qt.AlignCenter, self.error)
            self._draw_overlay(p)
            return
        r = self.image_rect()
        d = self._dpr()
        kx = self.img.width() / float(self.lsize[0])
        ky = self.img.height() / float(self.lsize[1])
        if r.left() >= -0.5 and r.top() >= -0.5 and r.right() <= W + 0.5 and r.bottom() <= H + 0.5:
            tw, th = max(1, round(r.width() * d)), max(1, round(r.height() * d))
            if self._pm is None or self._pm_key != (tw, th):
                src = self.img
                if (tw, th) != (src.width(), src.height()):
                    src = src.scaled(tw, th, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
                self._pm = QPixmap.fromImage(src)
                self._pm.setDevicePixelRatio(d)
                self._pm_key = (tw, th)
            p.drawPixmap(QPointF(round(r.x() * d) / d, round(r.y() * d) / d), self._pm)
        else:
            vis = r.intersected(QRectF(0, 0, W, H))
            s = self._scale()
            src = QRectF((vis.x() - r.x()) / s * kx, (vis.y() - r.y()) / s * ky, vis.width() / s * kx, vis.height() / s * ky)
            p.setRenderHint(QPainter.SmoothPixmapTransform, self.zoom < 3.0 or kx < 0.99)
            p.drawImage(vis, self.img, src)
        self._draw_overlay(p)

    def _overlay_lines(self):
        if self._info:
            path = self.current()
            if not path:
                return []
            lines = [os.path.basename(path), f'{self.lsize[0]} × {self.lsize[1]}    {self.index + 1} / {len(self.files)}    {self.zoom * 100:.0f}%']
            try:
                st = os.stat(path)
                lines.append(f'{human_size(st.st_size)}    {fmt_time(st.st_mtime)}')
            except OSError:
                pass
            r = self.ratings().get(path)
            if r:
                lines.append('★' * r)
            lines.append('雙擊／Enter：Photo Viewer 管理　E：編輯　I：關閉資訊')
            return lines
        return [self._flash] if self._flash else []

    def _draw_overlay(self, p):
        lines = self._overlay_lines()
        if not lines:
            return
        p.save()
        p.setFont(self.font_)
        fm = QFontMetrics(self.font_)
        w = max(fm.horizontalAdvance(t) for t in lines) + 22
        h = fm.height() * len(lines) + 14
        box = QRectF(16, self.height() - h - 16, w, h)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0, 0, 0, 170))
        p.drawRoundedRect(box, 6, 6)
        p.setPen(QColor(238, 238, 238))
        y = box.y() + 7 + fm.ascent()
        for t in lines:
            p.drawText(QPointF(box.x() + 11, y), t)
            y += fm.height()
        p.restore()

    def flash(self, text, ms=1200):
        self._flash = text
        self._flash_timer.start(ms)
        self.update()

    def _clear_flash(self):
        self._flash = ''
        self.update()

    # ------------------------------------------------------------------ actions
    def ratings(self):
        if self._ratings is None:
            self._ratings = RatingDB()
        return self._ratings

    def open_full(self, mode='manage'):
        path = self.current()
        try:
            startup.launch_full_app(f'--{mode}', path) if path else startup.launch_full_app()
        except OSError as e:
            startup.message_box(f'無法啟動 Photo Viewer：\n{e}', hwnd=int(self.winId()))
            return
        self.close()

    def toggle_fullscreen(self):
        if self._fullscreen:
            self._fullscreen = False
            if self._was_max:
                self.showMaximized()
            else:
                self.showNormal()
        else:
            self._was_max = bool(self.windowStates() & Qt.WindowMaximized)
            self._fullscreen = True
            self.showFullScreen()
        self.update()

    def delete_current(self):
        path = self.current()
        if not path:
            return
        if not startup.message_box(f'確定要將「{os.path.basename(path)}」移到資源回收筒嗎？', '刪除', yes_no=True,
                                   hwnd=int(self.winId())):
            return
        if not move_to_trash(path):
            startup.message_box('無法刪除此檔案。', '刪除', hwnd=int(self.winId()))
            return
        self.loader.invalidate(path)
        self.ratings().remove(path)
        i = self.index
        del self.files[i]
        self.shown = None
        if not self.files:
            self.close()
            return
        self.show_index(min(i, len(self.files) - 1), 1)

    def rotate(self, op):
        path = self.current()
        if not path:
            return
        ok, msg = rotate_file(path, op)
        if not ok:
            startup.message_box(msg, '旋轉', hwnd=int(self.winId()))
            return
        self.loader.invalidate(path)
        self.shown = None
        self.loader.put('fit', path, read_qimage(path, *self._bound()))
        self.show_index(self.index, self._direction)
        self.flash(msg)

    def copy_image(self):
        path = self.current()
        if path:
            img = self.loader.get('full', path)
            if img is None or img.isNull():
                img = read_qimage(path)
            if not img.isNull():
                QGuiApplication.clipboard().setImage(img)
                self.flash('已複製影像到剪貼簿')

    def set_rating(self, r):
        path = self.current()
        if path:
            self.ratings().set(path, r)
            self.flash('評等：' + ('★' * r if r else '無'))

    # ------------------------------------------------------------------ events
    def event(self, ev):
        if ev.type() == QEvent.Close:
            self._stop_movie()
            self._save_geometry()
        return super().event(ev)

    def resizeEvent(self, ev):
        self._pm = None
        self._recalc()
        self._update_cursor()
        super().resizeEvent(ev)

    def _update_cursor(self):
        self.setCursor(Qt.OpenHandCursor if self.pannable() else Qt.ArrowCursor)

    def keyPressEvent(self, ev):
        k = ev.key()
        ctrl = bool(ev.modifiers() & Qt.ControlModifier)
        if ctrl and Qt.Key_0 <= k <= Qt.Key_5:
            self.set_rating(k - Qt.Key_0)
        elif ctrl and k == Qt.Key_C:
            self.copy_image()
        elif k in (Qt.Key_Right, Qt.Key_PageDown, Qt.Key_Space):
            self.next()
        elif k in (Qt.Key_Left, Qt.Key_PageUp, Qt.Key_Backspace):
            self.prev()
        elif k in (Qt.Key_Up, Qt.Key_Down):
            if self.pannable():
                self.off += QPointF(0, 80 if k == Qt.Key_Up else -80)
                self._clamp()
                self.update()
            elif k == Qt.Key_Down:
                self.next()
            else:
                self.prev()
        elif k == Qt.Key_Home:
            self.show_index(0, 1)
        elif k == Qt.Key_End:
            self.show_index(len(self.files) - 1, -1)
        elif k in (Qt.Key_Plus, Qt.Key_Equal):
            self.zoom_in()
        elif k in (Qt.Key_Minus, Qt.Key_Underscore):
            self.zoom_out()
        elif k in (Qt.Key_0, Qt.Key_Asterisk):
            self.fit_view()
        elif k in (Qt.Key_1, Qt.Key_Slash):
            self.set_zoom(1.0)
        elif k in (Qt.Key_F, Qt.Key_F11):
            self.toggle_fullscreen()
        elif k in (Qt.Key_Return, Qt.Key_Enter):
            self.open_full('manage')
        elif k == Qt.Key_E:
            self.open_full('edit')
        elif k == Qt.Key_Escape:
            if self._fullscreen:
                self.toggle_fullscreen()
            else:
                self.close()
        elif k == Qt.Key_Delete:
            self.delete_current()
        elif k == Qt.Key_BracketLeft:
            self.rotate('ccw')
        elif k == Qt.Key_BracketRight:
            self.rotate('cw')
        elif k == Qt.Key_I:
            self._info = not self._info
            self.update()
        else:
            super().keyPressEvent(ev)

    def mousePressEvent(self, ev):
        if ev.button() == Qt.LeftButton:
            self._press = self._last = ev.position()
            self._dragged = False
            if self.pannable():
                self.setCursor(Qt.ClosedHandCursor)

    def mouseMoveEvent(self, ev):
        if self._last is not None and (ev.buttons() & Qt.LeftButton):
            d = ev.position() - self._last
            if (ev.position() - self._press).manhattanLength() > 3:
                self._dragged = True
            if self.pannable():
                self.off += d
                self._clamp()
                self.update()
            self._last = ev.position()

    def mouseReleaseEvent(self, ev):
        if ev.button() == Qt.LeftButton:
            self._press = self._last = None
            self._update_cursor()

    def mouseDoubleClickEvent(self, ev):
        if ev.button() == Qt.LeftButton:
            self.open_full('manage')

    def wheelEvent(self, ev):
        dy = ev.angleDelta().y()
        if not dy:
            return
        if ev.modifiers() & Qt.ControlModifier:
            self.set_zoom(self.zoom * (1.25 ** (dy / 120.0)), ev.position())
            return
        self._wheel += dy
        while abs(self._wheel) >= 120:
            step = -1 if self._wheel > 0 else 1
            self._wheel += 120 * step
            self.next() if step > 0 else self.prev()
