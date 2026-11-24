"""Main window: mode bar (管理 / 檢視 / 編輯) with stacked pages."""
from __future__ import annotations

import os

from PySide6.QtCore import Qt, QTimer, QStandardPaths
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                               QButtonGroup, QStackedWidget, QMenu, QMessageBox)

from .common import APP_TITLE, Settings, RatingDB, app_icon, is_image, norm, glyph_icon, G
from .dialogs import show_shortcuts, show_about, show_licenses, show_donate, SettingsDialog
from .manager import ManagePage
from .thumbs import ThumbCache
from .viewer import ViewPage


class MainWindow(QMainWindow):
    def __init__(self, start_path=None, start_mode=None):
        super().__init__()
        self.settings = Settings()
        self.ratings = RatingDB()
        self.thumbs = ThumbCache(self)
        self.mode = None
        self._edit = None          # the editor (and numpy/Pillow) is created on first use
        self._edit_return = 'manage'
        self._was_maximized = False

        self.setWindowTitle(APP_TITLE)
        self.setWindowIcon(app_icon())
        self.resize(1400, 900)

        central = QWidget()
        v = QVBoxLayout(central)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        self.modebar = self._build_modebar()
        v.addWidget(self.modebar)
        self.stack = QStackedWidget()
        v.addWidget(self.stack, 1)
        self.setCentralWidget(central)

        self.manage = ManagePage(self.thumbs, self.ratings, self.settings)
        self.view = ViewPage(self.thumbs, self.ratings, self.settings)
        for page in (self.manage, self.view):
            self.stack.addWidget(page)

        self.manage.requestView.connect(self.open_viewer)
        self.manage.requestEdit.connect(self.open_editor)
        self.manage.fileChanged.connect(self.view.on_external_change)
        self.manage.fileDeleted.connect(self.view.on_external_delete)
        self.view.requestManage.connect(self.back_to_manage)
        self.view.requestEdit.connect(self.open_editor)
        self.view.requestFullscreen.connect(self._set_fullscreen)
        self.view.fileChanged.connect(self.manage.on_external_change)
        self.view.fileDeleted.connect(self.manage.on_external_delete)

        self.help_menu = QMenu('說明(&H)', self)
        a = self.help_menu.addAction('快速鍵一覽')
        a.setShortcut(QKeySequence('F1'))
        a.triggered.connect(lambda: show_shortcuts(self))
        self.help_menu.addAction('開放原始碼授權…', lambda: show_licenses(self))
        from .common import DONATE_URL
        if DONATE_URL:
            self.help_menu.addSeparator()
            self.help_menu.addAction(glyph_icon(G.HEART, '#ff7aa8'), f'贊助 {APP_TITLE}…', lambda: show_donate(self))
        self.help_menu.addAction('關於', lambda: show_about(self))
        self.settings_menu = QMenu('設定(&S)', self)
        self.act_settings = self.settings_menu.addAction(glyph_icon(G.SETTINGS), '顯示與字體大小…')
        self.act_settings.setShortcut(QKeySequence('Ctrl+,'))
        self.act_settings.triggered.connect(self.open_settings)
        self.act_exit = QAction('結束', self)
        self.act_exit.setShortcut(QKeySequence('Ctrl+Q'))
        self.act_exit.triggered.connect(self.close)
        self.addAction(self.act_exit)

        geo = self.settings.get('window/geometry')
        if geo is not None:
            try:
                self.restoreGeometry(geo)
            except TypeError:
                pass

        self._scale_icons(self)
        self._start(start_path, start_mode)

    @property
    def edit(self):
        if self._edit is None:
            from .editor import EditPage
            self._edit = EditPage(self.settings)
            self.stack.addWidget(self._edit)
            self._edit.finished.connect(self._edit_finished)
            self._edit.saved.connect(self._edit_saved)
            self._edit.stitchRequested.connect(lambda p: self.manage.open_stitch([p], os.path.dirname(p)))
            self._scale_icons(self._edit)
        return self._edit

    # ------------------------------------------------------------------ building
    def _build_modebar(self):
        bar = QWidget()
        bar.setObjectName('ModeBar')
        h = QHBoxLayout(bar)
        h.setContentsMargins(0, 0, 8, 0)
        h.setSpacing(0)
        title = QLabel(APP_TITLE)
        title.setObjectName('AppTitle')
        h.addWidget(title)
        h.addStretch(1)
        self.mode_group = QButtonGroup(self)
        self.mode_group.setExclusive(True)
        self.mode_buttons = {}
        for key, text, glyph in (('manage', '管理', G.GRID), ('view', '檢視', G.PHOTO), ('edit', '編輯', G.EDIT)):
            b = QPushButton(glyph_icon(glyph), ' ' + text)
            b.setCheckable(True)
            b.setFocusPolicy(Qt.NoFocus)
            b.clicked.connect(lambda _=False, k=key: self._mode_clicked(k))
            self.mode_group.addButton(b)
            self.mode_buttons[key] = b
            h.addWidget(b)
        from .common import DONATE_URL
        if DONATE_URL:
            heart = QPushButton(glyph_icon(G.HEART, '#ff7aa8'), '')
            heart.setObjectName('DonateButton')
            heart.setToolTip(f'贊助 {APP_TITLE}（自願小額贊助）')
            heart.setFocusPolicy(Qt.NoFocus)
            heart.clicked.connect(lambda: show_donate(self))
            h.addWidget(heart)
        gear = QPushButton(glyph_icon(G.SETTINGS), '')
        gear.setToolTip('設定：字體大小（Ctrl+,）')
        gear.setFocusPolicy(Qt.NoFocus)
        gear.clicked.connect(self.open_settings)
        h.addWidget(gear)
        return bar

    def _start(self, start_path, start_mode=None):
        start_path = os.path.abspath(start_path) if start_path else None
        if start_path and os.path.isfile(start_path) and is_image(start_path):
            self.manage.navigate(os.path.dirname(start_path), select=start_path)
            if start_mode == 'manage':
                self.set_mode('manage')
            elif start_mode == 'edit':
                self.set_mode('manage')
                QTimer.singleShot(0, lambda p=start_path: self.open_editor(p))
            else:
                self.view.open_path(start_path)
                self.set_mode('view')
            return
        folder = start_path if start_path and os.path.isdir(start_path) else None
        if folder is None:
            last = self.settings.get('manage/last_folder')
            if last and os.path.isdir(last):
                folder = last
            else:
                folder = QStandardPaths.writableLocation(QStandardPaths.PicturesLocation) or os.path.expanduser('~')
        self.manage.navigate(folder)
        self.set_mode('manage')

    # ------------------------------------------------------------------ modes
    def set_mode(self, mode):
        if mode != 'view' and self.mode == 'view':
            self.view.leave()
        self.mode = mode
        page = self.manage if mode == 'manage' else self.view if mode == 'view' else self.edit
        self.stack.setCurrentWidget(page)
        self.mode_buttons[mode].setChecked(True)
        mb = self.menuBar()
        mb.clear()
        for m in page.menus:
            mb.addMenu(m)
        mb.addMenu(self.settings_menu)
        mb.addMenu(self.help_menu)
        if mode == 'manage':
            QTimer.singleShot(0, self.manage.focus_view)
            self.setWindowTitle(f"{self.manage.folder} - {APP_TITLE}" if self.manage.folder else APP_TITLE)
        elif mode == 'view':
            QTimer.singleShot(0, self.view.canvas.setFocus)
            cur = self.view.current_path()
            self.setWindowTitle(f"{os.path.basename(cur)} - {APP_TITLE}" if cur else APP_TITLE)
        else:
            QTimer.singleShot(0, self.edit.canvas.setFocus)
            self.setWindowTitle(f"編輯：{os.path.basename(self.edit.path or '')} - {APP_TITLE}")

    def _mode_clicked(self, mode):
        if mode == self.mode:
            return
        if self.mode == 'edit':
            if not self.edit.confirm_leave():
                self.mode_buttons['edit'].setChecked(True)
                return
            path = self.edit.path
            self.edit.unload()
            if mode == 'manage':
                self.back_to_manage(path)
            else:
                self._show_in_viewer(path)
            return
        if mode == 'manage':
            self.back_to_manage(self.view.current_path() if self.mode == 'view' else None)
        elif mode == 'view':
            cur = self.manage.current_image()
            imgs = self.manage.image_list()
            if not imgs:
                self.mode_buttons[self.mode].setChecked(True)
                QMessageBox.information(self, '檢視', '此資料夾沒有影像。')
                return
            if cur is None:
                cur = imgs[0]
            idx = next((i for i, p in enumerate(imgs) if norm(p) == norm(cur)), 0)
            self.open_viewer(imgs, idx)
        elif mode == 'edit':
            path = self.view.current_path() if self.mode == 'view' else self.manage.current_image()
            if not path:
                self.mode_buttons[self.mode].setChecked(True)
                QMessageBox.information(self, '編輯', '請先選取一張影像。')
                return
            self.open_editor(path)

    def open_viewer(self, files, index):
        self.view.open_files(files, index)
        self.set_mode('view')

    def _show_in_viewer(self, path):
        if path and any(norm(f) == norm(path) for f in self.view.files):
            i = next(i for i, f in enumerate(self.view.files) if norm(f) == norm(path))
            self.view.on_external_change(path)
            self.view.show_index(i)
        elif path:
            self.view.open_path(path)
        self.set_mode('view')

    def back_to_manage(self, path=None):
        if self.isFullScreen():
            self._set_fullscreen(False)
        if path:
            folder = os.path.dirname(path)
            if not self.manage.folder or norm(folder) != norm(self.manage.folder):
                self.manage.navigate(folder, select=path)
            else:
                self.manage.select_path(path)
        self.set_mode('manage')

    def open_editor(self, path):
        if not path:
            return
        if self.mode == 'edit':
            if not self.edit.confirm_leave():
                return
        ret = self.mode if self.mode in ('manage', 'view') else self._edit_return
        if self.mode == 'view':
            self.view.leave()
        if self.edit.load(path):
            self._edit_return = ret
            self.set_mode('edit')

    def _edit_finished(self, path):
        if self._edit_return == 'view' and path:
            self._show_in_viewer(path)
        else:
            self.back_to_manage(path or None)

    def _edit_saved(self, path):
        self.thumbs.invalidate(path)
        self.manage.on_external_change(path)
        self.view.on_external_change(path)

    # ------------------------------------------------------------------ settings
    @staticmethod
    def _scale_icons(root):
        from PySide6.QtWidgets import QApplication
        from .theme import scale_icons
        scale_icons(root, QApplication.instance().font().pointSizeF())

    def open_settings(self):
        SettingsDialog(self.settings, self.apply_font_size, self).exec()

    def apply_font_size(self, pt):
        from PySide6.QtWidgets import QApplication
        from .theme import set_font_size
        pt = set_font_size(QApplication.instance(), pt)
        self._scale_icons(self)          # toolbar / mode-bar / list icons follow the font size
        self.manage.refresh_layout()
        self.view.refresh_layout()

    # ------------------------------------------------------------------ full screen
    def _set_fullscreen(self, on):
        if on:
            if not self.isFullScreen():
                self._was_maximized = self.isMaximized()
            self.modebar.hide()
            self.menuBar().hide()
            self.showFullScreen()
        else:
            self.modebar.show()
            self.menuBar().show()
            if self.isFullScreen():
                if self._was_maximized:
                    self.showMaximized()
                else:
                    self.showNormal()
            if self.view._fullscreen:
                self.view.set_fullscreen(False)

    # ------------------------------------------------------------------ closing
    def closeEvent(self, ev):
        if self.mode == 'edit' and not self.edit.confirm_leave():
            ev.ignore()
            return
        if self.isFullScreen():
            self._set_fullscreen(False)
        self.settings.set('window/geometry', self.saveGeometry())
        self.settings.sync()
        self.thumbs.cancel_pending()
        self.view.loader.clear()
        if self._edit is not None:
            self._edit.shutdown()
        ev.accept()
