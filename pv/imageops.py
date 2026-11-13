"""Non-destructive image adjustment pipeline (numpy + Pillow).

All tone/colour work happens on float32 RGB arrays in the 0..1 range.  Geometry
(orientation, straighten, crop) is applied to a PIL image before the pipeline so
the same parameters can be rendered on a small preview proxy or the full image.
"""
from __future__ import annotations

import copy
import math

import numpy as np
from PIL import Image

LUMA = np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)
LUT_N = 4096

HSL_CENTERS = [0, 30, 60, 120, 180, 240, 270, 300]
HSL_NAMES = ['紅色', '橙色', '黃色', '綠色', '青色', '藍色', '紫色', '洋紅']
BW_CENTERS = [0, 60, 120, 180, 240, 300]
BW_NAMES = ['紅色', '黃色', '綠色', '青色', '藍色', '洋紅']

ID_LEVELS = [0, 1.0, 255, 0, 255]           # in_black, gamma, in_white, out_black, out_white
ID_CURVE = [[0, 0], [255, 255]]
CHANNELS = ('rgb', 'r', 'g', 'b')

DEFAULTS = {
    # lighting
    'exposure': 0.0, 'brightness': 0, 'contrast': 0, 'highlights': 0, 'shadows': 0,
    'whites': 0, 'blacks': 0, 'clarity': 0, 'dehaze': 0,
    # levels / curves
    'levels': {c: list(ID_LEVELS) for c in CHANNELS},
    'curves': {c: [list(p) for p in ID_CURVE] for c in CHANNELS},
    # colour
    'temperature': 0, 'tint': 0, 'vibrance': 0, 'saturation': 0,
    'hsl_hue': [0] * 8, 'hsl_sat': [0] * 8, 'hsl_lum': [0] * 8,
    'cb_shadows': [0, 0, 0], 'cb_midtones': [0, 0, 0], 'cb_highlights': [0, 0, 0], 'cb_preserve': True,
    'split_hi_hue': 45, 'split_hi_sat': 0, 'split_sh_hue': 215, 'split_sh_sat': 0, 'split_balance': 0,
    'bw': False, 'bw_mix': [0] * 6,
    # detail
    'sharpen_amount': 0, 'sharpen_radius': 1.0, 'noise_reduction': 0,
    # effects
    'vignette_amount': 0, 'vignette_midpoint': 50, 'vignette_feather': 50, 'grain': 0,
    # geometry
    'orient': 1, 'straighten': 0.0, 'crop': None,
}

GEOMETRY_KEYS = ('orient', 'straighten', 'crop')


def default_params() -> dict:
    return copy.deepcopy(DEFAULTS)


