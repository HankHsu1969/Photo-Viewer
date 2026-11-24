"""Dialogs: rename, batch rename, batch resize/convert, save options, help."""
from __future__ import annotations

import os
import time

from PySide6.QtCore import Qt, Signal, QSize, QRectF
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QLineEdit,
                               QSpinBox, QComboBox, QDialogButtonBox, QTableWidget, QTableWidgetItem,
                               QHeaderView, QPushButton, QFileDialog, QCheckBox, QProgressDialog,
                               QMessageBox, QApplication, QRadioButton, QButtonGroup, QToolButton)

from . import __version__
from .common import APP_TITLE, unique_path


class ColorButton(QToolButton):
    """Colour swatch button; click to choose a colour."""
    colorChanged = Signal(str)

    def __init__(self, color='#ffffff', title='選擇顏色', parent=None):
        super().__init__(parent)
        self._color = QColor(color).name()
        self._title = title
        self.setToolTip(title)
        self.setIconSize(QSize(30, 16))
        self.clicked.connect(self._pick)
        self._refresh()

    def color(self) -> str:
        return self._color

    def setColor(self, c):
        self._color = QColor(c).name()
        self._refresh()

    def _refresh(self):
        pm = QPixmap(60, 32)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QPen(QColor('#8a8a90'), 2))
        p.setBrush(QColor(self._color))
        p.drawRoundedRect(QRectF(1, 1, 58, 30), 6, 6)
        p.end()
        self.setIcon(QIcon(pm))

    def _pick(self):
        from PySide6.QtWidgets import QColorDialog
        c = QColorDialog.getColor(QColor(self._color), self, self._title)
        if c.isValid():
            self.setColor(c.name())
            self.colorChanged.emit(self._color)


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


