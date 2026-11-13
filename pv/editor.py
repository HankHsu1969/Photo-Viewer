"""Edit mode: non-destructive lighting / colour / detail / geometry adjustments with live preview."""
from __future__ import annotations

import copy
import json
import os
import shutil
import threading
import time
import traceback

import numpy as np
from PIL import Image, ImageOps
from PySide6.QtCore import Qt, Signal, QThread, QTimer, QSize, QEventLoop
from PySide6.QtGui import QAction, QKeySequence, QGuiApplication
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QToolBar, QLabel, QSplitter, QScrollArea,
                               QComboBox, QPushButton, QToolButton, QTabWidget, QCheckBox, QRadioButton,
                               QButtonGroup, QSpinBox, QDoubleSpinBox, QMessageBox, QFileDialog, QDialog,
                               QProgressDialog, QMenu, QSizePolicy, QAbstractSpinBox, QGridLayout)

from .canvas import EditCanvas
from .common import (G, glyph_icon, array_to_qimage, compose_orientation, ORIENT_OPS, cache_dir,
                     WRITABLE_EXTS, ext_of, norm)
from .dialogs import SaveOptionsDialog
from .editwidgets import ParamSlider, Section, HistogramWidget, CurvesWidget, LevelsWidget, hex_hsv
from .imageops import (default_params, merge_params, DEFAULTS, GEOMETRY_KEYS, PreviewEngine, render_full,
                       save_image, transform_rect, auto_levels, auto_contrast, straighten_scale, histogram,
                       to_uint8, process, HSL_NAMES, HSL_CENTERS, BW_NAMES, BW_CENTERS, CHANNELS)

PRESETS = {
    '鮮豔': {'vibrance': 35, 'saturation': 8, 'contrast': 12, 'clarity': 12},
    '柔和': {'contrast': -18, 'highlights': -25, 'shadows': 20, 'saturation': -12, 'clarity': -15},
    '高對比': {'contrast': 40, 'clarity': 25, 'blacks': -15, 'whites': 12, 'vibrance': 10},
    '亮部陰影平衡': {'highlights': -45, 'shadows': 45, 'clarity': 10, 'vibrance': 10},
    '暖色調': {'temperature': 28, 'tint': 4, 'vibrance': 10},
    '冷色調': {'temperature': -28, 'tint': -3, 'vibrance': 8},
    '電影感': {'contrast': 18, 'highlights': -20, 'saturation': -12, 'split_hi_hue': 40, 'split_hi_sat': 28,
            'split_sh_hue': 190, 'split_sh_sat': 32, 'split_balance': 10, 'vignette_amount': -22},
    '復古懷舊': {'contrast': -10, 'saturation': -30, 'split_hi_hue': 42, 'split_hi_sat': 35, 'split_sh_hue': 25,
             'split_sh_sat': 18, 'vignette_amount': -35, 'grain': 18, 'levels': {'rgb': [0, 1.0, 255, 22, 240]}},
    '褪色底片': {'contrast': -12, 'saturation': -15, 'grain': 10,
             'curves': {'rgb': [[0, 32], [64, 66], [192, 196], [255, 238]]}},
    '黑白經典': {'bw': True, 'contrast': 22, 'clarity': 10, 'bw_mix': [10, 15, -5, -10, -20, 0]},
    '黑白高反差': {'bw': True, 'contrast': 50, 'clarity': 30, 'blacks': -20, 'bw_mix': [20, 25, -10, -20, -40, 0]},
    '棕褐色調': {'bw': True, 'contrast': 10, 'split_hi_hue': 38, 'split_hi_sat': 40, 'split_sh_hue': 30,
             'split_sh_sat': 45, 'vignette_amount': -20},
}

ASPECTS = [('自由比例', None), ('原始比例', 'orig'), ('1:1 正方形', 1.0), ('4:3', 4 / 3), ('3:2', 1.5),
           ('16:9', 16 / 9), ('5:4', 1.25), ('3:4（直）', 0.75), ('2:3（直）', 2 / 3), ('9:16（直）', 9 / 16)]

CH_KEYS = ['rgb', 'r', 'g', 'b']
CH_LABELS = ['RGB', '紅', '綠', '藍']


# --------------------------------------------------------------------------- workers
class RenderWorker(QThread):
    rendered = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cond = threading.Condition()
        self._job = None
        self._quit = False

    def submit(self, fn):
        with self._cond:
            self._job = fn
            self._cond.notify()

    def stop(self):
        with self._cond:
            self._quit = True
            self._cond.notify()
        self.wait(3000)

    def run(self):
        while True:
            with self._cond:
                while self._job is None and not self._quit:
                    self._cond.wait()
                if self._quit:
                    return
                fn, self._job = self._job, None
            try:
                res = fn()
            except Exception:  # noqa: BLE001
                traceback.print_exc()
                continue
            self.rendered.emit(res)


class SaveWorker(QThread):
    done = Signal(bool, str)

    def __init__(self, full, params, alpha, target, exif, icc, quality, resize_long, parent=None):
        super().__init__(parent)
        self.args = (full, params, alpha, target, exif, icc, quality, resize_long)

    def run(self):
        full, params, alpha, target, exif, icc, quality, resize_long = self.args
        try:
            res = render_full(full, params, alpha, resize_long)
            save_image(res, target, exif, icc, quality)
            self.done.emit(True, target)
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            self.done.emit(False, str(e))


