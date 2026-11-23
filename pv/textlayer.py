"""Text layers: one layout/paint routine shared by the editor's live canvas overlay and the saved image.

A text layer is a plain dict (stored in the edit parameters, so undo/redo and "dirty" tracking just work).
Positions are fractions of the output image (x, y = centre of the text block) and the font size is a
percentage of the output image height, so a layer looks the same on the preview, after a resize and in
the full-resolution file.
"""
from __future__ import annotations

import copy

from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QImage, QPainter, QPainterPath, QPen, QPolygonF, QTransform

REF = 200.0            # glyph outlines are built at this pixel size, then scaled
BOX_PAD = 0.22         # background box padding, in font heights
SHADOW_OFF = (0.05, 0.06)

DEFAULT_FONT = 'Microsoft JhengHei UI'

TEXT_DEFAULTS = {
    'text': '', 'x': 0.5, 'y': 0.5, 'size': 8.0, 'angle': 0.0,
    'font': DEFAULT_FONT, 'bold': True, 'italic': False, 'align': 'center',
    'color': '#ffffff', 'opacity': 100,
    'stroke': 0, 'stroke_color': '#000000',          # outline width in % of the font size
    'shadow': True,
    'box': False, 'box_color': '#000000', 'box_opacity': 55,
}

MIN_SIZE, MAX_SIZE = 0.5, 60.0
PLACEHOLDER = '輸入文字'     # laid out (and ghosted on the canvas only) while a new layer is still empty


def new_text(**kw) -> dict:
    t = copy.deepcopy(TEXT_DEFAULTS)
    t.update(kw)
    return t


def normalized(t: dict) -> dict:
    """The layer with any missing keys filled in (layers from older presets / versions)."""
    if all(k in t for k in TEXT_DEFAULTS):
        return t
    out = copy.deepcopy(TEXT_DEFAULTS)
    out.update(t)
    return out


def label(t: dict) -> str:
    first = next((ln.strip() for ln in str(t.get('text', '')).split('\n') if ln.strip()), '')
    return first or '（空白文字）'


def is_blank(t: dict) -> bool:
    return not str(t.get('text', '')).strip()


# --------------------------------------------------------------------------- layout
_cache: dict = {}


def _font(t) -> QFont:
    f = QFont(t['font'] or DEFAULT_FONT)
    f.setPixelSize(int(REF))
    f.setBold(bool(t['bold']))
    f.setItalic(bool(t['italic']))
    f.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
    return f


def ref_path(t: dict, use_cache=True):
    """(path, rect): the text outline at REF px, centred on the origin, and its layout box."""
    t = normalized(t)
    txt = PLACEHOLDER if is_blank(t) else str(t['text'])
    key = (txt, t['font'], bool(t['bold']), bool(t['italic']), t['align'])
    if use_cache:
        hit = _cache.get(key)
        if hit is not None:
            return hit
    f = _font(t)
    fm = QFontMetricsF(f)
    lines = txt.split('\n') or ['']
    line_h = fm.lineSpacing()
    widths = [fm.horizontalAdvance(ln) for ln in lines]
    bw = max(widths + [REF * 0.3])
    total_h = line_h * len(lines)
    path = QPainterPath()
    for i, (ln, w) in enumerate(zip(lines, widths)):
        if t['align'] == 'left':
            x = -bw / 2.0
        elif t['align'] == 'right':
            x = bw / 2.0 - w
        else:
            x = -w / 2.0
        y = -total_h / 2.0 + i * line_h + fm.ascent()
        if ln:
            path.addText(QPointF(x, y), f, ln)
    res = (path, QRectF(-bw / 2.0, -total_h / 2.0, bw, total_h))
    if use_cache:
        if len(_cache) > 300:
            _cache.clear()
        _cache[key] = res
    return res


def transform(t: dict, W: float, H: float) -> QTransform:
    """Maps REF-space coordinates of the layer to image pixels of a W x H image."""
    t = normalized(t)
    s = float(t['size']) / 100.0 * H / REF
    tr = QTransform()
    tr.translate(float(t['x']) * W, float(t['y']) * H)
    tr.rotate(float(t['angle']))
    tr.scale(s, s)
    return tr