def merge_params(base: dict, extra: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in extra.items():
        if k not in DEFAULTS:
            continue
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            for kk, vv in v.items():
                out[k][kk] = copy.deepcopy(vv)
        else:
            out[k] = copy.deepcopy(v)
    return out


# --------------------------------------------------------------------------- helpers
def smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def luminance(img):
    return img @ LUMA


def _gauss_kernel(sigma):
    r = max(1, int(math.ceil(sigma * 3.0)))
    x = np.arange(-r, r + 1, dtype=np.float32)
    k = np.exp(-(x * x) / (2.0 * sigma * sigma))
    return (k / k.sum()).astype(np.float32), r


def _conv_sep(a, k, r):
    h, w = a.shape
    p = np.pad(a, ((0, 0), (r, r)), mode='edge')
    out = np.zeros((h, w), np.float32)
    tmp = np.empty((h, w), np.float32)
    for i, kv in enumerate(k):
        np.multiply(p[:, i:i + w], kv, out=tmp)
        out += tmp
    p = np.pad(out, ((r, r), (0, 0)), mode='edge')
    out2 = np.zeros((h, w), np.float32)
    for i, kv in enumerate(k):
        np.multiply(p[i:i + h, :], kv, out=tmp)
        out2 += tmp
    return out2


def gaussian_blur(a, sigma):
    """Gaussian blur of a 2-D float32 array. Large radii use a downscale/upscale shortcut."""
    a = np.ascontiguousarray(a, dtype=np.float32)
    if sigma < 0.3:
        return a.copy()
    if sigma <= 2.5:
        return _conv_sep(a, *_gauss_kernel(sigma))
    h, w = a.shape
    f = sigma / 1.6
    sw, sh = max(2, int(round(w / f))), max(2, int(round(h / f)))
    small = np.asarray(Image.fromarray(a).resize((sw, sh), Image.Resampling.BOX), dtype=np.float32)
    small = _conv_sep(np.ascontiguousarray(small), *_gauss_kernel(1.2))
    big = Image.fromarray(np.ascontiguousarray(small)).resize((w, h), Image.Resampling.BILINEAR)
    return np.array(big, dtype=np.float32)


def rgb_to_hsv(img):
    r, g, b = img[..., 0], img[..., 1], img[..., 2]
    mx = img.max(axis=2)
    mn = img.min(axis=2)
    d = mx - mn
    s = np.where(mx > 1e-6, d / np.maximum(mx, 1e-6), 0.0).astype(np.float32)
    dd = np.where(d > 1e-6, d, 1.0)
    rc = (mx - r) / dd
    gc = (mx - g) / dd
    bc = (mx - b) / dd
    h = np.where(r == mx, bc - gc, np.where(g == mx, 2.0 + rc - bc, 4.0 + gc - rc))
    h = (h / 6.0) % 1.0
    h = np.where(d > 1e-6, h, 0.0).astype(np.float32) * 360.0
    return h, s, mx


def hsv_to_rgb(h, s, v):
    h6 = (h % 360.0) / 60.0
    fl = np.floor(h6)
    i = fl.astype(np.int32) % 6
    f = (h6 - fl).astype(np.float32)
    p = v * (1.0 - s)
    q = v * (1.0 - s * f)
    t = v * (1.0 - s * (1.0 - f))
    r = np.choose(i, [v, q, p, p, t, v])
    g = np.choose(i, [t, v, v, q, p, p])
    b = np.choose(i, [p, p, t, v, v, q])
    return np.stack([r, g, b], axis=-1).astype(np.float32)


def hue_sat(img):
    """Fast HSV hue (degrees), saturation and value of an RGB float image."""
    r, g, b = img[..., 0], img[..., 1], img[..., 2]
    mx = np.maximum(np.maximum(r, g), b)
    mn = np.minimum(np.minimum(r, g), b)
    d = mx - mn
    inv = 1.0 / np.maximum(d, 1e-6)
    h = np.where(mx == r, (g - b) * inv, np.where(mx == g, (b - r) * inv + 2.0, (r - g) * inv + 4.0))
    h = (h * 60.0) % 360.0
    h *= (d >= 1e-6)
    s = d / np.maximum(mx, 1e-6)
    return h.astype(np.float32, copy=False), s.astype(np.float32, copy=False), mx


def hsv_to_rgb_fast(h, s, v):
    out = np.empty(h.shape + (3,), np.float32)
    vs = v * s
    h6 = h / 60.0
    for c, n in enumerate((5.0, 3.0, 1.0)):
        k = (n + h6) % 6.0
        t = np.minimum(np.minimum(k, 4.0 - k), 1.0)
        np.maximum(t, 0.0, out=t)
        out[..., c] = v - vs * t
    return out


def _lut_apply(Y, lut):
    idx = (np.clip(Y, 0.0, 1.0) * (LUT_N - 1) + 0.5).astype(np.int32)
    return lut[idx]


def _lut_contrast_brightness(c, b):
    x = np.linspace(0.0, 1.0, LUT_N, dtype=np.float64)
    if c:
        a = 1.0 + c * 1.6 if c > 0 else 1.0 / (1.0 - c * 1.6)
        xa = np.power(x, a)
        x = xa / (xa + np.power(1.0 - x, a) + 1e-12)
    if b:
        x = np.power(x, 2.0 ** (-b * 0.85))
    return x.astype(np.float32)


def _lut_whites_blacks(wh, bl):
    x = np.linspace(0.0, 1.0, LUT_N, dtype=np.float64)
    y = x.copy()
    if wh:
        y = y + wh * 0.25 * smoothstep(0.45, 1.0, x)
    if bl:
        y = y + bl * 0.15 * (1.0 - smoothstep(0.0, 0.45, x))
    return y.astype(np.float32)


def hue_interp(h, centers, values):
    xs = [centers[-1] - 360.0] + list(centers) + [centers[0] + 360.0]
    ys = [values[-1]] + list(values) + [values[0]]
    return np.interp(h, xs, ys).astype(np.float32)


def hue_color(hue_deg):
    """Pure hue as RGB (0..1)."""
    import colorsys
    return np.array(colorsys.hsv_to_rgb((hue_deg % 360) / 360.0, 1.0, 1.0), dtype=np.float32)


# --------------------------------------------------------------------------- LUTs
def levels_lut(lv):
    ib, gamma, iw, ob, ow = lv
    x = np.linspace(0.0, 1.0, LUT_N, dtype=np.float32)
    ib, iw = ib / 255.0, iw / 255.0
    if iw <= ib + 1e-3:
        iw = ib + 1e-3
    t = np.clip((x - ib) / (iw - ib), 0.0, 1.0)
    t = np.power(t, 1.0 / max(0.05, gamma))
    return (ob / 255.0 + t * (ow - ob) / 255.0).astype(np.float32)


def _pchip_slopes(xs, ys):
    n = len(xs)
    h = np.diff(xs)
    d = np.diff(ys) / h
    m = np.zeros(n)
    if n == 2:
        m[:] = d[0]
        return m, h, d
    for k in range(1, n - 1):
        if d[k - 1] * d[k] <= 0:
            m[k] = 0.0
        else:
            w1 = 2 * h[k] + h[k - 1]
            w2 = h[k] + 2 * h[k - 1]
            m[k] = (w1 + w2) / (w1 / d[k - 1] + w2 / d[k])

    def end(h0, h1, d0, d1):
        v = ((2 * h0 + h1) * d0 - h0 * d1) / (h0 + h1)
        if np.sign(v) != np.sign(d0):
            v = 0.0
        elif np.sign(d0) != np.sign(d1) and abs(v) > abs(3 * d0):
            v = 3 * d0
        return v

    m[0] = end(h[0], h[1], d[0], d[1])
    m[-1] = end(h[-1], h[-2], d[-1], d[-2])
    return m, h, d


def curve_eval(points, x):
    """Monotone cubic (PCHIP) curve through points [(x,y) in 0..255]; x in 0..1. Returns 0..1."""
    pts = sorted((float(p[0]), float(p[1])) for p in points)
    xs = np.array([p[0] for p in pts]) / 255.0
    ys = np.array([p[1] for p in pts]) / 255.0
    keep = np.concatenate([[True], np.diff(xs) > 1e-6])
    xs, ys = xs[keep], ys[keep]
    if len(xs) == 1:
        return np.full_like(x, ys[0], dtype=np.float32)
    m, h, _ = _pchip_slopes(xs, ys)
    xc = np.clip(x, xs[0], xs[-1])
    idx = np.clip(np.searchsorted(xs, xc) - 1, 0, len(xs) - 2)
    hh = h[idx]
    t = (xc - xs[idx]) / hh
    t2, t3 = t * t, t * t * t
    y = ((2 * t3 - 3 * t2 + 1) * ys[idx] + (t3 - 2 * t2 + t) * hh * m[idx]
         + (-2 * t3 + 3 * t2) * ys[idx + 1] + (t3 - t2) * hh * m[idx + 1])
    return np.clip(y, 0.0, 1.0).astype(np.float32)


def curve_lut(points):
    return curve_eval(points, np.linspace(0.0, 1.0, LUT_N, dtype=np.float32))


def _is_id_levels(lv):
    return list(lv) == ID_LEVELS or (lv[0] == 0 and abs(lv[1] - 1.0) < 1e-6 and lv[2] == 255
                                     and lv[3] == 0 and lv[4] == 255)


def _is_id_curve(pts):
    return [list(map(float, p)) for p in pts] == [[0.0, 0.0], [255.0, 255.0]]


def build_luts(p):
    lv, cv = p['levels'], p['curves']
    if all(_is_id_levels(lv[c]) for c in CHANNELS) and all(_is_id_curve(cv[c]) for c in CHANNELS):
        return None
    x = np.linspace(0.0, 1.0, LUT_N, dtype=np.float32)
    master = x
    if not _is_id_levels(lv['rgb']):
        master = levels_lut(lv['rgb'])
    if not _is_id_curve(cv['rgb']):
        master = curve_eval(cv['rgb'], master)
    luts = []
    for c in ('r', 'g', 'b'):
        lut = master
        if not _is_id_levels(lv[c]):
            lut = np.interp(lut, x, levels_lut(lv[c])).astype(np.float32)
        if not _is_id_curve(cv[c]):
            lut = curve_eval(cv[c], lut)
        luts.append(lut.astype(np.float32))
    return luts


def apply_luts(img, luts):
    out = np.empty_like(img)
    for c in range(3):
        idx = np.clip(img[..., c], 0.0, 1.0)
        idx = (idx * (LUT_N - 1) + 0.5).astype(np.int32)
        out[..., c] = luts[c][idx]
    return out


# --------------------------------------------------------------------------- pipeline stages
def _dehaze(img, amount, diag):
    if amount > 0:
        dark = img.min(axis=2)
        dark_b = gaussian_blur(dark, diag * 0.01)
        sub = img[::8, ::8].reshape(-1, 3)
        A = np.clip(np.percentile(sub, 99.5, axis=0), 0.6, 1.0).astype(np.float32)
        t = 1.0 - amount * 0.92 * (dark_b / max(float(A.mean()), 1e-3))
        t = np.clip(t, 0.12, 1.0)[..., None]
        return ((img - A) / t + A).astype(np.float32)
    amt = -amount
    return (img * (1.0 - 0.55 * amt) + np.float32(0.55 * amt * 0.82)).astype(np.float32)


def _denoise(img, amt, scale):
    s = max(scale, 0.2)
    Y = img @ LUMA
    chroma = img - Y[..., None]
    sig_c = (1.0 + 4.0 * amt) * s
    for c in range(3):
        chroma[..., c] = gaussian_blur(chroma[..., c], sig_c)
    Yb = gaussian_blur(Y, (0.6 + 1.6 * amt) * s)
    edge = np.abs(Y - Yb)
    wgt = amt * np.clip(1.0 - edge * 14.0, 0.0, 1.0)
    Yn = Y + (Yb - Y) * wgt
    return (Yn[..., None] + chroma).astype(np.float32)


def process(src, p, scale=1.0, inplace=False, stop_at=None):
    """Apply all tone / colour / detail / effect adjustments.

    src   : float32 HxWx3 array (0..1) with geometry already applied
    scale : size of src relative to the full-resolution image (for pixel radii)
    stop_at: 'levels' returns the image right before the levels/curves stage
    """
    img = src if inplace else src.astype(np.float32, copy=True)
    h, w = img.shape[:2]
    diag = math.hypot(w, h)

    # white balance
    T, M = p['temperature'], p['tint']
    if T or M:
        g = np.array([2 ** (0.5 * T / 100.0), 2 ** (-0.5 * M / 100.0), 2 ** (-0.5 * T / 100.0)], np.float32)
        g /= float(g @ LUMA)
        img *= g

    # exposure
    if p['exposure']:
        img *= np.float32(2.0 ** p['exposure'])

    # dehaze
    if p['dehaze']:
        img = _dehaze(img, p['dehaze'] / 100.0, diag)

    # tonal adjustments in the luminance domain (hue preserving)
    tone_keys = ('contrast', 'brightness', 'highlights', 'shadows', 'whites', 'blacks', 'clarity')
    if any(p[k] for k in tone_keys):
        np.maximum(img, 0.0, out=img)
        Y = img @ LUMA
        Yt = np.clip(Y, 0.0, 1.0)
        c, b = p['contrast'] / 100.0, p['brightness'] / 100.0
        if c or b:
            Yt = _lut_apply(Yt, _lut_contrast_brightness(c, b))
        sh, hl = p['shadows'] / 100.0, p['highlights'] / 100.0
        if sh or hl:
            Yb = gaussian_blur(Yt, diag * 0.012)
            Ym = 0.5 * Yb + 0.5 * Yt
            if sh:
                k = 1.6 * abs(sh) * (1.0 - smoothstep(0.0, 0.62, Ym))
                Yt = np.power(Yt, 1.0 / (1.0 + k)) if sh > 0 else np.power(Yt, 1.0 + k)
            if hl:
                k = 1.6 * abs(hl) * smoothstep(0.38, 1.0, Ym)
                u = 1.0 - Yt
                u = np.power(u, 1.0 / (1.0 + k)) if hl < 0 else np.power(u, 1.0 + k)
                Yt = 1.0 - u
        if p['whites'] or p['blacks']:
            Yt = _lut_apply(Yt, _lut_whites_blacks(p['whites'] / 100.0, p['blacks'] / 100.0))
        if p['clarity']:
            Yb2 = gaussian_blur(np.ascontiguousarray(Yt, dtype=np.float32), diag * 0.006)
            mid = np.clip(4.0 * Yt * (1.0 - Yt), 0.0, 1.0)
            Yt = Yt + p['clarity'] / 100.0 * 1.3 * (Yt - Yb2) * (0.25 + 0.75 * mid)
        Yt = np.clip(Yt, 0.0, 1.5).astype(np.float32)
        safe = Y > 1e-3
        ratio = np.where(safe, Yt / np.maximum(Y, 1e-3), 1.0)
        np.clip(ratio, 0.0, 12.0, out=ratio)
        img *= ratio[..., None].astype(np.float32)
        img += np.where(safe, 0.0, Yt - Y)[..., None].astype(np.float32)

    if stop_at == 'levels':
        return np.clip(img, 0.0, 1.0)

    # levels + curves
    luts = build_luts(p)
    if luts is not None:
        img = apply_luts(img, luts)

    # vibrance / saturation
    vib, sat = p['vibrance'] / 100.0, p['saturation'] / 100.0
    if vib or sat:
        np.maximum(img, 0.0, out=img)
        Y = (img @ LUMA)[..., None]
        if vib:
            r_, g_, b_ = img[..., 0], img[..., 1], img[..., 2]
            mx = np.maximum(np.maximum(r_, g_), b_)
            mn = np.minimum(np.minimum(r_, g_), b_)
            s = (mx - mn) / (mx + 1e-6)
            f = 1.0 + vib * 1.2 * (1.0 - s) if vib > 0 else 1.0 + vib * (1.0 - 0.5 * s)
            img = Y + (img - Y) * f[..., None].astype(np.float32)
        if sat:
            img = Y + (img - Y) * np.float32(1.0 + sat)

    # HSL colour equaliser
    hh_v, hs_v, hl_v = p['hsl_hue'], p['hsl_sat'], p['hsl_lum']
    if any(hh_v) or any(hs_v) or any(hl_v):
        np.maximum(img, 0.0, out=img)
        H, S, V = hue_sat(img)
        if any(hh_v):
            img = hsv_to_rgb_fast(H + hue_interp(H, HSL_CENTERS, hh_v) * 0.3, S, V)
        if any(hs_v):
            f = 1.0 + hue_interp(H, HSL_CENTERS, hs_v) / 100.0
            f = np.minimum(f, 1.0 / np.maximum(S, 1e-4))
            Vc = V[..., None]
            img = Vc - (Vc - img) * f[..., None]
        if any(hl_v):
            img *= (1.0 + hue_interp(H, HSL_CENTERS, hl_v) / 100.0 * 0.6 * S)[..., None]

    # black & white
    if p['bw']:
        np.maximum(img, 0.0, out=img)
        Y = img @ LUMA
        if any(p['bw_mix']):
            H, S, _ = hue_sat(img)
            Y = Y * (1.0 + hue_interp(H, BW_CENTERS, p['bw_mix']) / 100.0 * S)
        img = np.repeat(Y[..., None], 3, axis=2).astype(np.float32)

    # colour balance
    cbs, cbm, cbh = p['cb_shadows'], p['cb_midtones'], p['cb_highlights']
    if any(cbs) or any(cbm) or any(cbh):
        Y0 = img @ LUMA
        Yc = np.clip(Y0, 0.0, 1.0)
        w_sh = 1.0 - smoothstep(0.0, 0.55, Yc)
        w_hi = smoothstep(0.45, 1.0, Yc)
        w_mid = np.clip(1.0 - w_sh - w_hi, 0.0, 1.0)

        def vec(vals):
            v = np.array(vals, np.float32) / 100.0 * 0.2
            return v - v.mean()

        delta = (w_sh[..., None] * vec(cbs) + w_mid[..., None] * vec(cbm) + w_hi[..., None] * vec(cbh))
        img = img + delta.astype(np.float32)
        if p['cb_preserve']:
            Y1 = img @ LUMA
            img *= np.where(Y1 > 1e-4, Y0 / np.maximum(Y1, 1e-4), 1.0)[..., None].astype(np.float32)

    # split toning
    if p['split_hi_sat'] or p['split_sh_sat']:
        Y = np.clip(img @ LUMA, 0.0, 1.0)
        pivot = 0.5 - p['split_balance'] / 100.0 * 0.3
        w_hi = smoothstep(pivot - 0.3, pivot + 0.3, Y)
        add = np.zeros_like(img)
        for hue, sat_, wgt in ((p['split_hi_hue'], p['split_hi_sat'], w_hi),
                               (p['split_sh_hue'], p['split_sh_sat'], 1.0 - w_hi)):
            if sat_:
                col = hue_color(hue)
                col = col - float(col @ LUMA)
                add += wgt[..., None] * (col * (sat_ / 100.0 * 0.35))
        img = img + add

    # noise reduction
    if p['noise_reduction']:
        img = _denoise(img, p['noise_reduction'] / 100.0, scale)

    # sharpen (luminance unsharp mask)
    if p['sharpen_amount']:
        Y = np.ascontiguousarray(img @ LUMA, dtype=np.float32)
        sigma = max(0.3, p['sharpen_radius'] * scale)
        det = Y - gaussian_blur(Y, sigma)
        img += (det * (p['sharpen_amount'] / 100.0 * 1.8))[..., None]

    # vignette
    va = p['vignette_amount'] / 100.0
    if va:
        yy = (np.arange(h, dtype=np.float32) - (h - 1) / 2.0) / max(1.0, (h - 1) / 2.0)
        xx = (np.arange(w, dtype=np.float32) - (w - 1) / 2.0) / max(1.0, (w - 1) / 2.0)
        d = np.sqrt(xx[None, :] ** 2 + yy[:, None] ** 2) / math.sqrt(2.0)
        r0 = 0.15 + p['vignette_midpoint'] / 100.0 * 0.75
        fe = 0.05 + p['vignette_feather'] / 100.0 * 0.9
        mask = smoothstep(r0 - fe * 0.5, r0 + fe, d).astype(np.float32)
        if va < 0:
            img *= (1.0 + va * mask)[..., None]
        else:
            img = img + (1.0 - img) * (va * mask)[..., None]

    # film grain
    if p['grain']:
        rng = np.random.default_rng(12345)
        noise = rng.standard_normal((h, w), dtype=np.float32) * (p['grain'] / 100.0 * 0.09)
        if scale > 0.6:
            noise = gaussian_blur(noise, 0.6 * scale)
        Y = np.clip(img @ LUMA, 0.0, 1.0)
        img += (noise * (0.35 + 0.65 * 4.0 * Y * (1.0 - Y)))[..., None]

    return np.clip(img, 0.0, 1.0, out=img if img.dtype == np.float32 else None).astype(np.float32, copy=False)


def to_uint8(img):
    return (img * 255.0 + 0.5).astype(np.uint8)


def histogram(u8):
    sub = u8[::2, ::2].reshape(-1, 3)
    r = np.bincount(sub[:, 0], minlength=256)
    g = np.bincount(sub[:, 1], minlength=256)
    b = np.bincount(sub[:, 2], minlength=256)
    lum = (sub[:, 0].astype(np.uint32) * 54 + sub[:, 1].astype(np.uint32) * 183
           + sub[:, 2].astype(np.uint32) * 19) >> 8
    l = np.bincount(lum, minlength=256)
    return r, g, b, l


# --------------------------------------------------------------------------- geometry
_TRANSPOSE = {2: Image.Transpose.FLIP_LEFT_RIGHT, 3: Image.Transpose.ROTATE_180,
              4: Image.Transpose.FLIP_TOP_BOTTOM, 5: Image.Transpose.TRANSPOSE,
              6: Image.Transpose.ROTATE_270, 7: Image.Transpose.TRANSVERSE, 8: Image.Transpose.ROTATE_90}


def apply_orient(im, orient):
    m = _TRANSPOSE.get(int(orient))
    return im.transpose(m) if m is not None else im


def straighten_scale(w, h, angle):
    th = math.radians(abs(angle))
    c, s = math.cos(th), math.sin(th)
    return min(w / (w * c + h * s), h / (w * s + h * c)) * 0.998


def apply_straighten(im, angle):
    if abs(angle) < 0.01:
        return im
    w, h = im.size
    sc = straighten_scale(w, h, angle)
    rot = im.rotate(-angle, resample=Image.Resampling.BICUBIC, expand=False)
    cw, ch = w * sc, h * sc
    left, top = (w - cw) / 2.0, (h - ch) / 2.0
    return rot.crop((int(round(left)), int(round(top)), int(round(left + cw)), int(round(top + ch))))


def apply_crop(im, crop):
    if not crop:
        return im
    w, h = im.size
    x0, y0, x1, y1 = crop
    box = (int(round(x0 * w)), int(round(y0 * h)), int(round(x1 * w)), int(round(y1 * h)))
    box = (min(box[0], w - 1), min(box[1], h - 1), max(box[2], box[0] + 1), max(box[3], box[1] + 1))
    return im.crop(box)


def apply_geometry(im, p, skip_crop=False):
    im = apply_orient(im, p['orient'])
    im = apply_straighten(im, p['straighten'])
    if not skip_crop:
        im = apply_crop(im, p['crop'])
    return im


def transform_rect(rect, op_matrix):
    a = op_matrix
    x0, y0, x1, y1 = rect
    pts = [(x0, y0), (x1, y0), (x0, y1), (x1, y1)]
    out = [(a[0] * (x - 0.5) + a[1] * (y - 0.5) + 0.5, a[2] * (x - 0.5) + a[3] * (y - 0.5) + 0.5) for x, y in pts]
    xs = [q[0] for q in out]
    ys = [q[1] for q in out]
    return [min(xs), min(ys), max(xs), max(ys)]


# --------------------------------------------------------------------------- auto adjustments
def auto_levels(pre):
    """Per-channel black/white points from an image sampled just before the levels stage."""
    sub = pre[::2, ::2].reshape(-1, 3)
    out = {}
    for i, c in enumerate(('r', 'g', 'b')):
        lo, hi = np.percentile(sub[:, i], [0.25, 99.75])
        lo, hi = float(lo) * 255, float(hi) * 255
        if hi - lo < 10:
            lo, hi = 0.0, 255.0
        out[c] = [int(round(lo)), 1.0, int(round(hi)), 0, 255]
    return out


def auto_contrast(pre):
    Y = (pre[::2, ::2] @ LUMA).ravel()
    lo, med, hi = np.percentile(Y, [0.3, 50, 99.7])
    if hi - lo < 0.04:
        return list(ID_LEVELS)
    m = (med - lo) / (hi - lo)
    gamma = 1.0
    if 0.02 < m < 0.98:
        gamma = float(np.clip(math.log(m) / math.log(0.46), 0.6, 1.8))
    return [int(round(lo * 255)), round(gamma, 2), int(round(hi * 255)), 0, 255]


# --------------------------------------------------------------------------- rendering
def geometry_size(w, h, p, skip_crop=False):
    """Exact output size of apply_geometry() for an input of w x h (mirrors its rounding)."""
    if int(p['orient']) in (5, 6, 7, 8):
        w, h = h, w
    angle = p['straighten']
    if abs(angle) >= 0.01:
        sc = straighten_scale(w, h, angle)
        cw, ch = w * sc, h * sc
        left, top = (w - cw) / 2.0, (h - ch) / 2.0
        w = int(round(left + cw)) - int(round(left))
        h = int(round(top + ch)) - int(round(top))
    if p['crop'] and not skip_crop:
        x0, y0, x1, y1 = p['crop']
        box = (int(round(x0 * w)), int(round(y0 * h)), int(round(x1 * w)), int(round(y1 * h)))
        box = (min(box[0], w - 1), min(box[1], h - 1), max(box[2], box[0] + 1), max(box[3], box[1] + 1))
        bx0, by0 = min(box[0], w - 1), min(box[1], h - 1)
        w, h = box[2] - bx0, box[3] - by0
    return w, h


class PreviewEngine:
    """Holds a downscaled proxy of the source and renders previews of parameter sets.

    A second, half-size proxy is used for fast feedback while a control is being dragged.
    """

    def __init__(self, full_rgb, max_side=1600):
        self.full = full_rgb
        self.max_side = max_side
        w, h = full_rgb.size
        s = min(1.0, max_side / float(max(w, h)))
        if s < 1.0:
            self.proxy = full_rgb.resize((max(1, round(w * s)), max(1, round(h * s))), Image.Resampling.LANCZOS)
        else:
            self.proxy = full_rgb.copy()
        self.scale = self.proxy.width / float(w)
        pw, ph = self.proxy.size
        self.fast = None
        if pw * ph > 1_100_000:
            self.fast = self.proxy.resize((max(1, pw // 2), max(1, ph // 2)), Image.Resampling.BOX)
        self._keys = {False: None, True: None}
        self._bases = {False: None, True: None}
        self._scales = {False: self.scale, True: self.scale}

    @property
    def base(self):
        return self._bases[False]

    def _cropped_from_full(self, p, skip_crop):
        return bool(p['crop']) and not skip_crop and self.scale < 1.0

    def logical_size(self, p, skip_crop=False):
        """Size of the full-quality preview frame for these geometry settings."""
        if self._cropped_from_full(p, skip_crop):
            w, h = geometry_size(self.full.width, self.full.height, p, False)
            s = min(1.0, self.max_side / float(max(w, h)))
            return max(1, round(w * s)), max(1, round(h * s))
        return geometry_size(self.proxy.width, self.proxy.height, p, skip_crop)

    def get_base(self, p, skip_crop=False, fast=False):
        fast = bool(fast and self.fast is not None)
        crop = None if skip_crop or not p['crop'] else tuple(round(v, 5) for v in p['crop'])
        key = (int(p['orient']), round(float(p['straighten']), 2), crop)
        if key != self._keys[fast] or self._bases[fast] is None:
            if fast:
                im = apply_geometry(self.fast, p, skip_crop)
            elif self._cropped_from_full(p, skip_crop):
                # re-sample the cropped region from the full image so cropped previews stay sharp
                im = apply_geometry(self.full, p)
                lw, lh = self.logical_size(p, skip_crop)
                if im.size != (lw, lh):
                    im = im.resize((lw, lh), Image.Resampling.LANCZOS)
            else:
                im = apply_geometry(self.proxy, p, skip_crop)
            arr = np.asarray(im, dtype=np.float32) * np.float32(1.0 / 255.0)
            self._bases[fast] = np.ascontiguousarray(arr)
            self._keys[fast] = key
            full_w = geometry_size(self.full.width, self.full.height, p, skip_crop)[0]
            self._scales[fast] = arr.shape[1] / float(max(1, full_w))
        return self._bases[fast]

    def render(self, p, skip_crop=False, fast=False):
        fast = bool(fast and self.fast is not None)
        base = self.get_base(p, skip_crop, fast)
        out = process(base, p, scale=self._scales[fast])
        u8 = to_uint8(out)
        return u8, histogram(u8), fast

    def base_scale(self):
        return self._scales[False]

    def pre_levels(self, p):
        base = self.get_base(p)
        small = base[::3, ::3]
        return process(small, p, scale=self._scales[False] / 3.0, stop_at='levels')


def render_full(full_rgb, p, alpha=None, resize_long=0):
    im = apply_geometry(full_rgb, p)
    arr = np.asarray(im, dtype=np.float32) * np.float32(1.0 / 255.0)
    del im
    out = process(np.ascontiguousarray(arr), p, scale=1.0, inplace=True)
    del arr
    res = Image.fromarray(to_uint8(out))
    del out
    if alpha is not None:
        a = apply_geometry(alpha, p)
        if a.size == res.size:
            res.putalpha(a)
    if resize_long and max(res.size) > resize_long:
        s = resize_long / float(max(res.size))
        res = res.resize((max(1, round(res.width * s)), max(1, round(res.height * s))), Image.Resampling.LANCZOS)
    return res


SAVE_FORMATS = {'.jpg': 'JPEG', '.jpeg': 'JPEG', '.jpe': 'JPEG', '.jfif': 'JPEG', '.png': 'PNG',
                '.webp': 'WEBP', '.tif': 'TIFF', '.tiff': 'TIFF', '.bmp': 'BMP'}


def save_image(res, target, exif=None, icc=None, quality=92):
    import os
    ext = os.path.splitext(target)[1].lower()
    fmt = SAVE_FORMATS.get(ext)
    if fmt is None:
        raise ValueError(f'不支援的儲存格式：{ext}')
    kw = {}
    if fmt in ('JPEG', 'BMP') and res.mode != 'RGB':
        res = res.convert('RGB')
    if fmt == 'JPEG':
        kw.update(quality=int(quality), subsampling=0 if quality >= 90 else 2, optimize=True)
    elif fmt == 'WEBP':
        kw.update(quality=int(quality), method=4)
    elif fmt == 'TIFF':
        kw['compression'] = 'tiff_lzw'
    if icc and fmt in ('JPEG', 'PNG', 'WEBP', 'TIFF'):
        kw['icc_profile'] = icc
    if exif is not None and fmt in ('JPEG', 'PNG', 'WEBP'):
        try:
            exif[0x0112] = 1
            kw['exif'] = exif.tobytes()
        except Exception:
            pass
    tmp = target + '.pvtmp'
    try:
        res.save(tmp, format=fmt, **kw)
    except Exception:
        kw.pop('exif', None)
        res.save(tmp, format=fmt, **kw)
    os.replace(tmp, target)