# --------------------------------------------------------------------------- page
class EditPage(QWidget):
    finished = Signal(str)
    saved = Signal(str)

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.path = None
        self.engine = None
        self.src_exif = None
        self.src_icc = None
        self.alpha = None
        self.params = default_params()
        self._saved_params = default_params()
        self.history = []
        self.hist_idx = -1
        self.crop_mode = False
        self._session = 0
        self._job = 0
        self._last_qimg = None
        self._comparing = False
        self._backed_up = set()
        self._sliders = {}
        self._cb_range = 'midtones'
        self._lv_ch = 'rgb'

        self.worker = RenderWorker(self)
        self.worker.rendered.connect(self._on_rendered)
        self.worker.start()
        self._commit_timer = QTimer(self)
        self._commit_timer.setSingleShot(True)
        self._commit_timer.setInterval(350)
        self._commit_timer.timeout.connect(self._commit)
        self._full_timer = QTimer(self)
        self._full_timer.setSingleShot(True)
        self._full_timer.setInterval(200)
        self._full_timer.timeout.connect(lambda: self._render(fast=False))
        self._flash_timer = QTimer(self)
        self._flash_timer.setSingleShot(True)
        self._flash_timer.timeout.connect(lambda: self.st_msg.setText(''))

        self.canvas = EditCanvas(self)
        self.canvas.shrink_only = True
        self.canvas.clicked.connect(self._canvas_clicked)
        self.canvas.zoomChanged.connect(lambda _z: self._update_status())

        self._build_actions()
        self.toolbar = self._build_toolbar()
        panel = self._build_panel()

        split = QSplitter(Qt.Horizontal)
        split.addWidget(self.canvas)
        split.addWidget(panel)
        split.setStretchFactor(0, 1)
        split.setStretchFactor(1, 0)
        split.setChildrenCollapsible(False)
        split.setSizes([1100, 360])

        self.statusw = QWidget()
        self.statusw.setObjectName('StatusBar')
        sh = QHBoxLayout(self.statusw)
        sh.setContentsMargins(6, 3, 6, 3)
        self.st_name = QLabel()
        self.st_name.setStyleSheet('color:#e8e8e8; font-weight:600;')
        self.st_dims = QLabel()
        self.st_dirty = QLabel()
        self.st_dirty.setStyleSheet('color:#ffb347;')
        self.st_msg = QLabel()
        self.st_msg.setStyleSheet('color:#7fd17f;')
        self.st_zoom = QLabel()
        for w in (self.st_name, self.st_dims, self.st_dirty, self.st_msg):
            sh.addWidget(w)
        sh.addStretch(1)
        sh.addWidget(self.st_zoom)

        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        v.addWidget(self.toolbar)
        v.addWidget(split, 1)
        v.addWidget(self.statusw)

    # ================================================================== UI construction
    def _act(self, text, slot, shortcut=None, glyph=None, tip=None, mirror=False):
        a = QAction(text, self)
        if glyph:
            a.setIcon(glyph_icon(glyph, mirror=mirror))
        if shortcut:
            if isinstance(shortcut, (list, tuple)):
                a.setShortcuts([QKeySequence(s) for s in shortcut])
            else:
                a.setShortcut(QKeySequence(shortcut))
        sc = a.shortcut()
        a.setToolTip(tip or (text + (f"（{sc.toString(QKeySequence.NativeText)}）" if not sc.isEmpty() else '')))
        a.triggered.connect(slot)
        return a

    def _build_actions(self):
        A = self._act
        self.act_save = A('儲存', lambda: self.save(False), 'Ctrl+S', G.SAVE)
        self.act_save_as = A('另存新檔…', lambda: self.save(True), 'Ctrl+Shift+S', G.SAVE_AS)
        self.act_undo = A('復原', self.undo, 'Ctrl+Z', G.UNDO)
        self.act_redo = A('取消復原', self.redo, ['Ctrl+Y', 'Ctrl+Shift+Z'], G.REDO)
        self.act_reset = A('全部重設', self.reset_all, None, G.RESET, tip='清除所有調整')
        self.act_fit = A('符合視窗', self.canvas.fit, 'Ctrl+0', G.FIT)
        self.act_100 = A('100%', self.canvas.actual_size, 'Ctrl+1', G.ACTUAL)
        self.act_done = A('完成', self.done, None, G.CHECK, tip='完成編輯並返回')
        self.act_cancel = A('取消', self.cancel, None, G.CANCEL, tip='放棄未儲存的調整並返回')
        m_file = QMenu('檔案(&F)', self)
        m_file.addActions([self.act_save, self.act_save_as])
        m_file.addSeparator()
        m_file.addActions([self.act_done, self.act_cancel])
        m_edit = QMenu('編輯(&E)', self)
        m_edit.addActions([self.act_undo, self.act_redo])
        m_edit.addSeparator()
        m_edit.addAction(self.act_reset)
        m_view = QMenu('檢視(&V)', self)
        m_view.addActions([self.act_fit, self.act_100])
        self.menus = [m_file, m_edit, m_view]

    def _build_toolbar(self):
        tb = QToolBar()
        tb.setIconSize(QSize(18, 18))
        tb.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        tb.addActions([self.act_save, self.act_save_as])
        tb.addSeparator()
        tb.addActions([self.act_undo, self.act_redo, self.act_reset])
        tb.addSeparator()
        self.btn_compare = QToolButton()
        self.btn_compare.setText('比較原圖')
        self.btn_compare.setIcon(glyph_icon(G.COMPARE))
        self.btn_compare.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.btn_compare.setToolTip('按住以顯示原始影像（或按住 \\ 鍵）')
        self.btn_compare.pressed.connect(lambda: self._compare(True))
        self.btn_compare.released.connect(lambda: self._compare(False))
        tb.addWidget(self.btn_compare)
        tb.addActions([self.act_fit, self.act_100])
        tb.addSeparator()
        tb.addWidget(QLabel(' 預設集 '))
        self.preset_combo = QComboBox()
        self.preset_combo.addItem('選擇效果…')
        for name in PRESETS:
            self.preset_combo.addItem(name)
        self.preset_combo.activated.connect(self._preset_activated)
        tb.addWidget(self.preset_combo)
        b = QToolButton()
        b.setText('…')
        b.setToolTip('儲存／載入自訂預設集')
        b.setPopupMode(QToolButton.InstantPopup)
        pm = QMenu(b)
        pm.addAction('將目前調整儲存為預設集…', self._save_preset)
        pm.addAction('載入預設集檔案…', self._load_preset)
        b.setMenu(pm)
        tb.addWidget(b)
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        tb.addWidget(spacer)
        tb.addAction(self.act_cancel)
        tb.addAction(self.act_done)
        btn = tb.widgetForAction(self.act_done)
        if btn is not None:
            btn.setStyleSheet('QToolButton { background:#2f6fd1; border:1px solid #3794ff; color:white; padding:3px 12px; }'
                              'QToolButton:hover { background:#3a7ee0; }')
        return tb

    def _slider(self, key, label, lo, hi, dec=0, grad=None, idx=None):
        default = DEFAULTS[key] if idx is None else DEFAULTS[key][idx]
        s = ParamSlider(label, lo, hi, default, dec, grad)
        if idx is None:
            s.valueChanged.connect(lambda v, k=key: self._set(k, v))
            self._sliders[key] = s
        else:
            s.valueChanged.connect(lambda v, k=key, i=idx: self._set_idx(k, i, v))
            self._sliders[(key, idx)] = s
        return s

    @staticmethod
    def _box():
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setSpacing(3)
        return w, lay

    def _build_panel(self):
        panel = QWidget()
        panel.setMinimumWidth(340)
        panel.setMaximumWidth(480)
        pv = QVBoxLayout(panel)
        pv.setContentsMargins(0, 0, 0, 0)
        pv.setSpacing(0)
        t = QLabel('色階分佈圖')
        t.setObjectName('PanelTitle')
        pv.addWidget(t)
        self.histo = HistogramWidget()
        pv.addWidget(self.histo)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        inner = QWidget()
        iv = QVBoxLayout(inner)
        iv.setContentsMargins(0, 4, 0, 0)
        iv.setSpacing(0)

        # ---- exposure / lighting
        w, l = self._box()
        row = QHBoxLayout()
        b = QPushButton(glyph_icon(G.BRIGHTNESS), ' 自動調整光線')
        b.setToolTip('自動設定黑白點與中間調')
        b.clicked.connect(self._auto_tone)
        row.addWidget(b)
        row.addStretch(1)
        l.addLayout(row)
        light = [('exposure', '曝光 (EV)', -4, 4, 2, ['#000000', '#ffffff']), ('brightness', '亮度', -100, 100, 0, None),
                 ('contrast', '對比', -100, 100, 0, None), ('highlights', '亮部', -100, 100, 0, None),
                 ('shadows', '陰影', -100, 100, 0, None), ('whites', '白色', -100, 100, 0, None),
                 ('blacks', '黑色', -100, 100, 0, None), ('clarity', '清晰度', -100, 100, 0, None),
                 ('dehaze', '去霧', -100, 100, 0, None)]
        for key, label, lo, hi, dec, grad in light:
            l.addWidget(self._slider(key, label, lo, hi, dec, grad))
        iv.addWidget(Section('曝光／光線', w, True, lambda: self._reset_keys([k[0] for k in light])))

        # ---- levels
        w, l = self._box()
        row = QHBoxLayout()
        self.lv_combo = QComboBox()
        self.lv_combo.addItems(CH_LABELS)
        self.lv_combo.currentIndexChanged.connect(self._lv_channel)
        row.addWidget(QLabel('通道'))
        row.addWidget(self.lv_combo)
        row.addStretch(1)
        b1 = QPushButton('自動色階')
        b1.setToolTip('分別調整紅綠藍通道的黑白點（同時校正偏色）')
        b1.clicked.connect(self._auto_levels)
        b2 = QPushButton('自動對比')
        b2.clicked.connect(self._auto_contrast)
        row.addWidget(b1)
        row.addWidget(b2)
        l.addLayout(row)
        self.levels_widget = LevelsWidget()
        self.levels_widget.levelsChanged.connect(self._levels_changed)
        l.addWidget(self.levels_widget)
        g = QGridLayout()
        self.lv_spins = []
        specs = [('輸入黑點', 0, 253, 0), ('中間調 γ', 0.1, 9.99, 2), ('輸入白點', 2, 255, 0),
                 ('輸出黑點', 0, 254, 0), ('輸出白點', 1, 255, 0)]
        for i, (lab, lo, hi, dec) in enumerate(specs):
            sp = QDoubleSpinBox() if dec else QSpinBox()
            if dec:
                sp.setDecimals(dec)
                sp.setSingleStep(0.05)
            sp.setRange(lo, hi)
            sp.setKeyboardTracking(False)
            sp.setAlignment(Qt.AlignRight)
            sp.valueChanged.connect(lambda v, i=i: self._lv_spin(i, v))
            self.lv_spins.append(sp)
            r, c = (0, i) if i < 3 else (2, i - 3)
            lb = QLabel(lab)
            lb.setStyleSheet('color:#9a9aa0; font-size:8.5pt;')
            g.addWidget(lb, r, c)
            g.addWidget(sp, r + 1, c)
        l.addLayout(g)
        iv.addWidget(Section('色階', w, False, lambda: self._reset_keys(['levels'])))

        # ---- curves
        w, l = self._box()
        row = QHBoxLayout()
        self.cv_combo = QComboBox()
        self.cv_combo.addItems(CH_LABELS)
        self.cv_combo.currentIndexChanged.connect(lambda i: self.curves_widget.set_channel(CH_KEYS[i]))
        row.addWidget(QLabel('通道'))
        row.addWidget(self.cv_combo)
        row.addStretch(1)
        b = QPushButton('重設此通道')
        b.clicked.connect(self._reset_curve_channel)
        row.addWidget(b)
        l.addLayout(row)
        self.curves_widget = CurvesWidget()
        self.curves_widget.curvesChanged.connect(self._curves_changed)
        l.addWidget(self.curves_widget)
        hint = QLabel('點擊新增控制點並拖曳；右鍵點控制點可刪除')
        hint.setStyleSheet('color:#8a8a90; font-size:8.5pt;')
        l.addWidget(hint)
        iv.addWidget(Section('色調曲線', w, False, lambda: self._reset_keys(['curves'])))

        # ---- white balance & colour
        w, l = self._box()
        row = QHBoxLayout()
        self.btn_pick = QPushButton(glyph_icon(G.EYEDROPPER), ' 點選中性灰')
        self.btn_pick.setCheckable(True)
        self.btn_pick.setToolTip('點選影像中應為白色或灰色的區域，自動校正白平衡')
        self.btn_pick.toggled.connect(self._pick_toggled)
        row.addWidget(self.btn_pick)
        row.addStretch(1)
        l.addLayout(row)
        l.addWidget(self._slider('temperature', '色溫', -100, 100, 0, ['#3a78d8', '#d8d8d8', '#f2c12e']))
        l.addWidget(self._slider('tint', '色調', -100, 100, 0, ['#35b54a', '#d8d8d8', '#d23cc8']))
        l.addWidget(self._slider('vibrance', '鮮豔度', -100, 100, 0, ['#7a7a7a', '#d8d8d8', '#e8604c']))
        l.addWidget(self._slider('saturation', '飽和度', -100, 100, 0, ['#808080', '#ff3030']))
        iv.addWidget(Section('白平衡與飽和度', w, True,
                             lambda: self._reset_keys(['temperature', 'tint', 'vibrance', 'saturation'])))

        # ---- colour EQ (HSL)
        w, l = self._box()
        tabs = QTabWidget()
        for key, title in (('hsl_hue', '色相'), ('hsl_sat', '飽和度'), ('hsl_lum', '亮度')):
            page = QWidget()
            pl = QVBoxLayout(page)
            pl.setContentsMargins(4, 4, 4, 4)
            pl.setSpacing(1)
            for i, (name, c) in enumerate(zip(HSL_NAMES, HSL_CENTERS)):
                if key == 'hsl_hue':
                    grad = [hex_hsv(c - 30), hex_hsv(c), hex_hsv(c + 30)]
                elif key == 'hsl_sat':
                    grad = [hex_hsv(c, 0.0, 0.75), hex_hsv(c, 1.0, 1.0)]
                else:
                    grad = [hex_hsv(c, 1.0, 0.25), hex_hsv(c, 0.85, 1.0)]
                pl.addWidget(self._slider(key, name, -100, 100, 0, grad, idx=i))
            tabs.addTab(page, title)
        l.addWidget(tabs)
        iv.addWidget(Section('色彩 EQ（HSL）', w, False, lambda: self._reset_keys(['hsl_hue', 'hsl_sat', 'hsl_lum'])))

        # ---- colour balance
        w, l = self._box()
        row = QHBoxLayout()
        grp = QButtonGroup(self)
        for label, rng in (('陰影', 'shadows'), ('中間調', 'midtones'), ('亮部', 'highlights')):
            rb = QRadioButton(label)
            rb.setChecked(rng == 'midtones')
            rb.toggled.connect(lambda on, r=rng: on and self._cb_range_changed(r))
            grp.addButton(rb)
            row.addWidget(rb)
        row.addStretch(1)
        l.addLayout(row)
        self._cb_sliders = []
        for i, (lab, grad) in enumerate((('青色 ↔ 紅色', ['#00c8d8', '#d8d8d8', '#e03030']),
                                         ('洋紅 ↔ 綠色', ['#d030c8', '#d8d8d8', '#30c040']),
                                         ('黃色 ↔ 藍色', ['#e8d020', '#d8d8d8', '#3060e0']))):
            s = ParamSlider(lab, -100, 100, 0, 0, grad)
            s.valueChanged.connect(lambda v, i=i: self._cb_changed(i, v))
            self._cb_sliders.append(s)
            l.addWidget(s)
        self.cb_preserve = QCheckBox('保持明度')
        self.cb_preserve.setChecked(True)
        self.cb_preserve.toggled.connect(lambda on: self._set('cb_preserve', bool(on)))
        l.addWidget(self.cb_preserve)
        iv.addWidget(Section('色彩平衡', w, False,
                             lambda: self._reset_keys(['cb_shadows', 'cb_midtones', 'cb_highlights', 'cb_preserve'])))

        # ---- split toning
        w, l = self._box()
        rainbow = [hex_hsv(h) for h in range(0, 361, 45)]
        l.addWidget(self._slider('split_hi_hue', '亮部色相', 0, 360, 0, rainbow))
        l.addWidget(self._slider('split_hi_sat', '亮部飽和度', 0, 100, 0, ['#808080', '#f0c060']))
        l.addWidget(self._slider('split_balance', '平衡', -100, 100, 0, None))
        l.addWidget(self._slider('split_sh_hue', '陰影色相', 0, 360, 0, rainbow))
        l.addWidget(self._slider('split_sh_sat', '陰影飽和度', 0, 100, 0, ['#808080', '#4080f0']))
        iv.addWidget(Section('分離色調', w, False, lambda: self._reset_keys(
            ['split_hi_hue', 'split_hi_sat', 'split_sh_hue', 'split_sh_sat', 'split_balance'])))

        # ---- black & white
        w, l = self._box()
        self.bw_check = QCheckBox('轉換為黑白')
        self.bw_check.toggled.connect(lambda on: self._set('bw', bool(on)))
        l.addWidget(self.bw_check)
        for i, (name, c) in enumerate(zip(BW_NAMES, BW_CENTERS)):
            l.addWidget(self._slider('bw_mix', name, -100, 100, 0, [hex_hsv(c, 0.9, 0.2), hex_hsv(c, 0.8, 1.0)], idx=i))
        iv.addWidget(Section('黑白', w, False, lambda: self._reset_keys(['bw', 'bw_mix'])))

        # ---- detail
        w, l = self._box()
        l.addWidget(self._slider('sharpen_amount', '銳利化 數量', 0, 200))
        l.addWidget(self._slider('sharpen_radius', '銳利化 半徑', 0.3, 5.0, 1))
        l.addWidget(self._slider('noise_reduction', '雜訊消除', 0, 100))
        iv.addWidget(Section('細節', w, False,
                             lambda: self._reset_keys(['sharpen_amount', 'sharpen_radius', 'noise_reduction'])))

        # ---- geometry
        w, l = self._box()
        g = QGridLayout()
        for i, (txt, op, glyph, mir) in enumerate((('向左 90°', 'ccw', G.ROTATE, True), ('向右 90°', 'cw', G.ROTATE, False),
                                                    ('水平翻轉', 'flip_h', G.FLIP_H, False),
                                                    ('垂直翻轉', 'flip_v', G.FLIP_H, False))):
            bt = QPushButton(glyph_icon(glyph, mirror=mir), ' ' + txt)
            bt.clicked.connect(lambda _=False, op=op: self._orient(op))
            g.addWidget(bt, i // 2, i % 2)
        l.addLayout(g)
        l.addWidget(self._slider('straighten', '拉直（角度）', -45, 45, 1))
        crop_row = QHBoxLayout()
        self.btn_crop = QPushButton(glyph_icon(G.CROP), ' 裁切')
        self.btn_crop.setCheckable(True)
        self.btn_crop.toggled.connect(self._crop_toggled)
        self.aspect_combo = QComboBox()
        for label, _ in ASPECTS:
            self.aspect_combo.addItem(label)
        self.aspect_combo.currentIndexChanged.connect(self._aspect_changed)
        crop_row.addWidget(self.btn_crop)
        crop_row.addWidget(self.aspect_combo, 1)
        l.addLayout(crop_row)
        crop_row2 = QHBoxLayout()
        self.btn_crop_apply = QPushButton('套用裁切')
        self.btn_crop_apply.setObjectName('Primary')
        self.btn_crop_apply.clicked.connect(self._apply_crop)
        self.btn_crop_cancel = QPushButton('取消')
        self.btn_crop_cancel.clicked.connect(self._cancel_crop)
        self.btn_crop_clear = QPushButton('清除裁切')
        self.btn_crop_clear.clicked.connect(self._clear_crop)
        for bt in (self.btn_crop_apply, self.btn_crop_cancel, self.btn_crop_clear):
            crop_row2.addWidget(bt)
        l.addLayout(crop_row2)
        iv.addWidget(Section('幾何（旋轉／拉直／裁切）', w, False, lambda: self._reset_keys(list(GEOMETRY_KEYS))))

        # ---- effects
        w, l = self._box()
        l.addWidget(self._slider('vignette_amount', '暈影 數量', -100, 100, 0, ['#000000', '#808080', '#ffffff']))
        l.addWidget(self._slider('vignette_midpoint', '暈影 中點', 0, 100))
        l.addWidget(self._slider('vignette_feather', '暈影 羽化', 0, 100))
        l.addWidget(self._slider('grain', '底片顆粒', 0, 100))
        iv.addWidget(Section('特效', w, False, lambda: self._reset_keys(
            ['vignette_amount', 'vignette_midpoint', 'vignette_feather', 'grain'])))

        iv.addStretch(1)
        scroll.setWidget(inner)
        pv.addWidget(scroll, 1)
        self._update_crop_buttons()
        return panel

    # ================================================================== loading
    def _proxy_side(self):
        scr = self.screen() or QGuiApplication.primaryScreen()
        if scr is None:
            return 1600
        g = scr.size()
        side = int(max(g.width(), g.height()) * scr.devicePixelRatio() * 0.8)
        return max(1200, min(2200, side))

    def load(self, path) -> bool:
        try:
            with Image.open(path) as src:
                src.load()
                exif = src.getexif()
                icc = src.info.get('icc_profile')
                img = ImageOps.exif_transpose(src)
                if img is src:
                    img = src.copy()
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, '編輯', f'無法開啟影像：\n{e}')
            return False
        if img.mode == 'P' and 'transparency' in img.info:
            img = img.convert('RGBA')
        alpha = img.getchannel('A') if 'A' in img.getbands() else None
        rgb = img.convert('RGB')
        self._session += 1
        self.path = path
        self.src_exif = exif
        self.src_icc = icc
        self.alpha = alpha
        self.engine = PreviewEngine(rgb, self._proxy_side())
        self.canvas.px_scale = 1.0 / self.engine.scale
        self.params = default_params()
        self._saved_params = default_params()
        self.history = [copy.deepcopy(self.params)]
        self.hist_idx = 0
        self._last_qimg = None
        self._comparing = False
        if self.crop_mode:
            self.btn_crop.blockSignals(True)
            self.btn_crop.setChecked(False)
            self.btn_crop.blockSignals(False)
            self.crop_mode = False
            self.canvas.set_crop_mode(False)
        self.btn_pick.setChecked(False)
        self.preset_combo.setCurrentIndex(0)
        self.canvas.clear('正在處理…')
        self._sync_ui()
        self._render()
        self._update_history_actions()
        self._update_status()
        return True

    def unload(self):
        self._session += 1
        self.engine = None
        self.path = None
        self.alpha = None
        self._last_qimg = None
        self.canvas.clear('')

    def shutdown(self):
        self.worker.stop()

    # ================================================================== params plumbing
    def _set(self, key, value):
        if self.params.get(key) == value:
            return
        self.params[key] = value
        self._changed()

    def _set_idx(self, key, idx, value):
        if self.params[key][idx] == value:
            return
        self.params[key][idx] = value
        self._changed()

    def _changed(self):
        if self.engine is not None and self.engine.fast is not None:
            # quick low-res frame now, full-quality frame once the control rests
            self._render(fast=True)
            self._full_timer.start()
        else:
            self._render()
        self._commit_timer.start()
        self._update_status()

    def _reset_keys(self, keys):
        for k in keys:
            self.params[k] = copy.deepcopy(DEFAULTS[k])
        if 'crop' in keys and self.crop_mode:
            self._cancel_crop()
        self._sync_ui()
        self._changed()

    def reset_all(self):
        geo = {k: self.params[k] for k in GEOMETRY_KEYS}
        self.params = default_params()
        if QMessageBox.question(self, '全部重設', '是否同時重設旋轉與裁切？') != QMessageBox.Yes:
            self.params.update(copy.deepcopy(geo))
        self._sync_ui()
        self._changed()

    def _sync_ui(self):
        p = self.params
        for key, s in self._sliders.items():
            if isinstance(key, tuple):
                s.setValue(p[key[0]][key[1]])
            else:
                s.setValue(p[key])
        for i, s in enumerate(self._cb_sliders):
            s.setValue(p['cb_' + self._cb_range][i])
        for wdg, val in ((self.cb_preserve, p['cb_preserve']), (self.bw_check, p['bw'])):
            wdg.blockSignals(True)
            wdg.setChecked(bool(val))
            wdg.blockSignals(False)
        self.levels_widget.set_levels(p['levels'])
        self._sync_levels_spins()
        self.curves_widget.set_curves(p['curves'])
        self._update_crop_buttons()

    def is_dirty(self):
        return self.engine is not None and self.params != self._saved_params

    # ================================================================== render
    def _render(self, fast=False):
        if self.engine is None:
            return
        if not fast:
            self._full_timer.stop()
        self._job += 1
        p = copy.deepcopy(self.params)
        skip = self.crop_mode
        eng, sess, job = self.engine, self._session, self._job

        def work():
            u8, hist, was_fast = eng.render(p, skip, fast)
            logical = eng.logical_size(p, skip)
            pre_hist = None
            if not was_fast:
                pre = process(eng.base[::4, ::4], p, scale=eng.base_scale() / 4.0, stop_at='levels')
                pre_hist = histogram(to_uint8(pre))
            return sess, job, array_to_qimage(u8), hist, pre_hist, logical

        self.worker.submit(work)

    def _on_rendered(self, res):
        sess, job, qimg, hist, pre_hist, logical = res
        if sess != self._session:
            return
        if job != self._job and self.canvas.has_image():
            cw, ch = self.canvas.logical_size()
            if abs(cw - logical[0]) > 2 or abs(ch - logical[1]) > 2:
                return  # stale frame of a different geometry; a newer render is on its way
        self._last_qimg = (qimg, logical)
        if not self._comparing:
            self.canvas.set_image(qimg, keep_view=True, logical=logical)
        self.histo.set_data(hist)
        if pre_hist is not None:
            self.levels_widget.set_histogram(pre_hist)
            self.curves_widget.set_histogram(pre_hist)
        self._update_status()

    def _compare(self, on):
        if self.engine is None or self._last_qimg is None:
            return
        self._comparing = on
        if on:
            base = self.engine.base
            if base is not None:
                self.canvas.set_image(array_to_qimage(to_uint8(base)), keep_view=True)
            self.st_msg.setText('顯示原圖')
        else:
            qimg, logical = self._last_qimg
            self.canvas.set_image(qimg, keep_view=True, logical=logical)
            self.st_msg.setText('')

    # ================================================================== undo / redo
    def _commit(self):
        snap = copy.deepcopy(self.params)
        if self.history and self.history[self.hist_idx] == snap:
            return
        del self.history[self.hist_idx + 1:]
        self.history.append(snap)
        if len(self.history) > 100:
            self.history.pop(0)
        self.hist_idx = len(self.history) - 1
        self._update_history_actions()

    def _flush_commit(self):
        if self._commit_timer.isActive():
            self._commit_timer.stop()
            self._commit()

    def undo(self):
        self._flush_commit()
        if self.hist_idx > 0:
            self.hist_idx -= 1
            self._restore(self.history[self.hist_idx])

    def redo(self):
        self._flush_commit()
        if self.hist_idx < len(self.history) - 1:
            self.hist_idx += 1
            self._restore(self.history[self.hist_idx])

    def _restore(self, snap):
        if self.crop_mode:
            self._cancel_crop()
        self.params = copy.deepcopy(snap)
        self._sync_ui()
        self._render()
        self._update_history_actions()
        self._update_status()

    def _update_history_actions(self):
        self.act_undo.setEnabled(self.hist_idx > 0)
        self.act_redo.setEnabled(self.hist_idx < len(self.history) - 1)

    # ================================================================== levels / curves
    def _lv_channel(self, i):
        self._lv_ch = CH_KEYS[i]
        self.levels_widget.set_channel(self._lv_ch)
        self._sync_levels_spins()

    def _sync_levels_spins(self):
        lv = self.params['levels'][self._lv_ch]
        for sp, val in zip(self.lv_spins, lv):
            sp.blockSignals(True)
            sp.setValue(val)
            sp.blockSignals(False)

    def _lv_spin(self, i, v):
        lv = self.params['levels'][self._lv_ch]
        v = round(float(v), 2) if i == 1 else int(v)
        if i == 0:
            v = min(v, lv[2] - 2)
        elif i == 2:
            v = max(v, lv[0] + 2)
        elif i == 3:
            v = min(v, lv[4] - 1)
        elif i == 4:
            v = max(v, lv[3] + 1)
        lv[i] = v
        self.levels_widget.set_levels(self.params['levels'])
        self._sync_levels_spins()
        self._changed()

    def _levels_changed(self):
        self.params['levels'] = self.levels_widget.get_levels()
        self._sync_levels_spins()
        self._changed()

    def _curves_changed(self):
        self.params['curves'] = self.curves_widget.get_curves()
        self._changed()

    def _reset_curve_channel(self):
        ch = CH_KEYS[self.cv_combo.currentIndex()]
        self.params['curves'][ch] = copy.deepcopy(DEFAULTS['curves'][ch])
        self.curves_widget.set_curves(self.params['curves'])
        self._changed()

    def _pre_levels_image(self):
        p = copy.deepcopy(self.params)
        p['levels'] = copy.deepcopy(DEFAULTS['levels'])
        return self.engine.pre_levels(p)

    def _auto_levels(self):
        if self.engine is None:
            return
        res = auto_levels(self._pre_levels_image())
        self.params['levels'] = copy.deepcopy(DEFAULTS['levels'])
        self.params['levels'].update(res)
        self._sync_ui()
        self._changed()
        self.flash('已套用自動色階')

    def _auto_contrast(self):
        if self.engine is None:
            return
        self.params['levels'] = copy.deepcopy(DEFAULTS['levels'])
        self.params['levels']['rgb'] = auto_contrast(self._pre_levels_image())
        self._sync_ui()
        self._changed()
        self.flash('已套用自動對比')

    def _auto_tone(self):
        if self.engine is None:
            return
        self.params['levels'] = copy.deepcopy(DEFAULTS['levels'])
        self.params['levels']['rgb'] = auto_contrast(self._pre_levels_image())
        if self.params['vibrance'] == 0:
            self.params['vibrance'] = 12
        self._sync_ui()
        self._changed()
        self.flash('已自動調整光線')

    # ================================================================== colour balance
    def _cb_range_changed(self, rng):
        self._cb_range = rng
        for i, s in enumerate(self._cb_sliders):
            s.setValue(self.params['cb_' + rng][i])

    def _cb_changed(self, i, v):
        self._set_idx('cb_' + self._cb_range, i, v)

    # ================================================================== white balance picker
    def _pick_toggled(self, on):
        if on and self.crop_mode:
            self.btn_crop.setChecked(False)
        self.canvas.pick_mode = on
        self.canvas._update_cursor()
        if on:
            self.flash('請在影像上點選應為白色或灰色的位置', 4000)

    def _canvas_clicked(self, pt):
        if not self.canvas.pick_mode or self.engine is None or self.engine.base is None:
            return
        base = self.engine.base
        h, w = base.shape[:2]
        x, y = int(pt.x()), int(pt.y())
        if not (0 <= x < w and 0 <= y < h):
            return
        patch = base[max(0, y - 3):y + 4, max(0, x - 3):x + 4].reshape(-1, 3).mean(axis=0)
        r, g, b = (max(float(c), 1e-4) for c in patch)
        T = float(np.clip(100.0 * np.log2(b / r), -100, 100))
        M = float(np.clip(-200.0 * np.log2(np.sqrt(r * b) / g), -100, 100))
        self.params['temperature'] = int(round(T))
        self.params['tint'] = int(round(M))
        self._sync_ui()
        self._changed()
        self.btn_pick.setChecked(False)
        self.flash(f'白平衡：色溫 {int(round(T))}，色調 {int(round(M))}')

    # ================================================================== geometry
    def _orient(self, op):
        if self.crop_mode:
            self._cancel_crop()
        p = self.params
        p['orient'] = compose_orientation(p['orient'], op)
        if p['crop']:
            p['crop'] = transform_rect(p['crop'], ORIENT_OPS[op])
        if op in ('flip_h', 'flip_v'):
            p['straighten'] = -p['straighten']
        self._sync_ui()
        self._changed()

    def _crop_toggled(self, on):
        if self.engine is None:
            return
        if on:
            self.btn_pick.setChecked(False)
            self.crop_mode = True
            self.canvas.set_crop_mode(True, self.params['crop'] or [0.0, 0.0, 1.0, 1.0])
            self._render()
            QTimer.singleShot(0, lambda: self._aspect_changed(self.aspect_combo.currentIndex(), keep_rect=True))
            self.flash('拖曳調整裁切範圍，Enter 套用、Esc 取消', 4000)
        else:
            if self.crop_mode:
                self._apply_crop()
        self._update_crop_buttons()

    def _aspect_changed(self, idx, keep_rect=False):
        _, a = ASPECTS[idx]
        if a == 'orig':
            lw, lh = self.canvas.logical_size()
            a = (lw / lh) if self.canvas.has_image() and lh else None
            if self.crop_mode and self.engine is not None:
                w, h = self.engine.proxy.size
                if self.params['orient'] in (5, 6, 7, 8):
                    w, h = h, w
                a = w / h
        if keep_rect and a is None:
            self.canvas.aspect = None
            return
        self.canvas.set_aspect(a) if self.crop_mode else setattr(self.canvas, 'aspect', a)

    def _apply_crop(self):
        if not self.crop_mode:
            return
        rect = [round(v, 5) for v in self.canvas.crop]
        if rect[0] <= 0.001 and rect[1] <= 0.001 and rect[2] >= 0.999 and rect[3] >= 0.999:
            rect = None
        self.crop_mode = False
        self.canvas.set_crop_mode(False)
        self.btn_crop.blockSignals(True)
        self.btn_crop.setChecked(False)
        self.btn_crop.blockSignals(False)
        self.params['crop'] = rect
        self._update_crop_buttons()
        self._changed()

    def _cancel_crop(self):
        if not self.crop_mode:
            return
        self.crop_mode = False
        self.canvas.set_crop_mode(False)
        self.btn_crop.blockSignals(True)
        self.btn_crop.setChecked(False)
        self.btn_crop.blockSignals(False)
        self._update_crop_buttons()
        self._render()

    def _clear_crop(self):
        if self.crop_mode:
            self.canvas.crop = [0.0, 0.0, 1.0, 1.0]
            self.canvas.update()
        if self.params['crop']:
            self.params['crop'] = None
            if not self.crop_mode:
                self._changed()
        self._update_crop_buttons()

    def _update_crop_buttons(self):
        self.btn_crop_apply.setEnabled(self.crop_mode)
        self.btn_crop_cancel.setEnabled(self.crop_mode)
        self.btn_crop_clear.setEnabled(self.crop_mode or bool(self.params.get('crop')))

    # ================================================================== presets
    def _preset_activated(self, idx):
        if idx <= 0 or self.engine is None:
            return
        name = self.preset_combo.itemText(idx)
        self._apply_preset_dict(PRESETS.get(name, {}))
        self.preset_combo.setCurrentIndex(0)
        self.flash(f'已套用預設集：{name}')

    def _apply_preset_dict(self, d):
        geo = {k: copy.deepcopy(self.params[k]) for k in GEOMETRY_KEYS}
        newp = merge_params(default_params(), d)
        newp.update(geo)
        self.params = newp
        self._sync_ui()
        self._changed()

    def _save_preset(self):
        d = os.path.join(cache_dir('presets'))
        fn, _ = QFileDialog.getSaveFileName(self, '儲存預設集', os.path.join(d, '我的預設集.json'), 'JSON (*.json)')
        if not fn:
            return
        data = {k: v for k, v in self.params.items() if k not in GEOMETRY_KEYS}
        try:
            with open(fn, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=1)
            self.flash('已儲存預設集')
        except OSError as e:
            QMessageBox.warning(self, '儲存預設集', str(e))

    def _load_preset(self):
        fn, _ = QFileDialog.getOpenFileName(self, '載入預設集', cache_dir('presets'), 'JSON (*.json)')
        if not fn:
            return
        try:
            with open(fn, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if not isinstance(data, dict):
                raise ValueError('格式不正確')
            self._apply_preset_dict(data)
            self.flash('已載入預設集')
        except (OSError, ValueError) as e:
            QMessageBox.warning(self, '載入預設集', f'無法載入：{e}')

    # ================================================================== saving
    def _output_size(self):
        w, h = self.engine.full.size
        p = self.params
        if p['orient'] in (5, 6, 7, 8):
            w, h = h, w
        if abs(p['straighten']) >= 0.01:
            s = straighten_scale(w, h, p['straighten'])
            w, h = int(round(w * s)), int(round(h * s))
        if p['crop']:
            x0, y0, x1, y1 = p['crop']
            w, h = max(1, int(round((x1 - x0) * w))), max(1, int(round((y1 - y0) * h)))
        return w, h

    def save(self, save_as=False) -> bool:
        if self.engine is None:
            return False
        if self.crop_mode:
            self._apply_crop()
        self._flush_commit()
        target = self.path
        ext = ext_of(target)
        if save_as or ext not in WRITABLE_EXTS:
            stem = os.path.splitext(os.path.basename(self.path))[0]
            dext = ext if ext in WRITABLE_EXTS else '.jpg'
            filters = {'.png': 'PNG (*.png)', '.webp': 'WEBP (*.webp)', '.tif': 'TIFF (*.tif *.tiff)',
                       '.tiff': 'TIFF (*.tif *.tiff)', '.bmp': 'BMP (*.bmp)'}
            all_f = 'JPEG (*.jpg *.jpeg);;PNG (*.png);;WEBP (*.webp);;TIFF (*.tif *.tiff);;BMP (*.bmp)'
            fn, chosen = QFileDialog.getSaveFileName(self, '另存新檔',
                                                     os.path.join(os.path.dirname(self.path), stem + '_edit' + dext),
                                                     all_f, filters.get(dext, 'JPEG (*.jpg *.jpeg)'))
            if not fn:
                return False
            if ext_of(fn) not in WRITABLE_EXTS:
                fn += {'PNG': '.png', 'WEBP': '.webp', 'TIFF': '.tif', 'BMP': '.bmp'}.get(chosen.split(' ')[0], '.jpg')
            target = fn
        else:
            r = QMessageBox.question(self, '儲存', f'要覆寫原始檔案「{os.path.basename(target)}」嗎？\n\n'
                                     f'原始檔會先備份到：\n{cache_dir("originals")}')
            if r != QMessageBox.Yes:
                return False
        dlg = SaveOptionsDialog(target, self._output_size(), self.settings, self)
        if dlg.exec() != QDialog.Accepted:
            return False
        quality, long_side = dlg.values()
        if norm(target) == norm(self.path) and norm(target) not in self._backed_up:
            try:
                shutil.copy2(target, os.path.join(cache_dir('originals'),
                                                  time.strftime('%Y%m%d-%H%M%S_') + os.path.basename(target)))
                self._backed_up.add(norm(target))
            except OSError:
                pass
        ok, msg = self._run_save(target, quality, long_side)
        if ok:
            self._saved_params = copy.deepcopy(self.params)
            self.saved.emit(target)
            self.flash(f'已儲存：{os.path.basename(target)}', 4000)
            self._update_status()
        else:
            QMessageBox.warning(self, '儲存失敗', msg)
        return ok

    def _run_save(self, target, quality, long_side):
        worker = SaveWorker(self.engine.full, copy.deepcopy(self.params), self.alpha, target,
                            self.src_exif, self.src_icc, quality, long_side, self)
        prog = QProgressDialog('正在以完整解析度套用調整並儲存…', None, 0, 0, self)
        prog.setWindowTitle('儲存')
        prog.setWindowModality(Qt.WindowModal)
        prog.setMinimumDuration(0)
        prog.setCancelButton(None)
        self._save_loop = QEventLoop()
        self._save_result = (False, '未完成')
        worker.done.connect(self._save_done)
        worker.start()
        prog.show()
        self._save_loop.exec()
        worker.wait()
        prog.close()
        worker.deleteLater()
        return self._save_result

    def _save_done(self, ok, msg):
        self._save_result = (ok, msg)
        self._save_loop.quit()

    # ================================================================== leaving
    def confirm_leave(self) -> bool:
        if self.crop_mode:
            self._apply_crop()
        if not self.is_dirty():
            return True
        box = QMessageBox(self)
        box.setWindowTitle('尚未儲存')
        box.setIcon(QMessageBox.Question)
        box.setText('影像已調整但尚未儲存，要儲存變更嗎？')
        b_save = box.addButton('儲存', QMessageBox.AcceptRole)
        b_as = box.addButton('另存新檔…', QMessageBox.AcceptRole)
        b_discard = box.addButton('不儲存', QMessageBox.DestructiveRole)
        box.addButton('取消', QMessageBox.RejectRole)
        box.setDefaultButton(b_save)
        box.exec()
        c = box.clickedButton()
        if c is b_save:
            return self.save(False)
        if c is b_as:
            return self.save(True)
        return c is b_discard

    def done(self):
        if self.confirm_leave():
            path = self.path
            self.unload()
            self.finished.emit(path or '')

    def cancel(self):
        if self.crop_mode:
            self._cancel_crop()
        if self.is_dirty():
            if QMessageBox.question(self, '取消編輯', '要放棄所有未儲存的調整嗎？') != QMessageBox.Yes:
                return
        path = self.path
        self.unload()
        self.finished.emit(path or '')

    # ================================================================== status / keys
    def flash(self, text, ms=2500):
        self.st_msg.setText(text)
        self._flash_timer.start(ms)

    def _update_status(self):
        if self.engine is None:
            self.st_name.setText('')
            self.st_dims.setText('')
            self.st_dirty.setText('')
            self.st_zoom.setText('')
            return
        self.st_name.setText(os.path.basename(self.path))
        w, h = self._output_size()
        self.st_dims.setText(f'輸出 {w} × {h}')
        self.st_dirty.setText('● 已修改' if self.is_dirty() else '')
        self.st_zoom.setText(f"預覽 {self.canvas.zoom() * 100:.0f}%")

    def keyPressEvent(self, ev):
        k = ev.key()
        if k == Qt.Key_Backslash and not ev.isAutoRepeat():
            self._compare(True)
            return
        if self.crop_mode and k in (Qt.Key_Return, Qt.Key_Enter):
            self._apply_crop()
            return
        if k == Qt.Key_Escape:
            if self.crop_mode:
                self._cancel_crop()
            elif self.btn_pick.isChecked():
                self.btn_pick.setChecked(False)
            return
        super().keyPressEvent(ev)

    def keyReleaseEvent(self, ev):
        if ev.key() == Qt.Key_Backslash and not ev.isAutoRepeat():
            self._compare(False)
            return
        super().keyReleaseEvent(ev)
