"""Shared helpers: paths, settings, ratings, icons, image I/O and file operations."""
from __future__ import annotations

import json
import os
import re
import shutil
import struct
import subprocess
import time

from PySide6.QtCore import Qt, QSettings, QFile, QRect, QRectF, QPointF, QSize
from PySide6.QtGui import (QImage, QImageReader, QImageIOHandler, QIcon, QPixmap, QPainter,
                           QFont, QColor, QFontDatabase, QLinearGradient, QPolygonF)

APP_NAME = "PhotoViewer"
APP_TITLE = "Photo Viewer"

IMAGE_EXTS = {'.jpg', '.jpeg', '.jpe', '.jfif', '.png', '.bmp', '.gif', '.webp', '.tif',
              '.tiff', '.ico', '.tga', '.ppm', '.pgm', '.pbm'}
WRITABLE_EXTS = {'.jpg', '.jpeg', '.jpe', '.jfif', '.png', '.bmp', '.webp', '.tif', '.tiff'}
JPEG_EXTS = {'.jpg', '.jpeg', '.jpe', '.jfif'}


def ext_of(path: str) -> str:
    return os.path.splitext(path)[1].lower()


def is_image(path: str) -> bool:
    return ext_of(path) in IMAGE_EXTS


def norm(path: str) -> str:
    return os.path.normcase(os.path.abspath(path))


_num_re = re.compile(r'(\d+)')


def natural_key(s: str):
    return [int(t) if t.isdigit() else t.lower() for t in _num_re.split(s)]


def human_size(n: float) -> str:
    for unit in ('B', 'KB', 'MB', 'GB'):
        if n < 1024 or unit == 'GB':
            return f"{n:.0f} {unit}" if unit == 'B' else f"{n:.1f} {unit}"
        n /= 1024.0
    return f"{n:.1f} TB"


def fmt_time(mtime_ns_or_s) -> str:
    t = mtime_ns_or_s / 1e9 if mtime_ns_or_s > 1e12 else mtime_ns_or_s
    return time.strftime('%Y/%m/%d %H:%M', time.localtime(t))


def app_data_dir() -> str:
    base = os.environ.get('APPDATA') or os.path.expanduser('~')
    d = os.path.join(base, APP_NAME)
    os.makedirs(d, exist_ok=True)
    return d


def cache_dir(sub: str) -> str:
    base = os.environ.get('LOCALAPPDATA') or app_data_dir()
    d = os.path.join(base, APP_NAME, sub)
    os.makedirs(d, exist_ok=True)
    return d


def list_images(folder: str) -> list[str]:
    try:
        names = [n for n in os.listdir(folder) if is_image(n)]
    except OSError:
        return []
    names.sort(key=natural_key)
    return [os.path.join(folder, n) for n in names]


# --------------------------------------------------------------------------- settings
class Settings:
    def __init__(self):
        self.s = QSettings(os.path.join(app_data_dir(), 'settings.ini'), QSettings.Format.IniFormat)

    def get(self, key, default=None, type_=None):
        v = self.s.value(key, default)
        if v is None:
            return default
        try:
            if type_ is bool:
                if isinstance(v, bool):
                    return v
                return str(v).lower() in ('true', '1', 'yes')
            if type_ is int:
                return int(v)
            if type_ is float:
                return float(v)
            if type_ is list:
                if isinstance(v, str):
                    return [v] if v else []
                return list(v)
        except (TypeError, ValueError):
            return default
        return v

    def set(self, key, value):
        self.s.setValue(key, value)

    def sync(self):
        self.s.sync()


class RatingDB:
    """0-5 star ratings stored in a small JSON file, keyed by normalised path."""

    def __init__(self):
        self.path = os.path.join(app_data_dir(), 'ratings.json')
        self.data: dict[str, int] = {}
        try:
            with open(self.path, 'r', encoding='utf-8') as f:
                self.data = {k: int(v) for k, v in json.load(f).items()}
        except (OSError, ValueError, AttributeError):
            self.data = {}

    def get(self, path: str) -> int:
        return self.data.get(norm(path), 0)

    def set(self, path: str, rating: int):
        k = norm(path)
        if rating:
            self.data[k] = int(rating)
        else:
            self.data.pop(k, None)
        self._save()

    def move(self, old: str, new: str):
        k = norm(old)
        if k in self.data:
            self.data[norm(new)] = self.data.pop(k)
            self._save()

    def remove(self, path: str):
        if self.data.pop(norm(path), None) is not None:
            self._save()

    def _save(self):
        tmp = self.path + '.tmp'
        try:
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump(self.data, f, ensure_ascii=False)
            os.replace(tmp, self.path)
        except OSError:
            pass


