"""Dialogs: rename, batch rename, batch resize/convert, save options, help."""
from __future__ import annotations

import os
import time

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QLineEdit,
                               QSpinBox, QComboBox, QDialogButtonBox, QTableWidget, QTableWidgetItem,
                               QHeaderView, QPushButton, QFileDialog, QCheckBox, QProgressDialog,
                               QMessageBox, QApplication, QRadioButton, QButtonGroup)

from . import __version__
from .common import APP_TITLE, unique_path


class RenameDialog(QDialog):
    def __init__(self, name, parent=None):
        super().__init__(parent)
        self.setWindowTitle('重新命名')
        self.setMinimumWidth(420)
        v = QVBoxLayout(self)
        v.addWidget(QLabel('新名稱：'))
        self.edit = QLineEdit(name)
        stem = os.path.splitext(name)[0]
        self.edit.setSelection(0, len(stem))
        v.addWidget(self.edit)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)

    def value(self):
        return self.edit.text().strip()


class BatchRenameDialog(QDialog):
    """Template based batch rename. ``#`` = sequence digit, {name} = original name, {date} = file date."""

    def __init__(self, paths, parent=None):
        super().__init__(parent)
        self.paths = list(paths)
        self.result_pairs = []
        self.setWindowTitle(f'批次重新命名（{len(self.paths)} 個檔案）')
        self.resize(640, 480)
        v = QVBoxLayout(self)
        form = QFormLayout()
        self.tpl = QLineEdit('IMG_###')
        self.start = QSpinBox()
        self.start.setRange(0, 999999)
        self.start.setValue(1)
        self.case = QComboBox()
        self.case.addItems(['副檔名保持不變', '副檔名轉小寫', '副檔名轉大寫'])
        form.addRow('命名範本：', self.tpl)
        form.addRow('', QLabel('<span style="color:#999"># 代表序號位數，{name} 原檔名，{date} 檔案日期 (yyyymmdd)</span>'))
        form.addRow('起始編號：', self.start)
        form.addRow('副檔名：', self.case)
        v.addLayout(form)
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(['原名稱', '新名稱'])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        v.addWidget(self.table, 1)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText('重新命名')
        bb.accepted.connect(self._apply)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)
        self.tpl.textChanged.connect(self._preview)
        self.start.valueChanged.connect(self._preview)
        self.case.currentIndexChanged.connect(self._preview)
        self._preview()

    def _new_names(self):
        tpl = self.tpl.text() or '###'
        n0 = self.start.value()
        out = []
        for i, p in enumerate(self.paths):
            stem, ext = os.path.splitext(os.path.basename(p))
            if self.case.currentIndex() == 1:
                ext = ext.lower()
            elif self.case.currentIndex() == 2:
                ext = ext.upper()
            s = tpl.replace('{name}', stem)
            if '{date}' in s:
                try:
                    s = s.replace('{date}', time.strftime('%Y%m%d', time.localtime(os.path.getmtime(p))))
                except OSError:
                    s = s.replace('{date}', '')
            if '#' in s:
                start = s.index('#')
                end = start
                while end < len(s) and s[end] == '#':
                    end += 1
                s = s[:start] + str(n0 + i).zfill(end - start) + s[end:]
            out.append(s + ext)
        return out

    def _preview(self):
        names = self._new_names()
        self.table.setRowCount(len(self.paths))
        for i, (p, n) in enumerate(zip(self.paths, names)):
            self.table.setItem(i, 0, QTableWidgetItem(os.path.basename(p)))
            self.table.setItem(i, 1, QTableWidgetItem(n))

    def _apply(self):
        names = self._new_names()
        if len(set(n.lower() for n in names)) != len(names):
            QMessageBox.warning(self, '批次重新命名', '新名稱有重複，請在範本中加入 # 序號。')
            return
        folder_sets = {}
        for p, n in zip(self.paths, names):
            folder_sets.setdefault(os.path.dirname(p), []).append((p, n))
        targets = {os.path.normcase(os.path.join(os.path.dirname(p), n)) for p, n in zip(self.paths, names)}
        sources = {os.path.normcase(p) for p in self.paths}
        for t in targets:
            if os.path.exists(t) and t not in sources:
                QMessageBox.warning(self, '批次重新命名', f'目標檔案已存在：\n{t}')
                return
        temps = []
        try:
            for i, p in enumerate(self.paths):
                tmp = os.path.join(os.path.dirname(p), f'.~pvrename_{i}_{os.getpid()}')
                os.rename(p, tmp)
                temps.append((p, tmp))
            for (p, tmp), n in zip(temps, names):
                dst = os.path.join(os.path.dirname(p), n)
                os.rename(tmp, dst)
                self.result_pairs.append((p, dst))
        except OSError as e:
            done = {old for old, _ in self.result_pairs}
            for p, tmp in temps:
                if p not in done and os.path.exists(tmp):
                    try:
                        os.rename(tmp, p)
                    except OSError:
                        pass
            QMessageBox.warning(self, '批次重新命名', f'重新命名失敗：{e}')
        self.accept()


