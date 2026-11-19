"""Asynchronous thumbnail cache, folder model and thumbnail delegate."""
from __future__ import annotations

import hashlib
import os
from collections import OrderedDict

from PySide6.QtCore import (Qt, QObject, Signal, QRunnable, QThreadPool, QAbstractListModel,
                            QModelIndex, QSize, QRectF, QPointF, QMimeData, QUrl)
from PySide6.QtGui import QImage, QPixmap, QPainter, QColor, QPen, QFont
from PySide6.QtWidgets import QStyledItemDelegate, QStyle

from .common import read_qimage, cache_dir, norm, is_image, human_size, fmt_time, glyph_pixmap, G

THUMB_MAX = 320
_HIDDEN = 0x2 | 0x4  # FILE_ATTRIBUTE_HIDDEN | FILE_ATTRIBUTE_SYSTEM


class Entry:
    __slots__ = ('path', 'name', 'is_dir', 'size', 'mtime', 'ext')

    def __init__(self, path, name, is_dir, size=0, mtime=0):
        self.path = path
        self.name = name
        self.is_dir = is_dir
        self.size = size
        self.mtime = mtime
        self.ext = '' if is_dir else os.path.splitext(name)[1].lower()

    @property
    def key(self):
        return f"{norm(self.path)}|{self.mtime}|{self.size}"


def entry_from_path(path: str) -> Entry:
    try:
        st = os.stat(path)
        return Entry(path, os.path.basename(path), False, st.st_size, st.st_mtime_ns)
    except OSError:
        return Entry(path, os.path.basename(path), False, 0, 0)


def scan_folder(folder: str, include_dirs=True) -> list[Entry]:
    out: list[Entry] = []
    try:
        with os.scandir(folder) as it:
            for de in it:
                try:
                    st = de.stat(follow_symlinks=False)
                    attrs = getattr(st, 'st_file_attributes', 0)
                    if de.is_dir(follow_symlinks=False):
                        if include_dirs and not (attrs & _HIDDEN) and not de.name.startswith(('.', '$')):
                            out.append(Entry(de.path, de.name, True, 0, st.st_mtime_ns))
                    elif is_image(de.name) and not (attrs & _HIDDEN):
                        out.append(Entry(de.path, de.name, False, st.st_size, st.st_mtime_ns))
                except OSError:
                    continue
    except OSError:
        pass
    return out


# --------------------------------------------------------------------------- cache
class _Sig(QObject):
    done = Signal(str, str, QImage)


