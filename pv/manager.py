"""Manage mode: folder tree, thumbnail browser, preview and properties (ACDSee style)."""
from __future__ import annotations

import os
import shutil

from PySide6.QtCore import (Qt, Signal, QTimer, QSize, QDir, QEvent, QStandardPaths, QFileSystemWatcher,
                            QModelIndex, QItemSelectionModel, QItemSelection, QRectF, QThreadPool)
from PySide6.QtGui import QAction, QKeySequence, QImage, QPainter, QColor, QGuiApplication
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QToolBar, QLabel, QListView, QTreeView,
                               QListWidget, QListWidgetItem, QSplitter, QLineEdit, QComboBox, QSlider,
                               QFileSystemModel, QAbstractItemView, QMenu, QMessageBox, QFileDialog,
                               QInputDialog, QTreeWidget, QTreeWidgetItem, QHeaderView, QProgressDialog,
                               QApplication, QSizePolicy, QToolButton)

from .common import (G, glyph_icon, norm, natural_key, human_size, fmt_time, exif_info, oriented_size,
                     move_to_trash, unique_path, reveal_in_explorer, rotate_file, is_image)
from .thumbs import FolderModel, ThumbDelegate, scan_folder, Entry
from .viewer import ImageTask, _LoadSig
from .dialogs import RenameDialog, BatchRenameDialog, BatchResizeDialog


class PreviewPane(QWidget):
    def __init__(self, thumbs, parent=None):
        super().__init__(parent)
        self.thumbs = thumbs
        self._img = QImage()
        self._path = None
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(1)
        self._sig = _LoadSig()
        self._sig.done.connect(self._done)
        self.setMinimumHeight(180)

    def show_entry(self, e: Entry | None):
        if e is None or e.is_dir:
            self._path = None
            self._img = QImage()
            self.update()
            return
        if self._path == e.path:
            return
        self._path = e.path
        t = self.thumbs.get(e)
        self._img = t if t is not None else QImage()
        self.update()
        self.pool.clear()
        self.pool.start(ImageTask(e.path, self._sig, decode_max=1000))

    def _done(self, path, img, _fit):
        if path == self._path and not img.isNull():
            self._img = img
            self.update()

    def paintEvent(self, ev):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(24, 24, 26))
        if self._img.isNull():
            p.setPen(QColor(110, 110, 116))
            p.drawText(self.rect(), Qt.AlignCenter, '預覽')
            return
        r = QRectF(self.rect()).adjusted(8, 8, -8, -8)
        iw, ih = self._img.width(), self._img.height()
        s = min(r.width() / iw, r.height() / ih, 1.0 if max(iw, ih) > 400 else 4.0)
        w, h = iw * s, ih * s
        target = QRectF(r.x() + (r.width() - w) / 2, r.y() + (r.height() - h) / 2, w, h)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        p.drawImage(target, self._img)