class ResizeDialog(QDialog):
    """Output size of the edited image.

    value() is None (keep the size), {'long': px} (aspect ratio kept, so it follows later crops and
    rotations) or {'w': px, 'h': px} (exact size, may stretch).
    """
    PRESETS = [('3840（4K）', 3840), ('2560', 2560), ('1920（Full HD）', 1920), ('1600', 1600), ('1280', 1280),
               ('1080（社群貼文）', 1080), ('1024', 1024), ('800', 800), ('640', 640)]

    def __init__(self, base, current=None, parent=None):
        from PySide6.QtWidgets import QDoubleSpinBox
        super().__init__(parent)
        self.setWindowTitle('調整影像尺寸')
        self.setMinimumWidth(440)
        self.bw, self.bh = max(1, base[0]), max(1, base[1])
        self._busy = False
        v = QVBoxLayout(self)
        v.addWidget(QLabel(f'目前尺寸（旋轉、裁切後）：<b>{self.bw} × {self.bh}</b> px'))
        form = QFormLayout()
        self.w = QSpinBox()
        self.h = QSpinBox()
        for sp in (self.w, self.h):
            sp.setRange(1, 30000)
            sp.setSuffix(' px')
            sp.setKeyboardTracking(True)
        self.pct = QDoubleSpinBox()
        self.pct.setRange(1.0, 1000.0)
        self.pct.setDecimals(1)
        self.pct.setSuffix(' %')
        self.lock = QCheckBox('保持長寬比')
        form.addRow('寬度：', self.w)
        form.addRow('高度：', self.h)
        form.addRow('比例：', self.pct)
        form.addRow('', self.lock)
        quick = QHBoxLayout()
        for pc in (25, 50, 75, 100, 200):
            b = QPushButton(f'{pc}%')
            b.clicked.connect(lambda _=False, pc=pc: self._set_pct(pc))
            quick.addWidget(b)
        quick.addStretch(1)
        form.addRow('快速：', quick)
        self.preset = QComboBox()
        self.preset.addItem('選擇長邊尺寸…')
        for label, _ in self.PRESETS:
            self.preset.addItem(label)
        self.preset.activated.connect(self._preset_chosen)
        form.addRow('常用長邊：', self.preset)
        v.addLayout(form)
        self.out_lbl = QLabel()
        self.out_lbl.setWordWrap(True)
        v.addWidget(self.out_lbl)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel | QDialogButtonBox.Reset)
        bb.button(QDialogButtonBox.Ok).setText('套用')
        bb.button(QDialogButtonBox.Reset).setText('還原原始尺寸')
        bb.button(QDialogButtonBox.Reset).clicked.connect(lambda: self._set_size(self.bw, self.bh))
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)

        from .imageops import resize_target
        cw, ch = resize_target(self.bw, self.bh, current) or (self.bw, self.bh)
        self.lock.setChecked(not current or 'long' in current)
        self._set_size(cw, ch)
        self.w.valueChanged.connect(lambda _v: self._edited('w'))
        self.h.valueChanged.connect(lambda _v: self._edited('h'))
        self.pct.valueChanged.connect(lambda _v: self._edited('pct'))
        self.lock.toggled.connect(lambda on: on and self._edited('w'))
        self.w.setFocus()
        self.w.selectAll()

    def _set_size(self, w, h):
        self._busy = True
        self.w.setValue(int(w))
        self.h.setValue(int(h))
        self.pct.setValue(round(w / self.bw * 100.0, 1))
        self._busy = False
        self._update_label()

    def _set_pct(self, pc):
        self._set_size(max(1, round(self.bw * pc / 100.0)), max(1, round(self.bh * pc / 100.0)))

    def _preset_chosen(self, idx):
        if idx <= 0:
            return
        long_side = self.PRESETS[idx - 1][1]
        s = long_side / float(max(self.bw, self.bh))
        self.lock.setChecked(True)
        self._set_size(max(1, round(self.bw * s)), max(1, round(self.bh * s)))
        self.preset.setCurrentIndex(0)

    def _edited(self, which):
        if self._busy:
            return
        self._busy = True
        if which == 'pct':
            s = self.pct.value() / 100.0
            self.w.setValue(max(1, round(self.bw * s)))
            self.h.setValue(max(1, round(self.bh * s)))
        elif self.lock.isChecked():
            if which == 'w':
                self.h.setValue(max(1, round(self.w.value() * self.bh / self.bw)))
            else:
                self.w.setValue(max(1, round(self.h.value() * self.bw / self.bh)))
            self.pct.setValue(round(self.w.value() / self.bw * 100.0, 1))
        else:
            self.pct.setValue(round(self.w.value() / self.bw * 100.0, 1))
        self._busy = False
        self._update_label()

    def _update_label(self):
        w, h = self.w.value(), self.h.value()
        mp = w * h / 1e6
        txt = f'輸出尺寸：<b>{w} × {h}</b> px（約 {mp:.1f} 百萬像素）'
        if w > self.bw or h > self.bh:
            txt += '<br><span style="color:#ffb347">放大影像會讓畫質變得較模糊。</span>'
        if not self.lock.isChecked() and abs(w / h - self.bw / self.bh) > 0.01:
            txt += '<br><span style="color:#ffb347">長寬比與原圖不同，影像會被拉伸。</span>'
        self.out_lbl.setText(txt)

    def value(self):
        w, h = self.w.value(), self.h.value()
        if (w, h) == (self.bw, self.bh):
            return None
        if self.lock.isChecked():
            return {'long': max(w, h)}
        return {'w': w, 'h': h}


