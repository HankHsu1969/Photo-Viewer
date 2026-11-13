"""View mode: fast full-window image viewer with prefetching and a filmstrip."""
from __future__ import annotations

import os
from collections import OrderedDict

from PySide6.QtCore import Qt, Signal, QObject, QRunnable, QThreadPool, QTimer, QSize, QItemSelectionModel
from PySide6.QtGui import QImage, QAction, QKeySequence, QMovie, QColor, QGuiApplication
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QToolBar, QLabel, QListView,
                               QMenu, QMessageBox, QFileDialog, QAbstractItemView, QSizePolicy)

from .canvas import ImageCanvas
from .common import (G, glyph_icon, read_qimage, list_images, norm, human_size, fmt_time, exif_info,
                     move_to_trash, rotate_file, reveal_in_explorer, IMAGE_EXTS)
from .thumbs import FolderModel, ThumbDelegate, entry_from_path


class _LoadSig(QObject):
    done = Signal(str, QImage, QImage)


class ImageTask(QRunnable):
    """Decode an image in a worker thread; optionally also produce a screen-fit scaled copy."""

    def __init__(self, path, sig, fit_w=0, fit_h=0, decode_max=0):
        super().__init__()
        self.path, self.sig = path, sig
        self.fit_w, self.fit_h, self.decode_max = fit_w, fit_h, decode_max
        self.setAutoDelete(True)

    def run(self):
        try:
            img = read_qimage(self.path, self.decode_max, self.decode_max) if self.decode_max else read_qimage(self.path)
            fit = QImage()
            if not img.isNull() and self.fit_w > 0 and (img.width() > self.fit_w or img.height() > self.fit_h):
                fit = img.scaled(self.fit_w, self.fit_h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        except Exception:  # noqa: BLE001
            img, fit = QImage(), QImage()
        self.sig.done.emit(self.path, img, fit)


class ImageLoader(QObject):
    """Prefetching full-resolution image cache."""
    loaded = Signal(str)

    def __init__(self, parent=None, max_bytes=700 * 1024 * 1024):
        super().__init__(parent)
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(2)
        self.cache: OrderedDict[str, tuple] = OrderedDict()
        self.inflight: set[str] = set()
        self.max_bytes = max_bytes
        self._sig = _LoadSig()
        self._sig.done.connect(self._done)

    def get(self, path):
        v = self.cache.get(path)
        if v is not None:
            self.cache.move_to_end(path)
        return v

    def request(self, path, fit_w, fit_h, priority=0):
        if path in self.cache or path in self.inflight:
            return
        self.inflight.add(path)
        self.pool.start(ImageTask(path, self._sig, fit_w, fit_h), priority)

    def invalidate(self, path):
        self.cache.pop(path, None)

    def clear(self):
        self.pool.clear()
        self.cache.clear()
        self.inflight.clear()

    def _done(self, path, img, fit):
        self.inflight.discard(path)
        self.cache[path] = (img, fit)
        total = sum(i.sizeInBytes() + f.sizeInBytes() for i, f in self.cache.values())
        while len(self.cache) > 3 and total > self.max_bytes:
            _, (i, f) = self.cache.popitem(last=False)
            total -= i.sizeInBytes() + f.sizeInBytes()
        self.loaded.emit(path)


class ViewPage(QWidget):
    requestManage = Signal(str)
    requestEdit = Signal(str)
    requestFullscreen = Signal(bool)
    fileChanged = Signal(str)
    fileDeleted = Signal(str)

    def __init__(self, thumbs, ratings, settings, parent=None):
        super().__init__(parent)
        self.thumbs, self.ratings, self.settings = thumbs, ratings, settings
        self.files: list[str] = []
        self.index = -1
        self._direction = 1
        self._displayed = None
        self._movie = None
        self._fullscreen = False
        self._info = False

        self.loader = ImageLoader(self)
        self.loader.loaded.connect(self._on_loaded)

        self.canvas = ImageCanvas(self, wheel_navigates=True)
        self.canvas.doubleClicked.connect(self.go_manage)
        self.canvas.wheelStep.connect(self.step)
        self.canvas.zoomChanged.connect(lambda _z: self._update_status())

        self.strip_model = FolderModel(thumbs, self)
        self.strip = QListView()
        self.strip.setModel(self.strip_model)
        self.strip_delegate = ThumbDelegate(thumbs, ratings, size=64, show_names=False)
        self.strip.setItemDelegate(self.strip_delegate)
        self.strip.setViewMode(QListView.IconMode)
        self.strip.setFlow(QListView.LeftToRight)
        self.strip.setWrapping(False)
        self.strip.setMovement(QListView.Static)
        self.strip.setUniformItemSizes(True)
        self.strip.setSelectionMode(QAbstractItemView.SingleSelection)
        self.strip.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.strip.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.strip.setFixedHeight(64 + 10 + 16)
        self.strip.setFocusPolicy(Qt.NoFocus)
        self.strip.setSpacing(2)
        self.strip.clicked.connect(lambda idx: self.show_index(idx.row()))

        self._build_actions()
        self.toolbar = self._build_toolbar()
        self.statusw = self._build_status()

        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        v.addWidget(self.toolbar)
        v.addWidget(self.canvas, 1)
        v.addWidget(self.strip)
        v.addWidget(self.statusw)

        self.slide_timer = QTimer(self)
        self.slide_timer.timeout.connect(self._slide_next)
        self.flash_timer = QTimer(self)
        self.flash_timer.setSingleShot(True)
        self.flash_timer.timeout.connect(self._clear_flash)
        self._flash_text = ''

        show_strip = settings.get('view/filmstrip', True, bool)
        self.act_strip.setChecked(show_strip)
        self.strip.setVisible(show_strip)

    # ------------------------------------------------------------------ UI building
    def _act(self, text, slot, shortcuts=None, glyph=None, mirror=False, checkable=False, tip=None):
        a = QAction(text, self)
        if glyph:
            a.setIcon(glyph_icon(glyph, mirror=mirror))
        if shortcuts:
            if isinstance(shortcuts, (list, tuple)):
                a.setShortcuts([QKeySequence(s) for s in shortcuts])
            else:
                a.setShortcut(QKeySequence(shortcuts))
        a.setCheckable(checkable)
        sc = a.shortcut()
        a.setToolTip(tip or (text + (f"（{sc.toString(QKeySequence.NativeText)}）" if not sc.isEmpty() else '')))
        if checkable:
            a.toggled.connect(slot)
        else:
            a.triggered.connect(slot)
        return a

    def _build_actions(self):
        A = self._act
        self.act_manage = A('管理模式', self.go_manage, None, G.GRID, tip='回到管理模式（Esc / Enter / 雙擊影像）')
        self.act_open = A('開啟影像…', self.open_dialog, 'Ctrl+O', G.FOLDER)
        self.act_reveal = A('在檔案總管中顯示', self._reveal, None)
        self.act_prev = A('上一張', self.prev, ['Left'], G.BACK)
        self.act_next = A('下一張', self.next, ['Right'], G.FORWARD)
        self.act_first = A('第一張', lambda: self.show_index(0), 'Home')
        self.act_last = A('最後一張', lambda: self.show_index(len(self.files) - 1), 'End')
        self.act_zoom_in = A('放大', self.canvas.zoom_in, ['+', '='], G.ZOOM_IN)
        self.act_zoom_out = A('縮小', self.canvas.zoom_out, ['-'], G.ZOOM_OUT)
        self.act_fit = A('符合視窗', self.canvas.fit, ['*', '0'], G.FIT)
        self.act_actual = A('實際大小 (100%)', self.canvas.actual_size, ['/', '1'], G.ACTUAL)
        self.act_full = A('全螢幕', self.toggle_fullscreen, ['F', 'F11'], G.FULLSCREEN)
        self.act_slide = A('投影片播放', self.toggle_slideshow, 'S', G.PLAY, checkable=True)
        self.act_info = A('顯示影像資訊', self.toggle_info, 'I', G.INFO, checkable=True)
        self.act_strip = A('顯示縮圖列', self._toggle_strip, 'T', G.FILMSTRIP, checkable=True)
        self.act_edit = A('編輯影像', self._edit, 'Ctrl+E', G.EDIT, tip='編輯影像：曝光、色階、曲線、色彩…（Ctrl+E）')
        self.act_rot_l = A('向左旋轉', lambda: self.rotate('ccw'), ['[', 'Ctrl+Left'], G.ROTATE, mirror=True)
        self.act_rot_r = A('向右旋轉', lambda: self.rotate('cw'), [']', 'Ctrl+Right'], G.ROTATE)
        self.act_delete = A('刪除', self.delete_current, 'Delete', G.DELETE)
        self.act_copy = A('複製影像到剪貼簿', self._copy_image, 'Ctrl+C', G.COPY)
        self.rating_actions = []
        for r in range(6):
            a = A('清除評等' if r == 0 else '★' * r, lambda _=False, r=r: self.set_rating(r), f'Ctrl+{r}')
            self.rating_actions.append(a)

        m_file = QMenu('檔案(&F)', self)
        m_file.addActions([self.act_open, self.act_reveal])
        m_file.addSeparator()
        m_file.addAction(self.act_manage)
        m_view = QMenu('檢視(&V)', self)
        m_view.addActions([self.act_prev, self.act_next, self.act_first, self.act_last])
        m_view.addSeparator()
        m_view.addActions([self.act_zoom_in, self.act_zoom_out, self.act_fit, self.act_actual])
        m_view.addSeparator()
        m_view.addActions([self.act_full, self.act_slide, self.act_info, self.act_strip])
        m_tools = QMenu('工具(&T)', self)
        m_tools.addAction(self.act_edit)
        m_tools.addSeparator()
        m_tools.addActions([self.act_rot_l, self.act_rot_r])
        m_rate = m_tools.addMenu('設定評等')
        m_rate.addActions(self.rating_actions)
        m_tools.addSeparator()
        m_tools.addActions([self.act_copy, self.act_delete])
        self.menus = [m_file, m_view, m_tools]
        # make shortcuts work even while the menu bar is hidden (full screen)
        for a in [self.act_prev, self.act_next, self.act_first, self.act_last, self.act_zoom_in, self.act_zoom_out,
                  self.act_fit, self.act_actual, self.act_full, self.act_slide, self.act_info, self.act_strip,
                  self.act_edit, self.act_rot_l, self.act_rot_r, self.act_delete, self.act_copy, self.act_open,
                  *self.rating_actions]:
            a.setShortcutContext(Qt.WidgetWithChildrenShortcut)
            self.addAction(a)

    def _build_toolbar(self):
        tb = QToolBar()
        tb.setIconSize(QSize(20, 20))
        tb.setToolButtonStyle(Qt.ToolButtonIconOnly)
        tb.addAction(self.act_manage)
        tb.addSeparator()
        tb.addActions([self.act_prev, self.act_next])
        tb.addSeparator()
        tb.addActions([self.act_zoom_in, self.act_zoom_out, self.act_fit, self.act_actual])
        tb.addSeparator()
        tb.addActions([self.act_rot_l, self.act_rot_r])
        tb.addSeparator()
        tb.addAction(self.act_edit)
        tb.addAction(self.act_delete)
        tb.addSeparator()
        tb.addActions([self.act_slide, self.act_full, self.act_info, self.act_strip])
        return tb

    def _build_status(self):
        w = QWidget()
        w.setObjectName('StatusBar')
        h = QHBoxLayout(w)
        h.setContentsMargins(6, 3, 6, 3)
        h.setSpacing(4)
        self.st_name = QLabel()
        self.st_name.setStyleSheet('color:#e8e8e8; font-weight:600;')
        self.st_index = QLabel()
        self.st_dims = QLabel()
        self.st_size = QLabel()
        self.st_date = QLabel()
        self.st_rating = QLabel()
        self.st_rating.setStyleSheet('color:#ffc828;')
        self.st_zoom = QLabel()
        for wd in (self.st_name, self.st_index, self.st_dims, self.st_size, self.st_date, self.st_rating):
            h.addWidget(wd)
        h.addStretch(1)
        h.addWidget(self.st_zoom)
        return w

    # ------------------------------------------------------------------ opening
    def current_path(self):
        if 0 <= self.index < len(self.files):
            return self.files[self.index]
        return None

    def open_files(self, files, index=0):
        self.files = list(files)
        self.index = -1
        self._displayed = None
        self.strip_model.set_entries([entry_from_path(p) for p in self.files])
        if not self.files:
            self.canvas.clear('沒有影像')
            self._update_status()
            return
        self.show_index(index)

    def open_path(self, path):
        folder = os.path.dirname(os.path.abspath(path))
        files = list_images(folder)
        n = norm(path)
        idx = next((i for i, f in enumerate(files) if norm(f) == n), -1)
        if idx < 0:
            files.append(path)
            idx = len(files) - 1
        self.open_files(files, idx)

    def open_dialog(self):
        start = os.path.dirname(self.current_path()) if self.current_path() else ''
        exts = ' '.join('*' + e for e in sorted(IMAGE_EXTS))
        fn, _ = QFileDialog.getOpenFileName(self, '開啟影像', start, f'影像檔 ({exts});;所有檔案 (*.*)')
        if fn:
            self.open_path(fn)

    # ------------------------------------------------------------------ navigation
    def _fit_size(self):
        d = self.canvas.devicePixelRatioF() or 1.0
        return int(self.canvas.width() * d), int(self.canvas.height() * d)

    def show_index(self, i, direction=None):
        if not self.files:
            return
        i = max(0, min(len(self.files) - 1, i))
        if direction is None:
            direction = 1 if i >= self.index else -1
        self._direction = direction
        self.index = i
        path = self.files[i]
        self._stop_movie()
        cached = self.loader.get(path)
        if cached is not None:
            self._display(path, *cached)
        else:
            fw, fh = self._fit_size()
            self.loader.request(path, fw, fh, priority=10)
        self._prefetch()
        self._sync_strip()
        self._update_status()

    def _prefetch(self):
        fw, fh = self._fit_size()
        order = (1, 2, -1) if self._direction > 0 else (-1, -2, 1)
        for k in order:
            j = self.index + k
            if 0 <= j < len(self.files):
                self.loader.request(self.files[j], fw, fh, priority=0)

    def _on_loaded(self, path):
        cur = self.current_path()
        if cur and path == cur and self._displayed != cur:
            v = self.loader.get(path)
            if v is not None:
                self._display(path, *v)

    def _display(self, path, img, fit):
        self._displayed = path
        if img.isNull():
            self.canvas.clear(f'無法開啟影像\n{os.path.basename(path)}')
            self._update_status()
            return
        self.canvas.set_image(img, hint=fit if not fit.isNull() else None)
        if path.lower().endswith('.gif'):
            self._start_movie(path)
        if self._info:
            self._refresh_info()
        if self._fullscreen and not self._info:
            self.flash(f"{os.path.basename(path)}    {self.index + 1} / {len(self.files)}", 1500)
        self._update_status()

    def step(self, d):
        if d > 0:
            self.next()
        else:
            self.prev()

    def next(self):
        if not self.files:
            return
        if self.index >= len(self.files) - 1:
            self.flash('已是最後一張', 1000)
            return
        self.show_index(self.index + 1, 1)

    def prev(self):
        if not self.files:
            return
        if self.index <= 0:
            self.flash('已是第一張', 1000)
            return
        self.show_index(self.index - 1, -1)

    def _sync_strip(self):
        if not self.strip.isVisible() or self.index < 0:
            return
        idx = self.strip_model.index(self.index)
        self.strip.selectionModel().setCurrentIndex(idx, QItemSelectionModel.ClearAndSelect)
        self.strip.scrollTo(idx, QAbstractItemView.PositionAtCenter)

    def _toggle_strip(self, on):
        self.strip.setVisible(on and not self._fullscreen)
        self.settings.set('view/filmstrip', on)
        if on:
            QTimer.singleShot(0, self._sync_strip)

    # ------------------------------------------------------------------ animation
    def _start_movie(self, path):
        m = QMovie(path)
        if not m.isValid() or m.frameCount() == 1:
            return
        m.frameChanged.connect(lambda _f, m=m: self.canvas.set_image(m.currentImage(), keep_view=True))
        self._movie = m
        m.start()

    def _stop_movie(self):
        if self._movie is not None:
            self._movie.stop()
            self._movie.deleteLater()
            self._movie = None

    # ------------------------------------------------------------------ status / overlays
    def _update_status(self):
        path = self.current_path()
        if not path:
            for lb in (self.st_name, self.st_index, self.st_dims, self.st_size, self.st_date, self.st_rating, self.st_zoom):
                lb.setText('')
            return
        self.st_name.setText(os.path.basename(path))
        self.st_index.setText(f"{self.index + 1} / {len(self.files)}")
        if self.isVisible():
            from .common import APP_TITLE
            self.window().setWindowTitle(f"{os.path.basename(path)} - {APP_TITLE}")
        img = self.canvas.image()
        self.st_dims.setText(f"{img.width()} × {img.height()}" if self._displayed == path and not img.isNull() else '載入中…')
        try:
            st = os.stat(path)
            self.st_size.setText(human_size(st.st_size))
            self.st_date.setText(fmt_time(st.st_mtime))
        except OSError:
            self.st_size.setText('')
            self.st_date.setText('')
        r = self.ratings.get(path)
        self.st_rating.setText('★' * r)
        self.st_zoom.setText(f"{self.canvas.zoom() * 100:.0f}%" + ('（符合視窗）' if self.canvas.is_fit() else ''))

    def flash(self, text, ms=1500):
        if self._info:
            return
        self._flash_text = text
        self.canvas.overlay_text = text
        self.canvas.update()
        self.flash_timer.start(ms)

    def _clear_flash(self):
        if not self._info:
            self.canvas.overlay_text = ''
            self.canvas.update()

    def toggle_info(self, on):
        self._info = on
        if on:
            self._refresh_info()
        else:
            self.canvas.overlay_text = ''
            self.canvas.update()

    def _refresh_info(self):
        path = self.current_path()
        if not path:
            return
        img = self.canvas.image()
        lines = [os.path.basename(path), f"{img.width()} × {img.height()}    {self.index + 1} / {len(self.files)}"]
        try:
            st = os.stat(path)
            lines.append(f"{human_size(st.st_size)}    {fmt_time(st.st_mtime)}")
        except OSError:
            pass
        for k, v in exif_info(path):
            if k in ('相機', '鏡頭', '拍攝時間', '快門', '光圈', 'ISO', '焦距', '曝光補償'):
                lines.append(f"{k}：{v}")
        self.canvas.overlay_text = '\n'.join(lines)
        self.canvas.update()

    # ------------------------------------------------------------------ actions
    def go_manage(self):
        if self.slide_timer.isActive():
            self.act_slide.setChecked(False)
        self.requestManage.emit(self.current_path() or '')

    def _edit(self):
        if self.current_path():
            self.requestEdit.emit(self.current_path())

    def _reveal(self):
        if self.current_path():
            reveal_in_explorer(self.current_path())

    def _copy_image(self):
        img = self.canvas.image()
        if not img.isNull():
            QGuiApplication.clipboard().setImage(img)
            self.flash('已複製影像到剪貼簿', 1000)

    def set_rating(self, r):
        path = self.current_path()
        if not path:
            return
        self.ratings.set(path, r)
        self.strip_model.refresh_path(path)
        self.fileChanged.emit(path)
        self.flash('評等：' + ('★' * r if r else '無'), 900)
        self._update_status()

    def rotate(self, op):
        path = self.current_path()
        if not path:
            return
        ok, msg = rotate_file(path, op)
        if not ok:
            QMessageBox.warning(self, '旋轉', msg)
            return
        self._after_file_change(path)
        self.fileChanged.emit(path)
        self.flash(msg, 900)

    def _after_file_change(self, path):
        self.loader.invalidate(path)
        self.thumbs.invalidate(path)
        self.strip_model.replace_entry(path, entry_from_path(path))
        if path == self.current_path():
            self._displayed = None
            fw, fh = self._fit_size()
            self.loader.request(path, fw, fh, priority=10)

    def on_external_change(self, path):
        """Called when another mode modified a file (rotation, edit save)."""
        if any(norm(f) == norm(path) for f in self.files):
            self._after_file_change(next(f for f in self.files if norm(f) == norm(path)))

    def on_external_delete(self, path):
        n = norm(path)
        for i, f in enumerate(self.files):
            if norm(f) == n:
                del self.files[i]
                self.strip_model.remove_path(f)
                self.loader.invalidate(f)
                if i < self.index or (i == self.index and self.index >= len(self.files)):
                    self.index = max(0, self.index - 1)
                break

    def delete_current(self):
        path = self.current_path()
        if not path:
            return
        if QMessageBox.question(self, '刪除', f'確定要將「{os.path.basename(path)}」移到資源回收筒嗎？') != QMessageBox.Yes:
            return
        if not move_to_trash(path):
            QMessageBox.warning(self, '刪除', '無法刪除此檔案。')
            return
        self.loader.invalidate(path)
        self.ratings.remove(path)
        i = self.index
        del self.files[i]
        self.strip_model.remove_path(path)
        self.fileDeleted.emit(path)
        self._displayed = None
        if not self.files:
            self.index = -1
            self.canvas.clear('資料夾中已沒有影像')
            self._update_status()
            return
        self.index = -1
        self.show_index(min(i, len(self.files) - 1), 1)

    # ------------------------------------------------------------------ full screen / slideshow
    def toggle_fullscreen(self):
        self.set_fullscreen(not self._fullscreen)

    def set_fullscreen(self, on):
        if on == self._fullscreen:
            return
        self._fullscreen = on
        self.toolbar.setVisible(not on)
        self.statusw.setVisible(not on)
        self.strip.setVisible(not on and self.act_strip.isChecked())
        self.canvas.bg = QColor(0, 0, 0) if on else QColor(30, 30, 32)
        self.requestFullscreen.emit(on)
        self.canvas.setFocus()
        if not on and self.act_strip.isChecked():
            QTimer.singleShot(0, self._sync_strip)

    def toggle_slideshow(self, on):
        if on:
            if not self.files:
                self.act_slide.setChecked(False)
                return
            self.slide_timer.start(self.settings.get('view/slide_ms', 3000, int))
            self.act_slide.setIcon(glyph_icon(G.PAUSE))
            if not self._fullscreen:
                self.set_fullscreen(True)
            self.flash('投影片播放（S 停止）', 1200)
        else:
            self.slide_timer.stop()
            self.act_slide.setIcon(glyph_icon(G.PLAY))

    def _slide_next(self):
        if not self.files:
            return
        if self.index >= len(self.files) - 1:
            self.show_index(0, 1)
        else:
            self.show_index(self.index + 1, 1)

    def leave(self):
        """Called when switching away from view mode."""
        if self.act_slide.isChecked():
            self.act_slide.setChecked(False)
        if self._fullscreen:
            self.set_fullscreen(False)
        self._stop_movie()

    # ------------------------------------------------------------------ keys
    def keyPressEvent(self, ev):
        k = ev.key()
        if k == Qt.Key_Escape:
            if self.act_slide.isChecked():
                self.act_slide.setChecked(False)
                if self._fullscreen:
                    self.set_fullscreen(False)
            elif self._fullscreen:
                self.set_fullscreen(False)
            else:
                self.go_manage()
            return
        if k in (Qt.Key_Return, Qt.Key_Enter):
            self.go_manage()
            return
        if k in (Qt.Key_Space, Qt.Key_PageDown):
            self.next()
            return
        if k in (Qt.Key_Backspace, Qt.Key_PageUp):
            self.prev()
            return
        if k in (Qt.Key_Up, Qt.Key_Down):
            if self.canvas.pannable():
                self.canvas.pan(0, 80 if k == Qt.Key_Up else -80)
            elif k == Qt.Key_Down:
                self.next()
            else:
                self.prev()
            return
        super().keyPressEvent(ev)

    def showEvent(self, ev):
        super().showEvent(ev)
        QTimer.singleShot(0, self._sync_strip)