# --------------------------------------------------------------------------- icons
class G:
    """Segoe Fluent / MDL2 glyph code points."""
    BACK = ''
    FORWARD = ''
    UP = ''
    REFRESH = ''
    ROTATE = ''
    DELETE = ''
    EDIT = ''
    PHOTO = ''
    GRID = ''
    FULLSCREEN = ''
    ZOOM_IN = ''
    ZOOM_OUT = ''
    FIT = ''
    ACTUAL = ''
    SAVE = ''
    SAVE_AS = ''
    UNDO = ''
    REDO = ''
    FOLDER = ''
    PLAY = ''
    PAUSE = ''
    COPY = ''
    MOVE = ''
    RENAME = ''
    SEARCH = ''
    INFO = ''
    CROP = ''
    STAR = ''
    STAR_FILL = ''
    SORT = ''
    FILTER = ''
    CHECK = ''
    CANCEL = ''
    RESET = ''
    COMPARE = ''
    EYEDROPPER = ''
    FILMSTRIP = ''
    PICTURES = ''
    DESKTOP = ''
    DOWNLOAD = ''
    DOCUMENT = ''
    DRIVE = ''
    HOME = ''
    NEW_FOLDER = ''
    FLIP_H = ''
    BRIGHTNESS = ''
    COLOR = ''
    PRESET = ''
    PREVIEW = ''
    SETTINGS = ''
    TEXT = ''
    BOLD = ''
    ITALIC = ''
    ALIGN_LEFT = ''
    ALIGN_CENTER = ''
    ALIGN_RIGHT = ''
    RESIZE = ''
    STITCH = ''
    ADD = ''
    ARROW_DOWN = ''
    ARROW_RIGHT = ''
    ARROW_LEFT = ''


_icon_family = None


def icon_family() -> str:
    global _icon_family
    if _icon_family is None:
        fams = set(QFontDatabase.families())
        _icon_family = next((f for f in ('Segoe Fluent Icons', 'Segoe MDL2 Assets') if f in fams), '')
    return _icon_family


def glyph_pixmap(code: str, color='#e8e8e8', size=32, mirror=False, scale=0.62) -> QPixmap:
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    fam = icon_family()
    if not fam:
        return pm
    p = QPainter(pm)
    p.setRenderHint(QPainter.TextAntialiasing)
    f = QFont(fam)
    f.setPixelSize(max(6, int(size * scale)))
    p.setFont(f)
    p.setPen(QColor(color))
    if mirror:
        p.translate(size, 0)
        p.scale(-1, 1)
    p.drawText(QRect(0, 0, size, size), Qt.AlignCenter, code)
    p.end()
    return pm


_icon_cache: dict = {}


def glyph_icon(code: str, color='#e3e3e3', mirror=False) -> QIcon:
    key = (code, color, mirror)
    if key in _icon_cache:
        return _icon_cache[key]
    icon = QIcon()
    if icon_family():
        icon.addPixmap(glyph_pixmap(code, color, 40, mirror), QIcon.Mode.Normal)
        icon.addPixmap(glyph_pixmap(code, '#ffffff', 40, mirror), QIcon.Mode.Active)
        icon.addPixmap(glyph_pixmap(code, '#5c5c60', 40, mirror), QIcon.Mode.Disabled)
    _icon_cache[key] = icon
    return icon


def app_icon() -> QIcon:
    icon = QIcon()
    for s in (16, 24, 32, 48, 64, 128, 256):
        pm = QPixmap(s, s)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        grad = QLinearGradient(0, 0, s, s)
        grad.setColorAt(0, QColor('#2f8cff'))
        grad.setColorAt(1, QColor('#7b4dff'))
        p.setBrush(grad)
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(QRectF(s * 0.06, s * 0.06, s * 0.88, s * 0.88), s * 0.2, s * 0.2)
        p.setBrush(QColor(255, 214, 90))
        p.drawEllipse(QPointF(s * 0.68, s * 0.34), s * 0.1, s * 0.1)
        p.setBrush(QColor(255, 255, 255, 240))
        p.drawPolygon(QPolygonF([QPointF(s * 0.16, s * 0.78), QPointF(s * 0.40, s * 0.44),
                                 QPointF(s * 0.56, s * 0.64), QPointF(s * 0.66, s * 0.54),
                                 QPointF(s * 0.84, s * 0.78)]))
        p.end()
        icon.addPixmap(pm)
    return icon


# --------------------------------------------------------------------------- image I/O
_ROT90 = QImageIOHandler.Transformation.TransformationRotate90