class SettingsDialog(QDialog):
    """Preferences. Font size changes are previewed live on the whole app; Cancel restores the old size."""
    PRESETS = [('小', 8.5), ('標準', 9.5), ('大', 11.0), ('特大', 13.0)]

    def __init__(self, settings, apply_font, parent=None):
        from PySide6.QtCore import QTimer
        from PySide6.QtWidgets import QSlider, QGroupBox
        from .theme import DEFAULT_FONT_PT, MIN_FONT_PT, MAX_FONT_PT
        super().__init__(parent)
        self.settings = settings
        self.apply_font = apply_font
        self.default_pt = DEFAULT_FONT_PT
        self.orig_pt = settings.get('ui/font_size', DEFAULT_FONT_PT, float)
        self.pt = self.orig_pt
        self.setWindowTitle('設定')
        self.setMinimumWidth(460)
        v = QVBoxLayout(self)

        grp = QGroupBox('顯示')
        g = QVBoxLayout(grp)
        row = QHBoxLayout()
        row.addWidget(QLabel('字體大小'))
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(int(MIN_FONT_PT * 2), int(MAX_FONT_PT * 2))  # 0.5 pt steps
        self.slider.setValue(int(round(self.orig_pt * 2)))
        row.addWidget(self.slider, 1)
        self.value_lbl = QLabel()
        self.value_lbl.setMinimumWidth(60)
        row.addWidget(self.value_lbl)
        g.addLayout(row)
        presets = QHBoxLayout()
        for name, pt in self.PRESETS:
            b = QPushButton(name)
            b.clicked.connect(lambda _=False, pt=pt: self.slider.setValue(int(round(pt * 2))))
            presets.addWidget(b)
        presets.addStretch(1)
        g.addLayout(presets)
        self.preview = QLabel('預覽：Kirapix 相片管理與修圖　Kirapix Quick 快速看圖　ABC abc 123')
        self.preview.setWordWrap(True)
        g.addWidget(self.preview)
        note = QLabel('變更會立即套用到 Kirapix 的所有畫面；Kirapix Quick 的資訊文字會在下次開啟時套用。')
        note.setObjectName('Hint')
        note.setWordWrap(True)
        g.addWidget(note)
        v.addWidget(grp)

        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel | QDialogButtonBox.RestoreDefaults)
        bb.button(QDialogButtonBox.RestoreDefaults).setText('還原預設')
        bb.button(QDialogButtonBox.RestoreDefaults).clicked.connect(
            lambda: self.slider.setValue(int(round(self.default_pt * 2))))
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)

        # restyling the whole app is not free: apply shortly after the slider stops moving
        self._apply_timer = QTimer(self)
        self._apply_timer.setSingleShot(True)
        self._apply_timer.setInterval(180)
        self._apply_timer.timeout.connect(lambda: self.apply_font(self.pt))
        self.slider.valueChanged.connect(self._changed)
        self._update_label()

    def _update_label(self):
        self.value_lbl.setText(f'{self.pt:g} pt')

    def _changed(self, v):
        self.pt = v / 2.0
        self._update_label()
        self._apply_timer.start()

    def accept(self):
        self._apply_timer.stop()
        self.apply_font(self.pt)
        self.settings.set('ui/font_size', self.pt)
        self.settings.sync()
        super().accept()

    def reject(self):
        self._apply_timer.stop()
        if self.pt != self.orig_pt:
            self.apply_font(self.orig_pt)
        super().reject()


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
<tr><td><b>拖曳縮圖到資料夾</b></td><td>移動（同一磁碟）；按住 Ctrl 複製、Shift 移動</td></tr>
<tr><td><b>工具列「拼接」/ 右鍵「拼接圖片」</b></td><td>把選取的圖片往下、往右或往左接成一張大圖（可再加入其他圖片）</td></tr>
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
<h3>設定</h3>
<table cellspacing=4>
<tr><td><b>Ctrl+,</b> 或右上角齒輪</td><td>設定字體大小（立即預覽）</td></tr>
</table>
<h3>編輯模式</h3>
<table cellspacing=4>
<tr><td><b>Ctrl+S</b></td><td>儲存　　<b>Ctrl+Shift+S</b> 另存新檔</td></tr>
<tr><td><b>Ctrl+Z / Ctrl+Y</b></td><td>復原 / 取消復原</td></tr>
<tr><td><b>按住 \\ 或「比較」按鈕</b></td><td>顯示原圖</td></tr>
<tr><td><b>雙擊滑桿</b></td><td>重設該項數值</td></tr>
<tr><td><b>C</b></td><td>裁切（Enter 套用、Esc 取消）</td></tr>
<tr><td><b>Ctrl+R</b></td><td>調整影像尺寸</td></tr>
<tr><td><b>T</b></td><td>文字：點一下影像新增；拖曳移動、拖曳右下角縮放</td></tr>
<tr><td><b>方向鍵 / Delete</b></td><td>文字：微調位置（Shift 加大）/ 刪除</td></tr>
<tr><td><b>工具列「拼接」</b></td><td>以這張為第一張，加入其他圖片拼接成大圖</td></tr>
</table>
"""


def show_shortcuts(parent):
    box = QMessageBox(parent)
    box.setWindowTitle('快速鍵一覽')
    box.setTextFormat(Qt.RichText)
    box.setText(SHORTCUTS_HTML)
    box.exec()


def show_about(parent):
    from .common import DONATE_URL
    donate = ('<p>Kirapix 免費使用；如果喜歡，歡迎從「說明 &gt; 贊助 Kirapix」小額支持。</p>' if DONATE_URL else '')
    QMessageBox.about(parent, '關於', f'<h3>{APP_TITLE}</h3><p>版本 {__version__}</p>'
                      '<p>快速看圖、相片管理與影像編輯工具；雙擊圖片則由 Kirapix Quick 快速開啟。</p>'
                      + donate +
                      '<p>使用開放原始碼元件：Qt / PySide6（LGPL v3）、Python、NumPy、Pillow。<br>'
                      '授權條文請見「說明 &gt; 開放原始碼授權」。</p>')


def show_donate(parent):
    """Voluntary donation: explain first (free app, unlocks nothing, paid via the named service), then open
    the donation page in the browser only if the user chooses to."""
    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QDesktopServices
    from .common import DONATE_URL, DONATE_PROVIDER, app_icon_image
    if not DONATE_URL:
        return False
    box = QMessageBox(parent)
    box.setStyleSheet('QLabel#qt_msgbox_informativelabel { min-width: 27em; }')
    box.setWindowTitle(f'贊助 {APP_TITLE}')
    box.setIconPixmap(QPixmap.fromImage(app_icon_image(64)))
    box.setText(f'<h3>喜歡 {APP_TITLE} 嗎？</h3>')
    provider = f'<b>{DONATE_PROVIDER}</b>' if DONATE_PROVIDER else '贊助頁面'
    box.setInformativeText(
        f'{APP_TITLE} 免費使用，沒有廣告，也不收集任何資料。<br>'
        f'如果它幫上你的忙，歡迎透過 {provider} 小額贊助，支持持續開發。<br><br>'
        '<span style="color:#9a9aa0">贊助完全自願，不會解鎖任何功能。按「前往贊助頁面」會用瀏覽器開啟贊助網站，'
        '付款由該服務處理，本程式不會經手任何付款資料。</span>')
    go = box.addButton('前往贊助頁面', QMessageBox.AcceptRole)
    box.addButton('以後再說', QMessageBox.RejectRole)
    box.setDefaultButton(go)
    box.exec()
    if box.clickedButton() is go:
        QDesktopServices.openUrl(QUrl(DONATE_URL))
        return True
    return False


def licenses_dir():
    """licenses/ next to the executables (installed / portable) or at the repository root (source)."""
    import sys
    if getattr(sys, 'frozen', False):
        base = os.path.dirname(sys.executable)
    else:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, 'licenses')


class LicensesDialog(QDialog):
    """Third-party notices (licenses/THIRD-PARTY-NOTICES.txt) with a button to open the full license texts."""

    def __init__(self, parent=None):
        from PySide6.QtWidgets import QPlainTextEdit
        super().__init__(parent)
        self.setWindowTitle('開放原始碼授權')
        self.resize(760, 560)
        self.folder = licenses_dir()
        v = QVBoxLayout(self)
        v.addWidget(QLabel(f'{APP_TITLE} 使用下列開放原始碼元件。完整授權條文在程式資料夾的 licenses 資料夾中。'))
        text = QPlainTextEdit()
        text.setReadOnly(True)
        text.setLineWrapMode(QPlainTextEdit.WidgetWidth)
        path = os.path.join(self.folder, 'THIRD-PARTY-NOTICES.txt')
        try:
            with open(path, encoding='utf-8-sig') as f:
                text.setPlainText(f.read())
        except OSError:
            text.setPlainText('找不到授權說明檔案：\n' + path + '\n\n'
                              '本程式使用 Qt / PySide6（LGPL v3）、Python（PSF License）、NumPy（BSD）、'
                              'Pillow（MIT-CMU）與 PyInstaller（GPL，附 bootloader 例外條款）。')
        v.addWidget(text, 1)
        bb = QDialogButtonBox(QDialogButtonBox.Close)
        bb.button(QDialogButtonBox.Close).setText('關閉')
        self.open_btn = bb.addButton('開啟授權檔案資料夾', QDialogButtonBox.ActionRole)
        self.open_btn.setEnabled(os.path.isdir(self.folder))
        self.open_btn.clicked.connect(lambda: os.startfile(self.folder))
        bb.rejected.connect(self.reject)
        v.addWidget(bb)


def show_licenses(parent):
    LicensesDialog(parent).exec()