class BatchResizeDialog(QDialog):
    FORMATS = [('保持原格式', None), ('JPEG (.jpg)', '.jpg'), ('PNG (.png)', '.png'), ('WEBP (.webp)', '.webp'),
               ('TIFF (.tif)', '.tif')]

    def __init__(self, paths, settings, parent=None):
        super().__init__(parent)
        self.paths = list(paths)
        self.settings = settings
        self.outputs = []
        self.setWindowTitle(f'批次調整大小／轉換格式（{len(self.paths)} 個檔案）')
        self.setMinimumWidth(480)
        v = QVBoxLayout(self)
        form = QFormLayout()
        mode_row = QHBoxLayout()
        self.rb_long = QRadioButton('長邊像素')
        self.rb_pct = QRadioButton('百分比')
        self.rb_keep = QRadioButton('不調整大小')
        self.rb_long.setChecked(True)
        grp = QButtonGroup(self)
        for rb in (self.rb_long, self.rb_pct, self.rb_keep):
            grp.addButton(rb)
            mode_row.addWidget(rb)
        mode_row.addStretch(1)
        form.addRow('調整方式：', mode_row)
        self.size = QSpinBox()
        self.size.setRange(16, 20000)
        self.size.setValue(settings.get('batch/long', 1920, int))
        self.size.setSuffix(' px')
        self.pct = QSpinBox()
        self.pct.setRange(1, 400)
        self.pct.setValue(50)
        self.pct.setSuffix(' %')
        form.addRow('長邊：', self.size)
        form.addRow('比例：', self.pct)
        self.upscale = QCheckBox('允許放大較小的影像')
        form.addRow('', self.upscale)
        self.fmt = QComboBox()
        for label, _ in self.FORMATS:
            self.fmt.addItem(label)
        form.addRow('輸出格式：', self.fmt)
        self.quality = QSpinBox()
        self.quality.setRange(1, 100)
        self.quality.setValue(settings.get('save/quality', 90, int))
        form.addRow('JPEG/WEBP 品質：', self.quality)
        out_row = QHBoxLayout()
        base = os.path.dirname(self.paths[0]) if self.paths else ''
        self.out = QLineEdit(os.path.join(base, 'resized'))
        b = QPushButton('瀏覽…')
        b.clicked.connect(self._browse)
        out_row.addWidget(self.out, 1)
        out_row.addWidget(b)
        form.addRow('輸出資料夾：', out_row)
        self.keep_exif = QCheckBox('保留 EXIF 資訊')
        self.keep_exif.setChecked(True)
        form.addRow('', self.keep_exif)
        v.addLayout(form)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText('開始')
        bb.accepted.connect(self._run)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)

    def _browse(self):
        d = QFileDialog.getExistingDirectory(self, '選擇輸出資料夾', self.out.text())
        if d:
            self.out.setText(d)

    def _run(self):
        from PIL import Image, ImageOps
        from .imageops import save_image
        out_dir = self.out.text().strip()
        if not out_dir:
            return
        os.makedirs(out_dir, exist_ok=True)
        self.settings.set('batch/long', self.size.value())
        fmt_ext = self.FORMATS[self.fmt.currentIndex()][1]
        prog = QProgressDialog('正在處理…', '取消', 0, len(self.paths), self)
        prog.setWindowTitle('批次處理')
        prog.setWindowModality(Qt.WindowModal)
        prog.setMinimumDuration(0)
        errors = []
        for i, p in enumerate(self.paths):
            prog.setValue(i)
            prog.setLabelText(f'正在處理：{os.path.basename(p)}')
            QApplication.processEvents()
            if prog.wasCanceled():
                break
            try:
                with Image.open(p) as im:
                    im.load()
                    exif = im.getexif() if self.keep_exif.isChecked() else None
                    icc = im.info.get('icc_profile')
                    im = ImageOps.exif_transpose(im)
                if im.mode not in ('RGB', 'RGBA'):
                    im = im.convert('RGBA' if 'A' in im.getbands() or 'transparency' in im.info else 'RGB')
                w, h = im.size
                if self.rb_long.isChecked():
                    s = self.size.value() / float(max(w, h))
                elif self.rb_pct.isChecked():
                    s = self.pct.value() / 100.0
                else:
                    s = 1.0
                if s > 1.0 and not self.upscale.isChecked():
                    s = 1.0
                if abs(s - 1.0) > 1e-6:
                    im = im.resize((max(1, round(w * s)), max(1, round(h * s))), Image.Resampling.LANCZOS)
                stem, ext = os.path.splitext(os.path.basename(p))
                ext = fmt_ext or ext.lower()
                if ext in ('.gif', '.ico', '.tga', '.ppm', '.pgm', '.pbm'):
                    ext = '.png'
                dst = unique_path(out_dir, stem + ext)
                save_image(im, dst, exif=exif, icc=icc, quality=self.quality.value())
                self.outputs.append(dst)
            except Exception as e:  # noqa: BLE001
                errors.append(f'{os.path.basename(p)}：{e}')
        prog.setValue(len(self.paths))
        if errors:
            QMessageBox.warning(self, '批次處理', '部分檔案處理失敗：\n' + '\n'.join(errors[:15]))
        else:
            QMessageBox.information(self, '批次處理', f'完成！已輸出 {len(self.outputs)} 個檔案到：\n{out_dir}')
        self.accept()