def oriented_size(path: str) -> QSize:
    r = QImageReader(path)
    r.setAutoTransform(True)
    s = r.size()
    if s.isValid() and (r.transformation() & _ROT90):
        s = s.transposed()
    return s


def read_qimage(path: str, max_w: int = 0, max_h: int = 0) -> QImage:
    """Decode an image honouring EXIF orientation; optionally decode at reduced size (fast for JPEG)."""
    r = QImageReader(path)
    r.setAutoTransform(True)
    if max_w > 0:
        max_h = max_h or max_w
        s = r.size()
        if s.isValid():
            rot = bool(r.transformation() & _ROT90)
            tw, th = (max_h, max_w) if rot else (max_w, max_h)
            if s.width() > tw or s.height() > th:
                r.setScaledSize(s.scaled(tw, th, Qt.KeepAspectRatio))
    img = r.read()
    if img.isNull():
        img = _pil_read(path, max_w, max_h)
    return img


def _pil_read(path: str, max_w: int = 0, max_h: int = 0) -> QImage:
    try:
        from PIL import Image, ImageOps
        with Image.open(path) as im:
            im = ImageOps.exif_transpose(im)
            if max_w > 0:
                im.thumbnail((max_w, max_h or max_w))
            return pil_to_qimage(im)
    except Exception:
        return QImage()


def pil_to_qimage(im) -> QImage:
    if im.mode in ('RGBA', 'LA', 'PA') or (im.mode == 'P' and 'transparency' in im.info):
        im = im.convert('RGBA')
        fmt, bpp = QImage.Format.Format_RGBA8888, 4
    else:
        im = im.convert('RGB')
        fmt, bpp = QImage.Format.Format_RGB888, 3
    data = im.tobytes()
    qi = QImage(data, im.width, im.height, im.width * bpp, fmt)
    return qi.copy()


def array_to_qimage(a) -> QImage:
    """HxWx3 uint8 numpy array -> QImage (deep copy)."""
    import numpy as np
    a = np.ascontiguousarray(a)
    h, w = a.shape[:2]
    qi = QImage(a.data, w, h, 3 * w, QImage.Format.Format_RGB888)
    return qi.copy()


# --------------------------------------------------------------------------- EXIF
_EXPOSURE_PROGRAM = {0: '未定義', 1: '手動', 2: '程式自動', 3: '光圈優先', 4: '快門優先',
                     5: '創意模式', 6: '運動模式', 7: '人像模式', 8: '風景模式'}
_METERING = {0: '未知', 1: '平均測光', 2: '中央重點', 3: '點測光', 4: '多點測光', 5: '評價測光', 6: '局部測光'}


def _rat(v):
    try:
        if isinstance(v, tuple) and len(v) == 2:
            return v[0] / v[1] if v[1] else 0.0
        return float(v)
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def exif_info(path: str) -> list[tuple[str, str]]:
    """Return a list of (label, value) EXIF items in Traditional Chinese."""
    out: list[tuple[str, str]] = []
    try:
        from PIL import Image
        with Image.open(path) as im:
            ex = im.getexif()
            if not ex:
                return out
            sub = ex.get_ifd(0x8769)
            gps = ex.get_ifd(0x8825)
    except Exception:
        return out

    def s(v):
        if isinstance(v, bytes):
            v = v.decode('utf-8', 'ignore')
        return str(v).strip('\x00 ').strip()

    make, model = s(ex.get(0x010F, '')), s(ex.get(0x0110, ''))
    if model:
        out.append(('相機', model if (not make or model.startswith(make.split()[0])) else f"{make} {model}"))
    lens = s(sub.get(0xA434, ''))
    if lens:
        out.append(('鏡頭', lens))
    dt = s(sub.get(0x9003, '') or ex.get(0x0132, ''))
    if dt:
        out.append(('拍攝時間', dt.replace(':', '/', 2)))
    et = _rat(sub.get(0x829A))
    if et:
        out.append(('快門', f"1/{round(1 / et)} 秒" if et < 1 else f"{et:g} 秒"))
    fn = _rat(sub.get(0x829D))
    if fn:
        out.append(('光圈', f"f/{fn:.1f}"))
    iso = sub.get(0x8827)
    if iso:
        if isinstance(iso, (tuple, list)):
            iso = iso[0]
        out.append(('ISO', str(iso)))
    fl = _rat(sub.get(0x920A))
    if fl:
        f35 = sub.get(0xA405)
        out.append(('焦距', f"{fl:.0f} mm" + (f"（等效 {f35} mm）" if f35 else '')))
    eb = _rat(sub.get(0x9204))
    if eb is not None and 0x9204 in sub:
        out.append(('曝光補償', f"{eb:+.1f} EV"))
    if 0x8822 in sub:
        out.append(('曝光模式', _EXPOSURE_PROGRAM.get(sub.get(0x8822), str(sub.get(0x8822)))))
    if 0x9207 in sub:
        out.append(('測光模式', _METERING.get(sub.get(0x9207), str(sub.get(0x9207)))))
    if 0x9209 in sub:
        out.append(('閃光燈', '有閃光' if (int(sub.get(0x9209)) & 1) else '未閃光'))
    if 0xA403 in sub:
        out.append(('白平衡', '手動' if sub.get(0xA403) == 1 else '自動'))
    sw = s(ex.get(0x0131, ''))
    if sw:
        out.append(('軟體', sw))
    artist = s(ex.get(0x013B, ''))
    if artist:
        out.append(('作者', artist))
    try:
        if gps and 2 in gps and 4 in gps:
            def deg(v):
                d, m, sec = (_rat(x) or 0.0 for x in v)
                return d + m / 60 + sec / 3600
            lat = deg(gps[2]) * (-1 if s(gps.get(1, 'N')) == 'S' else 1)
            lon = deg(gps[4]) * (-1 if s(gps.get(3, 'E')) == 'W' else 1)
            out.append(('GPS', f"{lat:.6f}, {lon:.6f}"))
    except Exception:
        pass
    return out