class ManagePage(QWidget):
    requestView = Signal(list, int)
    requestEdit = Signal(str)
    fileChanged = Signal(str)
    fileDeleted = Signal(str)

    SORTS = [('名稱', 'name'), ('修改日期', 'date'), ('檔案大小', 'size'), ('類型', 'type')]

    def __init__(self, thumbs, ratings, settings, parent=None):
        super().__init__(parent)
        self.thumbs, self.ratings, self.settings = thumbs, ratings, settings
        self.folder = ''
        self.all_entries: list[Entry] = []
        self.back_stack: list[str] = []
        self.fwd_stack: list[str] = []
        self._tree_sync = False

        self.model = FolderModel(thumbs, self)
        self.delegate = ThumbDelegate(thumbs, ratings, size=settings.get('manage/thumb', 150, int))

        self._build_actions()
        self.toolbar = self._build_toolbar()

        # left: quick access + folder tree
        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        lv.setSpacing(0)
        t1 = QLabel('快速存取')
        t1.setObjectName('PanelTitle')
        lv.addWidget(t1)
        self.quick = QListWidget()
        self.quick.setIconSize(QSize(18, 18))
        self.quick.setMaximumHeight(200)
        self.quick.itemClicked.connect(lambda it: self.navigate(it.data(Qt.UserRole)))
        self.quick.setContextMenuPolicy(Qt.CustomContextMenu)
        self.quick.customContextMenuRequested.connect(self._quick_menu)
        lv.addWidget(self.quick)
        t2 = QLabel('資料夾')
        t2.setObjectName('PanelTitle')
        lv.addWidget(t2)
        self.fs_model = QFileSystemModel(self)
        self.fs_model.setFilter(QDir.AllDirs | QDir.NoDotAndDotDot | QDir.Drives)
        self.fs_model.setRootPath('')
        self.tree = QTreeView()
        self.tree.setModel(self.fs_model)
        for c in (1, 2, 3):
            self.tree.hideColumn(c)
        self.tree.setHeaderHidden(True)
        self.tree.setAnimated(False)
        self.tree.setIndentation(14)
        self.tree.setUniformRowHeights(True)
        self.tree.selectionModel().currentChanged.connect(self._tree_current_changed)
        lv.addWidget(self.tree, 1)
        self._tree_timer = QTimer(self)
        self._tree_timer.setSingleShot(True)
        self._tree_timer.setInterval(220)
        self._tree_timer.timeout.connect(self._tree_navigate)
        self._refresh_quick()

        # center: thumbnails
        self.view = QListView()
        self.view.setModel(self.model)
        self.view.setItemDelegate(self.delegate)
        self.view.setViewMode(QListView.IconMode)
        self.view.setResizeMode(QListView.Adjust)
        self.view.setMovement(QListView.Static)
        self.view.setUniformItemSizes(True)
        self.view.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.view.setSpacing(3)
        self.view.setLayoutMode(QListView.Batched)
        self.view.setBatchSize(300)
        self.view.setMouseTracking(True)
        self.view.setDragEnabled(True)
        self.view.setDragDropMode(QAbstractItemView.DragOnly)
        self.view.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.view.verticalScrollBar().setSingleStep(30)
        self.view.setContextMenuPolicy(Qt.CustomContextMenu)
        self.view.customContextMenuRequested.connect(self._context_menu)
        self.view.doubleClicked.connect(self._activate)
        self.view.selectionModel().selectionChanged.connect(self._selection_changed)
        self.view.selectionModel().currentChanged.connect(lambda *_: self._sel_timer.start())
        self.view.installEventFilter(self)
        self.view.viewport().installEventFilter(self)
        for a in self.view_actions:
            a.setShortcutContext(Qt.WidgetWithChildrenShortcut)
            self.view.addAction(a)

        # right: preview + properties
        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(0, 0, 0, 0)
        rv.setSpacing(0)
        t3 = QLabel('預覽')
        t3.setObjectName('PanelTitle')
        rv.addWidget(t3)
        self.preview = PreviewPane(thumbs)
        rv.addWidget(self.preview, 2)
        t4 = QLabel('屬性')
        t4.setObjectName('PanelTitle')
        rv.addWidget(t4)
        self.props = QTreeWidget()
        self.props.setColumnCount(2)
        self.props.setHeaderLabels(['屬性', '值'])
        self.props.header().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.props.setRootIsDecorated(False)
        self.props.setIndentation(8)
        rv.addWidget(self.props, 3)
        self.right_panel = right

        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.addWidget(left)
        self.splitter.addWidget(self.view)
        self.splitter.addWidget(right)
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setStretchFactor(2, 0)
        self.splitter.setChildrenCollapsible(False)
        sizes = settings.get('manage/splitter', None, list)
        try:
            self.splitter.setSizes([int(x) for x in sizes] if sizes and len(sizes) == 3 else [240, 900, 300])
        except (TypeError, ValueError):
            self.splitter.setSizes([240, 900, 300])
        self.splitter.splitterMoved.connect(lambda *_: settings.set('manage/splitter', self.splitter.sizes()))
        show_preview = settings.get('manage/preview', True, bool)
        right.setVisible(show_preview)
        self.act_preview.setChecked(show_preview)

        self.statusw = QWidget()
        self.statusw.setObjectName('StatusBar')
        sh = QHBoxLayout(self.statusw)
        sh.setContentsMargins(6, 3, 6, 3)
        self.st_left = QLabel()
        self.st_right = QLabel()
        sh.addWidget(self.st_left)
        sh.addStretch(1)
        sh.addWidget(self.st_right)

        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        v.addWidget(self.toolbar)
        v.addWidget(self.splitter, 1)
        v.addWidget(self.statusw)

        self.watcher = QFileSystemWatcher(self)
        self.watcher.directoryChanged.connect(lambda _p: self._refresh_timer.start())
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.setInterval(700)
        self._refresh_timer.timeout.connect(lambda: self.reload(keep_selection=True))
        self._sel_timer = QTimer(self)
        self._sel_timer.setSingleShot(True)
        self._sel_timer.setInterval(90)
        self._sel_timer.timeout.connect(self._update_details)
        self._filter_timer = QTimer(self)
        self._filter_timer.setSingleShot(True)
        self._filter_timer.setInterval(160)
        self._filter_timer.timeout.connect(lambda: self._apply_filter_sort(keep=True))

    # ------------------------------------------------------------------ building
    def _act(self, text, slot, shortcut=None, glyph=None, mirror=False, checkable=False, tip=None):
        a = QAction(text, self)
        if glyph:
            a.setIcon(glyph_icon(glyph, mirror=mirror))
        if shortcut:
            if isinstance(shortcut, (list, tuple)):
                a.setShortcuts([QKeySequence(s) for s in shortcut])
            else:
                a.setShortcut(QKeySequence(shortcut))
        a.setCheckable(checkable)
        sc = a.shortcut()
        a.setToolTip(tip or (text + (f"（{sc.toString(QKeySequence.NativeText)}）" if not sc.isEmpty() else '')))
        (a.toggled if checkable else a.triggered).connect(slot)
        return a

    def _build_actions(self):
        A = self._act
        self.act_back = A('上一頁', self.go_back, 'Alt+Left', G.BACK)
        self.act_fwd = A('下一頁', self.go_forward, 'Alt+Right', G.FORWARD)
        self.act_up = A('上一層', self.go_up, 'Alt+Up', G.UP)
        self.act_refresh = A('重新整理', lambda: self.reload(keep_selection=True), 'F5', G.REFRESH)
        self.act_open_folder = A('開啟資料夾…', self._open_folder_dialog, 'Ctrl+O', G.FOLDER)
        self.act_new_folder = A('新增資料夾…', self._new_folder, 'Ctrl+Shift+N', G.NEW_FOLDER)
        self.act_fav = A('加入快速存取', self._add_favorite, 'Ctrl+D', G.STAR)
        self.act_view = A('檢視', self._view_selected, None, G.PHOTO, tip='以檢視模式開啟（Enter / 雙擊）')
        self.act_edit = A('編輯', self._edit_selected, 'Ctrl+E', G.EDIT, tip='編輯影像：曝光、色階、曲線、色彩…（Ctrl+E）')
        self.act_rot_l = A('向左旋轉', lambda: self._rotate_selected('ccw'), 'Ctrl+Alt+Left', G.ROTATE, mirror=True)
        self.act_rot_r = A('向右旋轉', lambda: self._rotate_selected('cw'), 'Ctrl+Alt+Right', G.ROTATE)
        self.act_delete = A('刪除', self._delete_selected, 'Delete', G.DELETE)
        self.act_rename = A('重新命名…', self._rename_selected, 'F2', G.RENAME)
        self.act_copy_to = A('複製到資料夾…', lambda: self._copy_move(False), None, G.COPY)
        self.act_move_to = A('移動到資料夾…', lambda: self._copy_move(True), None, G.MOVE)
        self.act_copy_path = A('複製路徑', self._copy_path, 'Ctrl+Shift+C')
        self.act_reveal = A('在檔案總管中顯示', self._reveal, None, G.FOLDER)
        self.act_select_all = A('全選', lambda: self.view.selectAll(), 'Ctrl+A')
        self.act_batch_rename = A('批次重新命名…', self._batch_rename, None, G.RENAME)
        self.act_batch_resize = A('批次調整大小／轉檔…', self._batch_resize, None, G.PHOTO)
        self.act_preview = A('顯示預覽與屬性窗格', self._toggle_preview, 'F9', G.PREVIEW, checkable=True)
        self.act_bigger = A('放大縮圖', lambda: self.size_slider.setValue(self.size_slider.value() + 20), 'Ctrl+=')
        self.act_smaller = A('縮小縮圖', lambda: self.size_slider.setValue(self.size_slider.value() - 20), 'Ctrl+-')
        self.rating_actions = []
        for r in range(6):
            a = A('清除評等' if r == 0 else '★' * r, lambda _=False, r=r: self._rate_selected(r), f'Ctrl+{r}')
            self.rating_actions.append(a)
        # actions that must only fire while the thumbnail list has focus
        self.view_actions = [self.act_edit, self.act_rot_l, self.act_rot_r, self.act_delete, self.act_rename,
                             self.act_copy_path, *self.rating_actions]

        m_file = QMenu('檔案(&F)', self)
        m_file.addActions([self.act_open_folder, self.act_new_folder, self.act_fav])
        m_file.addSeparator()
        m_file.addActions([self.act_reveal])
        m_edit = QMenu('編輯(&E)', self)
        m_edit.addActions([self.act_select_all, self.act_copy_to, self.act_move_to, self.act_rename,
                           self.act_delete, self.act_copy_path])
        m_view = QMenu('檢視(&V)', self)
        m_view.addActions([self.act_view, self.act_refresh])
        m_view.addSeparator()
        m_view.addActions([self.act_back, self.act_fwd, self.act_up])
        m_view.addSeparator()
        m_view.addActions([self.act_bigger, self.act_smaller, self.act_preview])
        m_tools = QMenu('工具(&T)', self)
        m_tools.addAction(self.act_edit)
        m_tools.addActions([self.act_rot_l, self.act_rot_r])
        m_rate = m_tools.addMenu('設定評等')
        m_rate.addActions(self.rating_actions)
        m_tools.addSeparator()
        m_tools.addActions([self.act_batch_rename, self.act_batch_resize])
        self.menus = [m_file, m_edit, m_view, m_tools]

    def _build_toolbar(self):
        tb = QToolBar()
        tb.setIconSize(QSize(20, 20))
        tb.addActions([self.act_back, self.act_fwd, self.act_up, self.act_refresh])
        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText('資料夾路徑')
        self.path_edit.setMinimumWidth(220)
        self.path_edit.returnPressed.connect(lambda: self.navigate(self.path_edit.text().strip().strip('"')))
        tb.addWidget(self.path_edit)
        tb.addSeparator()
        for a in (self.act_view, self.act_edit):
            tb.addAction(a)
            btn = tb.widgetForAction(a)
            if isinstance(btn, QToolButton):
                btn.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        tb.addActions([self.act_rot_l, self.act_rot_r, self.act_delete])
        tb.addSeparator()
        self.sort_combo = QComboBox()
        for label, _ in self.SORTS:
            self.sort_combo.addItem('排序：' + label)
        self.sort_combo.setCurrentIndex(self.settings.get('manage/sort', 0, int))
        self.sort_combo.currentIndexChanged.connect(self._sort_changed)
        tb.addWidget(self.sort_combo)
        self.act_desc = self._act('遞減排序', self._sort_changed, None, G.SORT, checkable=True)
        self.act_desc.blockSignals(True)
        self.act_desc.setChecked(self.settings.get('manage/desc', False, bool))
        self.act_desc.blockSignals(False)
        tb.addAction(self.act_desc)
        self.rating_filter = QComboBox()
        self.rating_filter.addItems(['全部評等', '★1 以上', '★2 以上', '★3 以上', '★4 以上', '★5'])
        self.rating_filter.currentIndexChanged.connect(lambda _i: self._apply_filter_sort(keep=True))
        tb.addWidget(self.rating_filter)
        self.search = QLineEdit()
        self.search.setPlaceholderText('搜尋檔名…')
        self.search.setClearButtonEnabled(True)
        self.search.setFixedWidth(150)
        self.search.textChanged.connect(lambda _t: self._filter_timer.start())
        tb.addWidget(self.search)
        tb.addSeparator()
        lb = QLabel(' 縮圖 ')
        tb.addWidget(lb)
        self.size_slider = QSlider(Qt.Horizontal)
        self.size_slider.setRange(64, 320)
        self.size_slider.setFixedWidth(110)
        self.size_slider.setValue(self.delegate.ts)
        self.size_slider.valueChanged.connect(self._thumb_size_changed)
        tb.addWidget(self.size_slider)
        tb.addAction(self.act_preview)
        return tb

    # ------------------------------------------------------------------ navigation
    def navigate(self, folder, select=None, add_history=True):
        if not folder:
            return
        folder = os.path.abspath(os.path.expandvars(os.path.expanduser(folder)))
        if os.path.isfile(folder) and is_image(folder):
            select = folder
            folder = os.path.dirname(folder)
        if not os.path.isdir(folder):
            QMessageBox.warning(self, '開啟資料夾', f'找不到資料夾：\n{folder}')
            self.path_edit.setText(self.folder)
            return
        if add_history and self.folder and norm(folder) != norm(self.folder):
            self.back_stack.append(self.folder)
            self.fwd_stack.clear()
        changed = norm(folder) != norm(self.folder) if self.folder else True
        self.folder = folder
        self.settings.set('manage/last_folder', folder)
        self.path_edit.setText(folder)
        if self.watcher.directories():
            self.watcher.removePaths(self.watcher.directories())
        self.watcher.addPath(folder)
        if changed:
            self.thumbs.cancel_pending()
        self.reload(select=[select] if select else None, scroll_top=changed)
        self._sync_tree()
        self.act_back.setEnabled(bool(self.back_stack))
        self.act_fwd.setEnabled(bool(self.fwd_stack))
        self.act_up.setEnabled(os.path.dirname(folder) != folder)

    def go_back(self):
        if self.back_stack:
            self.fwd_stack.append(self.folder)
            prev = self.back_stack.pop()
            self.navigate(prev, select=None, add_history=False)

    def go_forward(self):
        if self.fwd_stack:
            self.back_stack.append(self.folder)
            self.navigate(self.fwd_stack.pop(), add_history=False)

    def go_up(self):
        if not self.folder:
            return
        parent = os.path.dirname(self.folder)
        if parent and parent != self.folder:
            self.navigate(parent, select=self.folder)

    def reload(self, keep_selection=False, select=None, scroll_top=False):
        if not self.folder:
            return
        sel = select if select is not None else (self.selected_paths() if keep_selection else None)
        scroll = None if scroll_top else self.view.verticalScrollBar().value()
        self.all_entries = scan_folder(self.folder)
        self._apply_filter_sort(select=sel, scroll=scroll)

    def _apply_filter_sort(self, select=None, scroll=None, keep=False):
        if keep:
            select = self.selected_paths()
            scroll = self.view.verticalScrollBar().value()
        text = self.search.text().strip().lower()
        minr = self.rating_filter.currentIndex()
        dirs = [e for e in self.all_entries if e.is_dir]
        files = [e for e in self.all_entries if not e.is_dir]
        if text:
            dirs = [e for e in dirs if text in e.name.lower()]
            files = [e for e in files if text in e.name.lower()]
        if minr:
            files = [e for e in files if self.ratings.get(e.path) >= minr]
        mode = self.SORTS[self.sort_combo.currentIndex()][1]
        keyf = {'name': lambda e: natural_key(e.name), 'date': lambda e: e.mtime,
                'size': lambda e: e.size, 'type': lambda e: (e.ext, natural_key(e.name))}[mode]
        dirs.sort(key=lambda e: natural_key(e.name))
        files.sort(key=keyf, reverse=self.act_desc.isChecked())
        self.model.set_entries(dirs + files)
        if select:
            self.select_paths(select)
        if scroll is not None:
            QTimer.singleShot(0, lambda s=scroll: self.view.verticalScrollBar().setValue(s))
        self._update_status()
        self._sel_timer.start()

    def select_paths(self, paths):
        sm = self.view.selectionModel()
        sel = QItemSelection()
        first = None
        for p in paths:
            if not p:
                continue
            r = self.model.row_of.get(norm(p))
            if r is not None:
                idx = self.model.index(r)
                sel.select(idx, idx)
                if first is None:
                    first = idx
        if first is not None:
            sm.setCurrentIndex(first, QItemSelectionModel.NoUpdate)
            sm.select(sel, QItemSelectionModel.ClearAndSelect)
            QTimer.singleShot(0, lambda f=first: self.view.scrollTo(f, QAbstractItemView.PositionAtCenter))

    def select_path(self, path):
        self.select_paths([path])

    def _sync_tree(self):
        idx = self.fs_model.index(self.folder)
        if idx.isValid():
            self._tree_sync = True
            self.tree.setCurrentIndex(idx)
            self.tree.scrollTo(idx)
            self._tree_sync = False

    def _tree_current_changed(self, cur, _prev):
        if self._tree_sync or not cur.isValid():
            return
        self._tree_timer.start()

    def _tree_navigate(self):
        idx = self.tree.currentIndex()
        if idx.isValid():
            path = self.fs_model.filePath(idx)
            if path and norm(path) != norm(self.folder or ''):
                self.navigate(path)

    def _refresh_quick(self):
        self.quick.clear()
        places = [
            ('桌面', QStandardPaths.writableLocation(QStandardPaths.DesktopLocation), G.DESKTOP),
            ('圖片', QStandardPaths.writableLocation(QStandardPaths.PicturesLocation), G.PICTURES),
            ('下載', QStandardPaths.writableLocation(QStandardPaths.DownloadLocation), G.DOWNLOAD),
            ('文件', QStandardPaths.writableLocation(QStandardPaths.DocumentsLocation), G.DOCUMENT),
        ]
        for name, path, glyph in places:
            if path and os.path.isdir(path):
                it = QListWidgetItem(glyph_icon(glyph), name)
                it.setData(Qt.UserRole, path)
                it.setToolTip(path)
                self.quick.addItem(it)
        for path in self.settings.get('manage/favorites', [], list):
            if os.path.isdir(path):
                it = QListWidgetItem(glyph_icon(G.STAR_FILL, '#ffc828'), os.path.basename(path.rstrip('\\/')) or path)
                it.setData(Qt.UserRole, path)
                it.setData(Qt.UserRole + 1, True)
                it.setToolTip(path)
                self.quick.addItem(it)

    def _add_favorite(self):
        if not self.folder:
            return
        favs = self.settings.get('manage/favorites', [], list)
        if norm(self.folder) not in [norm(f) for f in favs]:
            favs.append(self.folder)
            self.settings.set('manage/favorites', favs)
            self._refresh_quick()

    def _quick_menu(self, pos):
        it = self.quick.itemAt(pos)
        if it is None or not it.data(Qt.UserRole + 1):
            return
        m = QMenu(self)
        a = m.addAction('從快速存取移除')
        if m.exec(self.quick.viewport().mapToGlobal(pos)) is a:
            favs = [f for f in self.settings.get('manage/favorites', [], list) if norm(f) != norm(it.data(Qt.UserRole))]
            self.settings.set('manage/favorites', favs)
            self._refresh_quick()

    def _open_folder_dialog(self):
        d = QFileDialog.getExistingDirectory(self, '開啟資料夾', self.folder)
        if d:
            self.navigate(d)

    # ------------------------------------------------------------------ selection helpers
    def selected_entries(self) -> list[Entry]:
        rows = sorted({i.row() for i in self.view.selectionModel().selectedIndexes()})
        return [self.model.entries[r] for r in rows if r < len(self.model.entries)]

    def selected_paths(self) -> list[str]:
        return [e.path for e in self.selected_entries()]

    def selected_images(self) -> list[str]:
        return [e.path for e in self.selected_entries() if not e.is_dir]

    def image_list(self) -> list[str]:
        return [e.path for e in self.model.entries if not e.is_dir]

    def current_entry(self):
        idx = self.view.currentIndex()
        if idx.isValid() and self.view.selectionModel().isSelected(idx):
            return self.model.entries[idx.row()]
        ents = self.selected_entries()
        return ents[0] if ents else None

    def current_image(self):
        e = self.current_entry()
        if e is not None and not e.is_dir:
            return e.path
        imgs = self.selected_images()
        return imgs[0] if imgs else None

    # ------------------------------------------------------------------ activation
    def _activate(self, idx: QModelIndex):
        if not idx.isValid():
            return
        e = self.model.entries[idx.row()]
        if e.is_dir:
            self.navigate(e.path)
        else:
            self._open_viewer(e.path)

    def _open_viewer(self, path):
        imgs = self.image_list()
        n = norm(path)
        idx = next((i for i, p in enumerate(imgs) if norm(p) == n), 0)
        self.requestView.emit(imgs, idx)

    def _view_selected(self):
        e = self.current_entry()
        if e is None:
            imgs = self.image_list()
            if imgs:
                self._open_viewer(imgs[0])
            return
        if e.is_dir:
            self.navigate(e.path)
        else:
            self._open_viewer(e.path)

    def _edit_selected(self):
        p = self.current_image()
        if p:
            self.requestEdit.emit(p)

    # ------------------------------------------------------------------ details
    def _selection_changed(self, *_):
        self._sel_timer.start()
        self._update_status()

    def _update_status(self):
        nd = sum(1 for e in self.model.entries if e.is_dir)
        nf = len(self.model.entries) - nd
        txt = f"{nf} 個影像" + (f"，{nd} 個資料夾" if nd else '')
        sel = self.selected_entries()
        if sel:
            size = sum(e.size for e in sel if not e.is_dir)
            txt += f"　｜　已選取 {len(sel)} 個（{human_size(size)}）"
        self.st_left.setText(txt)
        self.st_right.setText(self.folder)

    def _update_details(self):
        e = self.current_entry()
        if not self.right_panel.isVisible():
            return
        self.preview.show_entry(e)
        self.props.clear()
        if e is None:
            return

        def section(title, items):
            if not items:
                return
            top = QTreeWidgetItem([title])
            f = top.font(0)
            f.setBold(True)
            top.setFont(0, f)
            top.setForeground(0, QColor(140, 180, 255))
            self.props.addTopLevelItem(top)
            for k, v in items:
                it = QTreeWidgetItem([k, str(v)])
                it.setToolTip(1, str(v))
                top.addChild(it)
            top.setExpanded(True)

        if e.is_dir:
            section('資料夾', [('名稱', e.name), ('路徑', e.path), ('修改日期', fmt_time(e.mtime))])
            return
        section('檔案', [('名稱', e.name), ('資料夾', os.path.dirname(e.path)), ('大小', human_size(e.size)),
                         ('修改日期', fmt_time(e.mtime)), ('類型', e.ext.lstrip('.').upper())])
        img_items = []
        s = oriented_size(e.path)
        if s.isValid():
            mp = s.width() * s.height() / 1e6
            img_items.append(('尺寸', f"{s.width()} × {s.height()}（{mp:.1f} MP）"))
        r = self.ratings.get(e.path)
        img_items.append(('評等', '★' * r if r else '—'))
        section('影像', img_items)
        section('相機 (EXIF)', exif_info(e.path))

    def _toggle_preview(self, on):
        self.right_panel.setVisible(on)
        self.settings.set('manage/preview', on)
        if on:
            self._update_details()

    def _thumb_size_changed(self, v):
        self.delegate.set_size(v)
        self.settings.set('manage/thumb', v)
        self.model.layoutAboutToBeChanged.emit()
        self.model.layoutChanged.emit()

    def _sort_changed(self, *_):
        self.settings.set('manage/sort', self.sort_combo.currentIndex())
        self.settings.set('manage/desc', self.act_desc.isChecked())
        self._apply_filter_sort(keep=True)

    # ------------------------------------------------------------------ events
    def eventFilter(self, obj, ev):
        if obj is self.view and ev.type() == QEvent.KeyPress:
            k = ev.key()
            if k in (Qt.Key_Return, Qt.Key_Enter):
                self._activate(self.view.currentIndex())
                return True
            if k == Qt.Key_Backspace:
                self.go_up()
                return True
        if obj is self.view.viewport() and ev.type() == QEvent.Wheel and (ev.modifiers() & Qt.ControlModifier):
            d = ev.angleDelta().y()
            self.size_slider.setValue(self.size_slider.value() + (16 if d > 0 else -16))
            return True
        return super().eventFilter(obj, ev)

    def focus_view(self):
        self.view.setFocus()

    # ------------------------------------------------------------------ context menu
    def _context_menu(self, pos):
        idx = self.view.indexAt(pos)
        sm = self.view.selectionModel()
        if idx.isValid() and not sm.isSelected(idx):
            sm.setCurrentIndex(idx, QItemSelectionModel.ClearAndSelect)
        if not idx.isValid():
            sm.clearSelection()
        ents = self.selected_entries()
        m = QMenu(self)
        if not ents:
            m.addAction(self.act_new_folder)
            m.addAction(self.act_refresh)
            m.addAction(self.act_fav)
            m.addSeparator()
            a = m.addAction(glyph_icon(G.FOLDER), '在檔案總管中開啟此資料夾')
            a.triggered.connect(lambda: reveal_in_explorer(self.folder))
        elif all(e.is_dir for e in ents):
            a = m.addAction(glyph_icon(G.FOLDER), '開啟')
            a.triggered.connect(lambda: self.navigate(ents[0].path))
            m.addSeparator()
            m.addActions([self.act_rename, self.act_delete])
            m.addSeparator()
            m.addActions([self.act_reveal, self.act_copy_path])
        else:
            m.addAction(self.act_view)
            m.addAction(self.act_edit)
            m.setDefaultAction(self.act_view)
            m.addSeparator()
            m.addActions([self.act_rot_l, self.act_rot_r])
            rm = m.addMenu(glyph_icon(G.STAR), '設定評等')
            rm.addActions(self.rating_actions)
            m.addSeparator()
            m.addActions([self.act_copy_to, self.act_move_to, self.act_rename, self.act_delete])
            m.addSeparator()
            m.addActions([self.act_batch_rename, self.act_batch_resize])
            m.addSeparator()
            m.addActions([self.act_copy_path, self.act_reveal])
        m.exec(self.view.viewport().mapToGlobal(pos))

    # ------------------------------------------------------------------ file operations
    def on_external_change(self, path):
        self.thumbs.invalidate(path)
        if self.folder and norm(os.path.dirname(path)) == norm(self.folder):
            self._refresh_timer.start(150)

    def on_external_delete(self, path):
        self.on_external_change(path)

    def _rotate_selected(self, op):
        imgs = self.selected_images()
        if not imgs:
            return
        errors = []
        for p in imgs:
            ok, msg = rotate_file(p, op)
            if ok:
                self.thumbs.invalidate(p)
                self.fileChanged.emit(p)
            else:
                errors.append(f"{os.path.basename(p)}：{msg}")
        self.reload(keep_selection=True)
        if errors:
            QMessageBox.warning(self, '旋轉', '\n'.join(errors[:15]))

    def _rate_selected(self, r):
        for p in self.selected_images():
            self.ratings.set(p, r)
            self.model.refresh_path(p)
        if self.rating_filter.currentIndex():
            self._apply_filter_sort(keep=True)
        self._sel_timer.start()

    def _delete_selected(self):
        ents = self.selected_entries()
        if not ents:
            return
        if len(ents) == 1:
            msg = f'確定要將「{ents[0].name}」移到資源回收筒嗎？'
        else:
            msg = f'確定要將這 {len(ents)} 個項目移到資源回收筒嗎？'
        if QMessageBox.question(self, '刪除', msg) != QMessageBox.Yes:
            return
        rows = sorted({i.row() for i in self.view.selectionModel().selectedIndexes()})
        next_row = rows[0] if rows else 0
        failed = []
        for e in ents:
            if move_to_trash(e.path):
                self.ratings.remove(e.path)
                self.thumbs.invalidate(e.path)
                self.fileDeleted.emit(e.path)
            else:
                failed.append(e.name)
        self.reload()
        if self.model.entries:
            r = min(next_row, len(self.model.entries) - 1)
            self.view.setCurrentIndex(self.model.index(r))
        if failed:
            QMessageBox.warning(self, '刪除', '無法刪除：\n' + '\n'.join(failed[:15]))

    def _rename_selected(self):
        e = self.current_entry()
        if e is None:
            return
        dlg = RenameDialog(e.name, self)
        if dlg.exec() != RenameDialog.Accepted:
            return
        new = dlg.value()
        if not new or new == e.name:
            return
        if not e.is_dir and not os.path.splitext(new)[1]:
            new += e.ext
        dst = os.path.join(os.path.dirname(e.path), new)
        if os.path.exists(dst) and norm(dst) != norm(e.path):
            QMessageBox.warning(self, '重新命名', '已有相同名稱的檔案。')
            return
        try:
            os.rename(e.path, dst)
        except OSError as ex:
            QMessageBox.warning(self, '重新命名', f'重新命名失敗：{ex}')
            return
        self.ratings.move(e.path, dst)
        self.thumbs.invalidate(e.path)
        self.fileDeleted.emit(e.path)
        self.reload(select=[dst])

    def _batch_rename(self):
        imgs = self.selected_images()
        if not imgs:
            return
        dlg = BatchRenameDialog(imgs, self)
        if dlg.exec() and dlg.result_pairs:
            for old, new in dlg.result_pairs:
                self.ratings.move(old, new)
                self.thumbs.invalidate(old)
                self.fileDeleted.emit(old)
            self.reload(select=[n for _, n in dlg.result_pairs])

    def _batch_resize(self):
        imgs = self.selected_images()
        if not imgs:
            return
        dlg = BatchResizeDialog(imgs, self.settings, self)
        dlg.exec()
        self.reload(keep_selection=True)

    def _copy_move(self, move):
        ents = self.selected_entries()
        if not ents:
            return
        start = self.settings.get('manage/last_target', self.folder)
        d = QFileDialog.getExistingDirectory(self, '移動到資料夾' if move else '複製到資料夾', start)
        if not d:
            return
        self.settings.set('manage/last_target', d)
        if norm(d) == norm(self.folder):
            if move:
                return
        prog = None
        if len(ents) > 8:
            prog = QProgressDialog('正在處理…', '取消', 0, len(ents), self)
            prog.setWindowModality(Qt.WindowModal)
            prog.setMinimumDuration(300)
        errors = []
        for i, e in enumerate(ents):
            if prog:
                prog.setValue(i)
                QApplication.processEvents()
                if prog.wasCanceled():
                    break
            try:
                dst = unique_path(d, e.name)
                if move:
                    shutil.move(e.path, dst)
                    self.ratings.move(e.path, dst)
                    self.thumbs.invalidate(e.path)
                    self.fileDeleted.emit(e.path)
                elif e.is_dir:
                    shutil.copytree(e.path, dst)
                else:
                    shutil.copy2(e.path, dst)
            except OSError as ex:
                errors.append(f"{e.name}：{ex}")
        if prog:
            prog.setValue(len(ents))
        self.reload(keep_selection=not move)
        if errors:
            QMessageBox.warning(self, '複製／移動', '\n'.join(errors[:15]))

    def _new_folder(self):
        if not self.folder:
            return
        name, ok = QInputDialog.getText(self, '新增資料夾', '資料夾名稱：', text='新資料夾')
        if not ok or not name.strip():
            return
        path = unique_path(self.folder, name.strip())
        try:
            os.makedirs(path)
        except OSError as ex:
            QMessageBox.warning(self, '新增資料夾', str(ex))
            return
        self.reload(select=[path])

    def _copy_path(self):
        paths = self.selected_paths()
        if paths:
            QGuiApplication.clipboard().setText('\n'.join(paths))

    def _reveal(self):
        paths = self.selected_paths()
        reveal_in_explorer(paths[0] if paths else self.folder)