class _ThumbTask(QRunnable):
    def __init__(self, key, path, disk_dir, sig):
        super().__init__()
        self.key, self.path, self.disk_dir, self.sig = key, path, disk_dir, sig
        self.setAutoDelete(True)

    def run(self):
        img = QImage()
        try:
            h = hashlib.md5(self.key.encode('utf-8')).hexdigest()
            jpg = os.path.join(self.disk_dir, h + '.jpg')
            png = os.path.join(self.disk_dir, h + '.png')
            for f in (jpg, png):
                if os.path.exists(f):
                    img = QImage(f)
                    if not img.isNull():
                        break
            if img.isNull():
                img = read_qimage(self.path, THUMB_MAX, THUMB_MAX)
                if not img.isNull():
                    if img.width() > THUMB_MAX or img.height() > THUMB_MAX:
                        img = img.scaled(THUMB_MAX, THUMB_MAX, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    try:
                        if os.path.getsize(self.path) > 80_000:
                            if img.hasAlphaChannel():
                                img.save(png, 'PNG')
                            else:
                                img.save(jpg, 'JPG', 88)
                    except OSError:
                        pass
        except Exception:  # noqa: BLE001
            img = QImage()
        self.sig.done.emit(self.key, self.path, img)


class ThumbCache(QObject):
    thumbReady = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(max(2, min(6, (os.cpu_count() or 4) - 1)))
        self.mem: OrderedDict[str, QImage] = OrderedDict()
        self.max_items = 4000
        self.pending: set[str] = set()
        self.failed: set[str] = set()
        self.disk_dir = cache_dir('thumbs')
        self._sig = _Sig()
        self._sig.done.connect(self._on_done)

    def get(self, entry: Entry, request=True):
        k = entry.key
        img = self.mem.get(k)
        if img is not None:
            self.mem.move_to_end(k)
            return img
        if request and k not in self.pending and k not in self.failed:
            self.pending.add(k)
            self.pool.start(_ThumbTask(k, entry.path, self.disk_dir, self._sig))
        return None

    def cancel_pending(self):
        self.pool.clear()
        self.pending.clear()

    def invalidate(self, path: str):
        prefix = norm(path) + '|'
        for k in [k for k in self.mem if k.startswith(prefix)]:
            del self.mem[k]
        self.failed = {k for k in self.failed if not k.startswith(prefix)}

    def _on_done(self, key, path, img):
        self.pending.discard(key)
        if img.isNull():
            self.failed.add(key)
        else:
            self.mem[key] = img
            while len(self.mem) > self.max_items:
                self.mem.popitem(last=False)
        self.thumbReady.emit(path)


# --------------------------------------------------------------------------- model
class FolderModel(QAbstractListModel):
    def __init__(self, cache: ThumbCache, parent=None):
        super().__init__(parent)
        self.entries: list[Entry] = []
        self.row_of: dict[str, int] = {}
        cache.thumbReady.connect(self.refresh_path)

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.entries)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or index.row() >= len(self.entries):
            return None
        e = self.entries[index.row()]
        if role == Qt.DisplayRole:
            return e.name
        if role == Qt.UserRole:
            return e
        if role == Qt.ToolTipRole:
            if e.is_dir:
                return e.name
            return f"{e.name}\n{human_size(e.size)}\n{fmt_time(e.mtime)}"
        return None

    def flags(self, index):
        f = super().flags(index)
        if not index.isValid():
            return f | Qt.ItemIsDropEnabled          # dropping on the grid background (from other apps)
        f |= Qt.ItemIsDragEnabled
        if index.row() < len(self.entries) and self.entries[index.row()].is_dir:
            f |= Qt.ItemIsDropEnabled                # folders are drop targets (move / copy into them)
        return f

    def set_entries(self, entries: list[Entry]):
        self.beginResetModel()
        self.entries = list(entries)
        self.row_of = {norm(e.path): i for i, e in enumerate(self.entries)}
        self.endResetModel()

    def refresh_path(self, path: str):
        r = self.row_of.get(norm(path))
        if r is not None:
            idx = self.index(r)
            self.dataChanged.emit(idx, idx)

    def refresh_all(self):
        if self.entries:
            self.dataChanged.emit(self.index(0), self.index(len(self.entries) - 1))

    def replace_entry(self, path: str, entry: Entry):
        r = self.row_of.get(norm(path))
        if r is not None:
            self.entries[r] = entry
            self.row_of.pop(norm(path), None)
            self.row_of[norm(entry.path)] = r
            idx = self.index(r)
            self.dataChanged.emit(idx, idx)

    def remove_path(self, path: str):
        r = self.row_of.get(norm(path))
        if r is None:
            return
        self.beginRemoveRows(QModelIndex(), r, r)
        del self.entries[r]
        self.row_of = {norm(e.path): i for i, e in enumerate(self.entries)}
        self.endRemoveRows()

    def mimeTypes(self):
        return ['text/uri-list']

    def mimeData(self, indexes):
        md = QMimeData()
        md.setUrls([QUrl.fromLocalFile(self.entries[i.row()].path) for i in indexes if i.isValid()])
        return md

    def supportedDragActions(self):
        return Qt.CopyAction | Qt.MoveAction

    def supportedDropActions(self):
        return Qt.CopyAction | Qt.MoveAction

    def canDropMimeData(self, data, action, row, column, parent):
        return data.hasUrls()

    def dropMimeData(self, data, action, row, column, parent):
        return False   # drops are handled by ManagePage.drop_files (via ThumbListView.dropEvent)


