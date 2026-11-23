"""Stitch several images into one big image: down (top to bottom), right (left to right) or left (right to left)."""
from __future__ import annotations

import os
import time

from PySide6.QtCore import Qt, QRectF, QSize
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QListWidget,
                               QListWidgetItem, QPushButton, QToolButton, QButtonGroup, QComboBox, QSpinBox,
                               QCheckBox, QLineEdit, QFileDialog, QMessageBox, QProgressDialog, QApplication,
                               QWidget, QAbstractItemView, QSizePolicy, QDialogButtonBox)

from .common import G, glyph_icon, read_qimage, oriented_size
from .dialogs import ColorButton

DIRECTIONS = [  # key, label, glyph, tooltip
    ('down', '往下接', G.ARROW_DOWN, '第一張在最上面，其餘依序往下接'),
    ('right', '往右接', G.ARROW_RIGHT, '第一張在最左邊，其餘依序往右接'),
    ('left', '往左接', G.ARROW_LEFT, '第一張在最右邊，其餘依序往左接'),
]
FITS = ['min', 'max', 'none']
JPEG_MAX = 65500


def plan_layout(sizes, direction, fit='min', gap=0, border=False):
    """Place images of the given (w, h) sizes in a row or column.

    direction: 'down' | 'right' | 'left'.  fit: 'min' / 'max' scales every image to the smallest /
    largest width (down) or height (right, left); 'none' keeps the sizes and centres them.
    Returns (W, H, [(index, x, y, w, h), ...]).
    """
    n = len(sizes)
    if not n:
        return 0, 0, []
    vertical = direction == 'down'
    ref = [w if vertical else h for w, h in sizes]
    target = min(ref) if fit == 'min' else max(ref)
    scaled = []
    for w, h in sizes:
        if fit == 'none':
            scaled.append((w, h))
        elif vertical:
            scaled.append((target, max(1, round(h * target / float(w)))))
        else:
            scaled.append((max(1, round(w * target / float(h))), target))
    order = list(range(n))
    if direction == 'left':
        order.reverse()                      # the first image ends up on the right
    b = gap if border else 0
    cross = max((w if vertical else h) for w, h in scaled)
    pos = b
    placed = []
    for i in order:
        w, h = scaled[i]
        if vertical:
            placed.append((i, b + (cross - w) // 2, pos, w, h))
            pos += h + gap
        else:
            placed.append((i, pos, b + (cross - h) // 2, w, h))
            pos += w + gap
    length = pos - gap + b
    W, H = (cross + 2 * b, length) if vertical else (length, cross + 2 * b)
    return W, H, sorted(placed, key=lambda t: t[0])


def _image_size(path):
    s = oriented_size(path)
    if s.isValid() and s.width() > 0:
        return s.width(), s.height()
    try:
        from PIL import Image, ImageOps
        with Image.open(path) as im:
            return ImageOps.exif_transpose(im).size
    except Exception:
        return None


class _Preview(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(260, 200)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.layout_ = (0, 0, [])
        self.thumbs = {}
        self.bg = QColor('#ffffff')

    def paintEvent(self, ev):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(24, 24, 26))
        W, H, placed = self.layout_
        if not W or not H:
            p.end()
            return
        s = min((self.width() - 16) / W, (self.height() - 16) / H)
        ox, oy = (self.width() - W * s) / 2.0, (self.height() - H * s) / 2.0
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        p.fillRect(QRectF(ox, oy, W * s, H * s), self.bg)
        for i, x, y, w, h in placed:
            r = QRectF(ox + x * s, oy + y * s, w * s, h * s)
            img = self.thumbs.get(i)
            if img is not None and not img.isNull():
                p.drawImage(r, img)
            else:
                p.fillRect(r, QColor(90, 90, 96))
        p.end()


class StitchDialog(QDialog):
    def __init__(self, paths, folder, settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.output = None
        self.open_after = False
        self.setWindowTitle(f'拼接圖片（{len(paths)} 張）')
        self.resize(980, 640)
        self._sizes = {}
        self._thumbs = {}
        root = QHBoxLayout(self)

        # ---- order
        left = QVBoxLayout()
        left.addWidget(QLabel('順序（可拖曳調整）'))
        self.list = QListWidget()
        self.list.setIconSize(QSize(56, 56))
        self.list.setDragDropMode(QAbstractItemView.InternalMove)
        self.list.setDefaultDropAction(Qt.MoveAction)
        self.list.setMinimumWidth(240)
        self._folder = folder or (os.path.dirname(paths[0]) if paths else '')
        self._add_paths(paths)
        self.list.model().rowsMoved.connect(lambda *_: self._update())
        left.addWidget(self.list, 1)
        add = QPushButton(glyph_icon(G.ADD), ' 加入圖片…')
        add.setToolTip('從任何資料夾加入更多圖片')
        add.clicked.connect(self._add_files)
        left.addWidget(add)
        row = QHBoxLayout()
        for text, fn in (('上移', lambda: self._move(-1)), ('下移', lambda: self._move(1)),
                         ('反轉', self._reverse), ('移除', self._remove)):
            b = QPushButton(text)
            b.clicked.connect(fn)
            row.addWidget(b)
        left.addLayout(row)
        root.addLayout(left, 0)

        # ---- options + preview
        right = QVBoxLayout()
        right.addWidget(QLabel('拼接方向'))
        drow = QHBoxLayout()
        self.dir_group = QButtonGroup(self)
        self._dir_btns = {}
        last_dir = settings.get('stitch/direction', 'down')
        for key, text, glyph, tip in DIRECTIONS:
            b = QToolButton()
            b.setText(text)
            b.setIcon(glyph_icon(glyph))
            b.setIconSize(QSize(26, 26))
            b.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
            b.setCheckable(True)
            b.setToolTip(tip)
            b.setMinimumWidth(92)
            b.setChecked(key == last_dir)
            b.toggled.connect(lambda on: on and self._direction_changed())
            self.dir_group.addButton(b)
            self._dir_btns[key] = b
            drow.addWidget(b)
        drow.addStretch(1)
        right.addLayout(drow)
        self.dir_hint = QLabel()
        self.dir_hint.setObjectName('Hint')
        right.addWidget(self.dir_hint)

        form = QFormLayout()
        self.fit = QComboBox()
        self.fit.currentIndexChanged.connect(lambda _i: self._update())
        form.addRow('尺寸：', self.fit)
        grow = QHBoxLayout()
        self.gap = QSpinBox()
        self.gap.setRange(0, 2000)
        self.gap.setSuffix(' px')
        self.gap.setValue(settings.get('stitch/gap', 0, int))
        self.gap.valueChanged.connect(lambda _v: self._update())
        self.border = QCheckBox('四周也留同樣寬度')
        self.border.setChecked(settings.get('stitch/border', False, bool))
        self.border.toggled.connect(lambda _on: self._update())
        grow.addWidget(self.gap)
        grow.addWidget(self.border)
        grow.addStretch(1)
        form.addRow('間距：', grow)
        self.bg = ColorButton(settings.get('stitch/bg', '#ffffff', str), '間距與底色')
        self.bg.colorChanged.connect(lambda _c: self._update())
        form.addRow('底色：', self.bg)
        right.addLayout(form)

        self.preview = _Preview()
        self.preview.thumbs = {}
        right.addWidget(self.preview, 1)
        self.info = QLabel()
        right.addWidget(self.info)

        oform = QFormLayout()
        frow = QHBoxLayout()
        self.fmt = QComboBox()
        self.fmt.addItems(['JPEG (.jpg)', 'PNG (.png)'])
        self.fmt.setCurrentIndex(1 if settings.get('stitch/fmt', 'jpg', str) == 'png' else 0)
        self.fmt.currentIndexChanged.connect(self._fmt_changed)
        self.quality = QSpinBox()
        self.quality.setRange(1, 100)
        self.quality.setValue(settings.get('save/quality', 92, int))
        self.quality.setPrefix('品質 ')
        frow.addWidget(self.fmt)
        frow.addWidget(self.quality)
        frow.addStretch(1)
        oform.addRow('格式：', frow)
        orow = QHBoxLayout()
        ext = '.png' if self.fmt.currentIndex() == 1 else '.jpg'
        self.out = QLineEdit(os.path.join(self._folder or os.path.expanduser('~'),
                                          time.strftime('拼接_%Y%m%d_%H%M%S') + ext))
        b = QPushButton('瀏覽…')
        b.clicked.connect(self._browse)
        orow.addWidget(self.out, 1)
        orow.addWidget(b)
        oform.addRow('儲存到：', orow)
        self.open_edit = QCheckBox('完成後開啟編輯（可再裁切、調整尺寸或加上文字）')
        self.open_edit.setChecked(settings.get('stitch/open_edit', False, bool))
        oform.addRow('', self.open_edit)
        right.addLayout(oform)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText('開始拼接')
        bb.accepted.connect(self._run)
        bb.rejected.connect(self.reject)
        self.ok_btn = bb.button(QDialogButtonBox.Ok)
        right.addWidget(bb)
        root.addLayout(right, 1)

        self._direction_changed()
        self._fmt_changed()

    # ------------------------------------------------------------------ state
    def direction(self):
        return next((k for k, b in self._dir_btns.items() if b.isChecked()), 'down')

    def paths(self):
        return [self.list.item(i).data(Qt.UserRole) for i in range(self.list.count())]

    def plan(self):
        paths = self.paths()
        sizes = [self._sizes[p] for p in paths]
        return plan_layout(sizes, self.direction(), FITS[max(0, self.fit.currentIndex())], self.gap.value(),
                           self.border.isChecked())

    def _add_paths(self, paths):
        bad = []
        for p in paths:
            size = self._sizes.get(p) or _image_size(p)
            if size is None:
                bad.append(os.path.basename(p))
                continue
            self._sizes[p] = size
            if p not in self._thumbs:
                self._thumbs[p] = read_qimage(p, 240)
            th = self._thumbs[p]
            it = QListWidgetItem(os.path.basename(p))
            it.setData(Qt.UserRole, p)
            it.setToolTip(f'{p}\n{size[0]} × {size[1]} px')
            if not th.isNull():
                it.setIcon(QIcon(QPixmap.fromImage(th)))
            self.list.addItem(it)
        if bad:
            QMessageBox.warning(self, '拼接圖片', '無法讀取：\n' + '\n'.join(bad[:15]))

    def _add_files(self):
        from .common import IMAGE_EXTS
        pats = ' '.join('*' + e for e in sorted(IMAGE_EXTS))
        cur = self.paths()
        start = os.path.dirname(cur[-1]) if cur else self._folder
        fns, _ = QFileDialog.getOpenFileNames(self, '加入圖片', start, f'圖片 ({pats});;所有檔案 (*)')
        if fns:
            self._add_paths(fns)
            self.list.setCurrentRow(self.list.count() - 1)
            self._update()

    def _direction_changed(self):
        d = self.direction()
        dim = '寬度' if d == 'down' else '高度'
        idx = max(0, self.fit.currentIndex()) if self.fit.count() else self.settings.get('stitch/fit', 0, int)
        self.fit.blockSignals(True)
        self.fit.clear()
        self.fit.addItems([f'縮放成相同{dim}（以最小的為準）', f'縮放成相同{dim}（以最大的為準）', '保持原尺寸（置中對齊）'])
        self.fit.setCurrentIndex(min(idx, 2))
        self.fit.blockSignals(False)
        self.dir_hint.setText(next(t for k, _, _, t in DIRECTIONS if k == d) + '。')
        self._update()

    def _fmt_changed(self, *_):
        png = self.fmt.currentIndex() == 1
        self.quality.setEnabled(not png)
        stem, ext = os.path.splitext(self.out.text().strip())
        if ext.lower() in ('.jpg', '.jpeg', '.png', ''):
            self.out.setText(stem + ('.png' if png else '.jpg'))
        self._update()

    def _update(self):
        W, H, placed = self.plan()
        paths = self.paths()
        self.preview.layout_ = (W, H, placed)
        self.preview.thumbs = {i: self._thumbs.get(p) for i, p in enumerate(paths)}
        self.preview.bg = QColor(self.bg.color())
        self.preview.update()
        n = len(paths)
        self.setWindowTitle(f'拼接圖片（{n} 張）')
        if n < 2:
            self.info.setText('<span style="color:#ffb347">至少需要兩張圖片：按左下角「加入圖片…」加入，'
                              '或在管理畫面按住 Ctrl 先選取多張再拼接。</span>')
        else:
            txt = f'{n} 張 → 輸出尺寸：<b>{W} × {H}</b> px（約 {W * H / 1e6:.1f} 百萬像素）'
            if self.fmt.currentIndex() == 0 and max(W, H) > JPEG_MAX:
                txt += f'<br><span style="color:#ff6b6b">超過 JPEG 的上限 {JPEG_MAX} px，請改用 PNG 或選擇「以最小的為準」。</span>'
            self.info.setText(txt)
        self.ok_btn.setEnabled(n >= 2)

    def _move(self, d):
        r = self.list.currentRow()
        if r < 0 or not (0 <= r + d < self.list.count()):
            return
        it = self.list.takeItem(r)
        self.list.insertItem(r + d, it)
        self.list.setCurrentRow(r + d)
        self._update()

    def _reverse(self):
        items = [self.list.takeItem(0) for _ in range(self.list.count())]
        for it in reversed(items):
            self.list.addItem(it)
        self._update()

    def _remove(self):
        r = self.list.currentRow()
        if r >= 0:
            self.list.takeItem(r)
            self._update()

    def _browse(self):
        png = self.fmt.currentIndex() == 1
        fn, _ = QFileDialog.getSaveFileName(self, '儲存拼接圖片', self.out.text(),
                                            'PNG (*.png)' if png else 'JPEG (*.jpg *.jpeg)')
        if fn:
            self.out.setText(fn)

    # ------------------------------------------------------------------ run
    def _run(self):
        paths = self.paths()
        if len(paths) < 2:
            return
        W, H, placed = self.plan()
        png = self.fmt.currentIndex() == 1
        if not png and max(W, H) > JPEG_MAX:
            QMessageBox.warning(self, '拼接圖片', f'輸出尺寸 {W} × {H} 超過 JPEG 的上限（{JPEG_MAX} px）。\n'
                                              '請改用 PNG，或選擇「以最小的為準」。')
            return
        if W * H > 250_000_000 and QMessageBox.question(
                self, '拼接圖片', f'輸出影像非常大（{W} × {H}，約 {W * H / 1e6:.0f} 百萬像素），'
                                 '可能需要大量記憶體與時間。要繼續嗎？') != QMessageBox.Yes:
            return
        out = self.out.text().strip().strip('"')
        if not out:
            return
        ext = os.path.splitext(out)[1].lower()
        want = ('.png',) if png else ('.jpg', '.jpeg')
        if ext not in want:
            out += want[0]
        if os.path.exists(out) and QMessageBox.question(
                self, '拼接圖片', f'「{os.path.basename(out)}」已存在，要覆寫嗎？') != QMessageBox.Yes:
            return
        os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)

        from PIL import Image, ImageOps
        from .imageops import save_image
        bg = QColor(self.bg.color())
        canvas = Image.new('RGB', (W, H), (bg.red(), bg.green(), bg.blue()))
        prog = QProgressDialog('正在拼接…', '取消', 0, len(placed) + 1, self)
        prog.setWindowTitle('拼接圖片')
        prog.setWindowModality(Qt.WindowModal)
        prog.setMinimumDuration(0)
        try:
            for k, (i, x, y, w, h) in enumerate(placed):
                prog.setValue(k)
                prog.setLabelText(f'正在處理：{os.path.basename(paths[i])}')
                QApplication.processEvents()
                if prog.wasCanceled():
                    return
                with Image.open(paths[i]) as src:
                    src.load()
                    im = ImageOps.exif_transpose(src)
                    if im is src:
                        im = src.copy()
                if im.mode in ('RGBA', 'LA', 'PA') or (im.mode == 'P' and 'transparency' in im.info):
                    im = im.convert('RGBA')
                else:
                    im = im.convert('RGB')
                if im.size != (w, h):
                    im = im.resize((w, h), Image.Resampling.LANCZOS)
                canvas.paste(im, (x, y), im if im.mode == 'RGBA' else None)
                del im
            prog.setLabelText('正在儲存…')
            prog.setValue(len(placed))
            QApplication.processEvents()
            save_image(canvas, out, quality=self.quality.value())
        except Exception as e:  # noqa: BLE001
            prog.close()
            QMessageBox.warning(self, '拼接圖片', f'拼接失敗：{e}')
            return
        finally:
            prog.close()
        self.settings.set('stitch/direction', self.direction())
        self.settings.set('stitch/fit', self.fit.currentIndex())
        self.settings.set('stitch/gap', self.gap.value())
        self.settings.set('stitch/border', self.border.isChecked())
        self.settings.set('stitch/bg', self.bg.color())
        self.settings.set('stitch/fmt', 'png' if png else 'jpg')
        self.settings.set('stitch/open_edit', self.open_edit.isChecked())
        if not png:
            self.settings.set('save/quality', self.quality.value())
        self.output = out
        self.open_after = self.open_edit.isChecked()
        self.accept()