# --------------------------------------------------------------------------- file ops
def move_to_trash(path: str) -> bool:
    try:
        r = QFile.moveToTrash(path)
    except Exception:
        return False
    if isinstance(r, tuple):
        r = r[0]
    return bool(r)


def unique_path(folder: str, name: str) -> str:
    base, ext = os.path.splitext(name)
    cand = os.path.join(folder, name)
    i = 1
    while os.path.exists(cand):
        cand = os.path.join(folder, f"{base} ({i}){ext}")
        i += 1
    return cand


def reveal_in_explorer(path: str):
    path = os.path.normpath(path)
    try:
        if os.path.isdir(path):
            subprocess.Popen(['explorer', path])
        else:
            subprocess.Popen(f'explorer /select,"{path}"')
    except OSError:
        pass


# --------------------------------------------------------------------------- orientation (D4 group)
# Each EXIF orientation as a 2x2 matrix mapping stored -> displayed coordinates (y axis down).
D4 = {1: (1, 0, 0, 1), 2: (-1, 0, 0, 1), 3: (-1, 0, 0, -1), 4: (1, 0, 0, -1),
      5: (0, 1, 1, 0), 6: (0, -1, 1, 0), 7: (0, -1, -1, 0), 8: (0, 1, -1, 0)}
_D4_INV = {v: k for k, v in D4.items()}
ORIENT_OPS = {'cw': D4[6], 'ccw': D4[8], '180': D4[3], 'flip_h': D4[2], 'flip_v': D4[4]}


def _mm(a, b):
    return (a[0] * b[0] + a[1] * b[2], a[0] * b[1] + a[1] * b[3],
            a[2] * b[0] + a[3] * b[2], a[2] * b[1] + a[3] * b[3])


def compose_orientation(cur: int, op: str) -> int:
    return _D4_INV[_mm(ORIENT_OPS[op], D4.get(cur, D4[1]))]


def _scan_jpeg_exif(data: bytes):
    """Return (status, seg_start, seg_end, ifd_entry_offset, endian)."""
    if data[:2] != b'\xff\xd8':
        return 'bad', 0, 0, 0, ''
    i = 2
    n = len(data)
    while i + 4 <= n:
        if data[i] != 0xFF:
            return 'bad', 0, 0, 0, ''
        while i + 1 < n and data[i + 1] == 0xFF:
            i += 1
        marker = data[i + 1]
        if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
            i += 2
            continue
        if marker in (0xDA, 0xD9):
            break
        seglen = struct.unpack('>H', data[i + 2:i + 4])[0]
        seg_end = i + 2 + seglen
        if marker == 0xE1 and data[i + 4:i + 10] == b'Exif\x00\x00':
            tiff = i + 10
            endian = {b'II': '<', b'MM': '>'}.get(bytes(data[tiff:tiff + 2]))
            if not endian:
                return 'bad', 0, 0, 0, ''
            ifd0 = struct.unpack(endian + 'I', data[tiff + 4:tiff + 8])[0]
            p = tiff + ifd0
            if p + 2 > seg_end:
                return 'no_tag', i, seg_end, 0, endian
            count = struct.unpack(endian + 'H', data[p:p + 2])[0]
            for k in range(count):
                ent = p + 2 + k * 12
                if ent + 12 > seg_end:
                    break
                tag, typ, cnt = struct.unpack(endian + 'HHI', data[ent:ent + 8])
                if tag == 0x0112 and typ == 3 and cnt == 1:
                    return 'found', i, seg_end, ent, endian
            return 'no_tag', i, seg_end, 0, endian
        i = seg_end
    return 'no_exif', 0, 0, 0, ''