class SaveOptionsDialog(QDialog):
    def __init__(self, target, size, settings, parent=None):
        super().__init__(parent)
        self.setWindowTitle('儲存選項')
        self.settings = settings
        ext = os.path.splitext(target)[1].lower()
        v = QVBoxLayout(self)
        v.addWidget(QLabel(f'儲存到：<b>{os.path.basename(target)}</b>　（{size[0]} × {size[1]}）'))
        form = QFormLayout()
        self.quality = QSpinBox()
        self.quality.setRange(1, 100)
        self.quality.setValue(settings.get('save/quality', 92, int))
        self.quality.setEnabled(ext in ('.jpg', '.jpeg', '.jpe', '.jfif', '.webp'))
        form.addRow('品質 (1-100)：', self.quality)
        self.resize_cb = QCheckBox('調整大小，長邊為')
        self.long = QSpinBox()
        self.long.setRange(16, 30000)
        self.long.setValue(min(max(size), settings.get('save/long', 2048, int)))
        self.long.setSuffix(' px')
        row = QHBoxLayout()
        row.addWidget(self.resize_cb)
        row.addWidget(self.long)
        row.addStretch(1)
        form.addRow('', row)
        v.addLayout(form)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText('儲存')
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)

    def values(self):
        self.settings.set('save/quality', self.quality.value())
        if self.resize_cb.isChecked():
            self.settings.set('save/long', self.long.value())
        return self.quality.value(), (self.long.value() if self.resize_cb.isChecked() else 0)


SHORTCUTS_HTML = """
<h3>管理模式</h3>
<table cellspacing=4>
<tr><td><b>雙擊 / Enter</b></td><td>以檢視模式開啟影像（資料夾則進入）</td></tr>
<tr><td><b>Ctrl+E</b></td><td>編輯選取的影像</td></tr>
<tr><td><b>Delete</b></td><td>移到資源回收筒</td></tr>
<tr><td><b>F2</b></td><td>重新命名</td></tr>
<tr><td><b>Ctrl+0~5</b></td><td>設定星等評等</td></tr>
<tr><td><b>Backspace / Alt+↑</b></td><td>上一層資料夾</td></tr>
<tr><td><b>Alt+← / Alt+→</b></td><td>上一頁 / 下一頁</td></tr>
<tr><td><b>Ctrl+滾輪</b></td><td>調整縮圖大小</td></tr>
<tr><td><b>F5</b></td><td>重新整理</td></tr>
</table>
<h3>檢視模式</h3>
<table cellspacing=4>
<tr><td><b>← / →</b></td><td>上一張 / 下一張</td></tr>
<tr><td><b>滾輪、空白鍵、PgUp/PgDn</b></td><td>上一張 / 下一張</td></tr>
<tr><td><b>Home / End</b></td><td>第一張 / 最後一張</td></tr>
<tr><td><b>雙擊影像 / Enter / Esc</b></td><td>回到管理模式</td></tr>
<tr><td><b>Ctrl+滾輪、+ / -</b></td><td>縮放</td></tr>
<tr><td><b>0 或 *</b>、<b>1 或 /</b></td><td>符合視窗、實際大小</td></tr>
<tr><td><b>F / F11</b></td><td>全螢幕</td></tr>
<tr><td><b>S</b></td><td>投影片播放</td></tr>
<tr><td><b>I</b></td><td>顯示影像資訊 / EXIF</td></tr>
<tr><td><b>[ / ]</b></td><td>向左 / 向右旋轉（JPEG 無損）</td></tr>
<tr><td><b>Ctrl+E</b></td><td>編輯影像</td></tr>
<tr><td><b>Ctrl+C</b></td><td>複製影像</td></tr>
</table>
<h3>編輯模式</h3>
<table cellspacing=4>
<tr><td><b>Ctrl+S</b></td><td>儲存　　<b>Ctrl+Shift+S</b> 另存新檔</td></tr>
<tr><td><b>Ctrl+Z / Ctrl+Y</b></td><td>復原 / 取消復原</td></tr>
<tr><td><b>按住 \\ 或「比較」按鈕</b></td><td>顯示原圖</td></tr>
<tr><td><b>雙擊滑桿</b></td><td>重設該項數值</td></tr>
<tr><td><b>Enter / Esc</b></td><td>裁切時：套用 / 取消</td></tr>
</table>
"""


def show_shortcuts(parent):
    box = QMessageBox(parent)
    box.setWindowTitle('快速鍵一覽')
    box.setTextFormat(Qt.RichText)
    box.setText(SHORTCUTS_HTML)
    box.exec()


def show_about(parent):
    QMessageBox.about(parent, '關於', f'<h3>{APP_TITLE}</h3><p>版本 {__version__}</p>'
                      '<p>仿 ACDSee 操作方式的快速看圖、相片管理與影像編輯工具。</p>'
                      '<p>Python · PySide6 (Qt) · NumPy · Pillow</p>')