# --------------------------------------------------------------------------- delegate
class ThumbDelegate(QStyledItemDelegate):
    def __init__(self, cache: ThumbCache, ratings=None, size=150, show_names=True, parent=None):
        super().__init__(parent)
        self.cache = cache
        self.ratings = ratings
        self.ts = size
        self.show_names = show_names
        self.pix: OrderedDict = OrderedDict()
        self._folder_pm = {}

    def set_size(self, s: int):
        self.ts = int(s)
        self.pix.clear()

    def sizeHint(self, option, index):
        # name row height follows the UI font size (Settings > 字體大小)
        name_h = option.fontMetrics.height() + 12 if self.show_names else 0
        return QSize(self.ts + 14, self.ts + 10 + name_h)

    def _thumb_pm(self, e: Entry, ts: int, dpr: float):
        k = (e.key, ts, dpr)
        pm = self.pix.get(k)
        if pm is not None:
            self.pix.move_to_end(k)
            return pm
        img = self.cache.get(e)
        if img is None:
            return None
        target = max(1, int(ts * dpr))
        if img.width() > target or img.height() > target:
            img = img.scaled(target, target, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        pm = QPixmap.fromImage(img)
        pm.setDevicePixelRatio(dpr)
        self.pix[k] = pm
        while len(self.pix) > 1500:
            self.pix.popitem(last=False)
        return pm

    def _folder(self, ts, dpr):
        k = (ts, dpr)
        if k not in self._folder_pm:
            size = max(16, int(ts * 0.8 * dpr))
            pm = glyph_pixmap(G.FOLDER, '#e9b949', size, scale=0.9)
            pm.setDevicePixelRatio(dpr)
            self._folder_pm[k] = pm
        return self._folder_pm[k]

    def paint(self, p: QPainter, opt, index):
        e = index.data(Qt.UserRole)
        if e is None:
            return
        p.save()
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        r = QRectF(opt.rect).adjusted(2, 2, -2, -2)
        sel = bool(opt.state & QStyle.StateFlag.State_Selected)
        hov = bool(opt.state & QStyle.StateFlag.State_MouseOver)
        if sel:
            p.setPen(QPen(QColor(55, 148, 255), 1.5))
            p.setBrush(QColor(55, 148, 255, 60))
            p.drawRoundedRect(r, 6, 6)
        elif hov:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(255, 255, 255, 20))
            p.drawRoundedRect(r, 6, 6)
        ts = self.ts
        tr = QRectF(r.x() + (r.width() - ts) / 2.0, r.y() + 4, ts, ts)
        dev = p.device()
        dpr = dev.devicePixelRatioF() if dev is not None else 1.0
        if e.is_dir:
            pm = self._folder(ts, dpr)
            w, h = pm.width() / dpr, pm.height() / dpr
            p.drawPixmap(QPointF(tr.x() + (ts - w) / 2, tr.y() + (ts - h) / 2), pm)
        else:
            pm = self._thumb_pm(e, ts, dpr)
            if pm is not None:
                w, h = pm.width() / pm.devicePixelRatio(), pm.height() / pm.devicePixelRatio()
                x, y = tr.x() + (ts - w) / 2.0, tr.y() + (ts - h) / 2.0
                p.drawPixmap(QPointF(x, y), pm)
                p.setPen(QPen(QColor(0, 0, 0, 140), 1))
                p.setBrush(Qt.NoBrush)
                p.drawRect(QRectF(x - 0.5, y - 0.5, w + 1, h + 1))
            else:
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(255, 255, 255, 14))
                p.drawRoundedRect(tr.adjusted(ts * 0.12, ts * 0.12, -ts * 0.12, -ts * 0.12), 5, 5)
                p.setPen(QColor(130, 130, 136))
                p.drawText(tr, Qt.AlignCenter, e.ext.lstrip('.').upper())
            rating = self.ratings.get(e.path) if self.ratings is not None else 0
            if rating:
                star_font = QFont(opt.font)
                star_font.setPointSizeF(max(7.0, opt.font.pointSizeF() * 0.95))
                p.setFont(star_font)
                txt = '★' * rating
                fm = p.fontMetrics()
                bw = fm.horizontalAdvance(txt) + 8
                bh = fm.height() + 2
                br = QRectF(tr.x() + 4, tr.bottom() - bh - 3, bw, bh)
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(0, 0, 0, 150))
                p.drawRoundedRect(br, 4, 4)
                p.setPen(QColor(255, 200, 40))
                p.drawText(br, Qt.AlignCenter, txt)
        if self.show_names:
            p.setFont(opt.font)
            tx = QRectF(r.x() + 4, tr.bottom() + 3, r.width() - 8, opt.fontMetrics.height() + 4)
            p.setPen(QColor(255, 255, 255) if sel else QColor(205, 205, 210))
            name = opt.fontMetrics.elidedText(e.name, Qt.ElideMiddle, int(tx.width()))
            p.drawText(tx, Qt.AlignHCenter | Qt.AlignTop, name)
        p.restore()