def jpeg_orientation(path: str) -> int:
    try:
        with open(path, 'rb') as f:
            data = f.read(256 * 1024)
        st, _, _, ent, e = _scan_jpeg_exif(data)
        if st == 'found':
            v = struct.unpack(e + 'H', data[ent + 8:ent + 10])[0]
            return v if v in D4 else 1
    except OSError:
        pass
    return 1


def _atomic_write(path: str, data: bytes):
    tmp = path + '.pvtmp'
    with open(tmp, 'wb') as f:
        f.write(data)
    try:
        st = os.stat(path)
        shutil.copystat(path, tmp)
        os.utime(tmp, ns=(st.st_atime_ns, time.time_ns()))
    except OSError:
        pass
    os.replace(tmp, path)


def _jpeg_set_orientation(path: str, orient: int):
    with open(path, 'rb') as f:
        data = bytearray(f.read())
    st, s0, s1, ent, e = _scan_jpeg_exif(data)
    if st == 'bad':
        return False, '無法解析 JPEG 檔案'
    if st == 'found':
        data[ent + 8:ent + 10] = struct.pack(e + 'H', orient)
    elif st == 'no_exif':
        tiff = (b'II*\x00' + struct.pack('<I', 8) + struct.pack('<H', 1) +
                struct.pack('<HHI', 0x0112, 3, 1) + struct.pack('<HH', orient, 0) + struct.pack('<I', 0))
        payload = b'Exif\x00\x00' + tiff
        seg = b'\xff\xe1' + struct.pack('>H', len(payload) + 2) + payload
        pos = 2
        if data[2:4] == b'\xff\xe0':  # keep JFIF APP0 first
            pos = 4 + struct.unpack('>H', data[4:6])[0]
        data[pos:pos] = seg
    else:  # EXIF block without orientation tag: rebuild the block with Pillow (no pixel re-encode)
        from PIL import Image
        with Image.open(path) as im:
            ex = im.getexif()
            ex[0x0112] = orient
            payload = ex.tobytes()
        if not payload.startswith(b'Exif\x00\x00'):
            payload = b'Exif\x00\x00' + payload
        if len(payload) + 2 > 65535:
            return False, 'EXIF 資料過大'
        seg = b'\xff\xe1' + struct.pack('>H', len(payload) + 2) + payload
        data[s0:s1] = seg
    _atomic_write(path, bytes(data))
    return True, '已無損旋轉'


def rotate_file(path: str, op: str):
    """Rotate/flip an image file on disk. JPEG is lossless (EXIF orientation). Returns (ok, message)."""
    ext = ext_of(path)
    try:
        if ext in JPEG_EXTS:
            cur = jpeg_orientation(path)
            return _jpeg_set_orientation(path, compose_orientation(cur, op))
        if ext in ('.png', '.bmp', '.tif', '.tiff', '.webp'):
            from PIL import Image, ImageOps
            methods = {'cw': Image.Transpose.ROTATE_270, 'ccw': Image.Transpose.ROTATE_90,
                       '180': Image.Transpose.ROTATE_180, 'flip_h': Image.Transpose.FLIP_LEFT_RIGHT,
                       'flip_v': Image.Transpose.FLIP_TOP_BOTTOM}
            with Image.open(path) as im:
                if getattr(im, 'n_frames', 1) > 1:
                    return False, '不支援旋轉多頁或動畫影像'
                im.load()
                info = dict(im.info)
                fmt = im.format
                out = ImageOps.exif_transpose(im).transpose(methods[op])
            kw = {}
            if info.get('icc_profile'):
                kw['icc_profile'] = info['icc_profile']
            if fmt == 'WEBP':
                kw.update(lossless=bool(info.get('lossless')), quality=95)
            elif fmt == 'TIFF' and info.get('compression') not in (None, 'raw'):
                kw['compression'] = info['compression']
            tmp = path + '.pvtmp'
            out.save(tmp, format=fmt, **kw)
            os.replace(tmp, path)
            return True, '已旋轉'
        return False, '此格式不支援旋轉'
    except Exception as e:  # noqa: BLE001
        return False, f'旋轉失敗：{e}'