def bounds(t: dict) -> QRectF:
    """Layout box in REF space, including the background box padding (used for selection and hit tests)."""
    t = normalized(t)
    _, rect = ref_path(t)
    pad = REF * (BOX_PAD if t['box'] else 0.06)
    return rect.adjusted(-pad, -pad, pad, pad)


def polygon(t: dict, W: float, H: float) -> QPolygonF:
    """Corners of the layer's box in image pixels: top-left, top-right, bottom-right, bottom-left."""
    r = bounds(t)
    tr = transform(t, W, H)
    return QPolygonF([tr.map(r.topLeft()), tr.map(r.topRight()), tr.map(r.bottomRight()), tr.map(r.bottomLeft())])


def hit_test(texts, W: float, H: float, pt: QPointF) -> int:
    """Index of the top-most layer under pt (image pixels), or -1."""
    for i in range(len(texts) - 1, -1, -1):
        inv, ok = transform(texts[i], W, H).inverted()
        if ok and bounds(texts[i]).contains(inv.map(pt)):
            return i
    return -1


# --------------------------------------------------------------------------- painting
def _color(hex_str, alpha_f):
    c = QColor(hex_str)
    if not c.isValid():
        c = QColor('#ffffff')
    c.setAlphaF(max(0.0, min(1.0, alpha_f)))
    return c


def paint_text(p: QPainter, t: dict, W: float, H: float, use_cache=True):
    t = normalized(t)
    path, rect = ref_path(t, use_cache)
    op = max(0.0, min(1.0, float(t['opacity']) / 100.0))
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.setTransform(transform(t, W, H), True)
    if t['box']:
        pad = REF * BOX_PAD
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(_color(t['box_color'], float(t['box_opacity']) / 100.0 * op))
        p.drawRoundedRect(rect.adjusted(-pad, -pad, pad, pad), REF * 0.14, REF * 0.14)
    stroke_w = REF * float(t['stroke']) / 100.0 * 2.0
    if t['shadow']:
        p.save()
        p.translate(REF * SHADOW_OFF[0], REF * SHADOW_OFF[1])
        sc = _color('#000000', 0.55 * op)
        if stroke_w > 0:
            p.strokePath(path, QPen(sc, stroke_w, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                                    Qt.PenJoinStyle.RoundJoin))
        p.fillPath(path, sc)
        p.restore()
    if stroke_w > 0:
        p.strokePath(path, QPen(_color(t['stroke_color'], op), stroke_w, Qt.PenStyle.SolidLine,
                                Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    p.fillPath(path, _color(t['color'], op))
    p.restore()


def paint_texts(p: QPainter, texts, W: float, H: float, use_cache=True):
    for t in texts or ():
        if not is_blank(t):
            paint_text(p, t, W, H, use_cache)


def render_onto_pil(im, texts):
    """Return a copy of a PIL image with the text layers painted at its full resolution."""
    texts = [t for t in (texts or []) if not is_blank(t)]
    if not texts:
        return im
    from PIL import Image
    has_alpha = 'A' in im.getbands()
    src = im.convert('RGBA' if has_alpha else 'RGB')
    w, h = src.size
    data = src.tobytes()
    fmt = QImage.Format.Format_RGBA8888 if has_alpha else QImage.Format.Format_RGB888
    qi = QImage(data, w, h, w * (4 if has_alpha else 3), fmt)
    qi = qi.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied if has_alpha else QImage.Format.Format_RGB32)
    del data
    p = QPainter(qi)
    paint_texts(p, texts, w, h, use_cache=False)   # may run in a worker thread: no shared cache
    p.end()
    out_fmt = QImage.Format.Format_RGBA8888 if has_alpha else QImage.Format.Format_RGB888
    qi = qi.convertToFormat(out_fmt)
    mode = 'RGBA' if has_alpha else 'RGB'
    buf = bytes(qi.constBits())
    res = Image.frombuffer(mode, (w, h), buf, 'raw', mode, qi.bytesPerLine(), 1)
    return res.copy()
