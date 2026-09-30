"""纯标准库项目图标生成器（无 PIL 依赖，可打包进 exe）。

生成 iOS 风格项目图标：圆角方块 + 类型渐变背景 + 顶部玻璃高光 + 白色几何符号。
内部以 2 倍分辨率绘制后盒式降采样，得到平滑抗锯齿边缘。
"""
from __future__ import annotations

import math
import struct
import zlib

TYPE_GRADIENTS = {
    "软件": ((0x4F, 0x6E, 0xF7), (0x8B, 0x5C, 0xF6)),
    "网站": ((0x06, 0xB6, 0xD4), (0x3B, 0x82, 0xF6)),
    "游戏": ((0xA8, 0x55, 0xF7), (0xEC, 0x48, 0x99)),
    "PPT": ((0xF9, 0x73, 0x16), (0xF4, 0x3F, 0x5E)),
    "文稿": ((0x14, 0xB8, 0xA6), (0x22, 0xC5, 0x55)),
    "脚本": ((0x22, 0xC5, 0x55), (0x84, 0xCC, 0x16)),
    "其他": ((0x64, 0x74, 0x8B), (0x94, 0xA3, 0xB8)),
    "文档加工": ((0x0E, 0xA5, 0xC9), (0x38, 0xBD, 0xF8)),
    "资料系统": ((0x5E, 0x5C, 0xE6), (0x7C, 0x3A, 0xED)),
    "本地应用": ((0xB4, 0x53, 0x09), (0xF5, 0x9E, 0x0B)),
    "克隆仓库": ((0x47, 0x55, 0x69), (0x64, 0x74, 0x8B)),
    "工具脚本": ((0x65, 0xA3, 0x0D), (0xA3, 0xE6, 0x35)),
}
DEFAULT_GRADIENT = TYPE_GRADIENTS["其他"]

TYPE_SYMBOL = {
    "软件": 0, "网站": 1, "游戏": 2, "PPT": 3, "文稿": 4, "脚本": 5, "其他": 6,
    "文档加工": 9, "资料系统": 6, "本地应用": 8, "克隆仓库": 7, "工具脚本": 5,
}
SYMBOL_NAMES = ["播放", "地球", "手柄", "图表", "文档", "终端", "菱形", "星星", "齿轮", "书本", "相机", "音符"]


def _png_chunk(tag: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)


def _encode_png(width: int, height: int, rgba: bytes) -> bytes:
    raw = bytearray()
    stride = width * 4
    for y in range(height):
        raw.append(0)  # filter: None
        raw += rgba[y * stride:(y + 1) * stride]
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + _png_chunk(b"IHDR", ihdr)
            + _png_chunk(b"IDAT", zlib.compress(bytes(raw), 9))
            + _png_chunk(b"IEND", b""))


def _in_polygon(px: float, py: float, poly: list[tuple[float, float]]) -> bool:
    inside = False
    n = len(poly)
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if (yi > py) != (yj > py) and px < (xj - xi) * (py - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def _fill_poly(alpha: bytearray, w: int, h: int, poly: list[tuple[float, float]], val: int) -> None:
    if len(poly) < 3:
        return
    for y in range(h):
        row = y * w
        for x in range(w):
            if _in_polygon(x + 0.5, y + 0.5, poly):
                alpha[row + x] = max(alpha[row + x], val)


def _fill_circle(alpha: bytearray, w: int, h: int, cx: float, cy: float, r: float, val: int) -> None:
    x0, x1 = max(0, int(cx - r - 1)), min(w - 1, int(cx + r + 1))
    y0, y1 = max(0, int(cy - r - 1)), min(h - 1, int(cy + r + 1))
    r2 = r * r
    for y in range(y0, y1 + 1):
        dy = y + 0.5 - cy
        row = y * w
        for x in range(x0, x1 + 1):
            dx = x + 0.5 - cx
            if dx * dx + dy * dy <= r2:
                alpha[row + x] = max(alpha[row + x], val)


def _fill_ring(alpha: bytearray, w: int, h: int, cx: float, cy: float, r: float, thick: float, val: int) -> None:
    x0, x1 = max(0, int(cx - r - 1)), min(w - 1, int(cx + r + 1))
    y0, y1 = max(0, int(cy - r - 1)), min(h - 1, int(cy + r + 1))
    r2 = r * r
    ri = r - thick
    ri2 = ri * ri
    for y in range(y0, y1 + 1):
        dy = y + 0.5 - cy
        row = y * w
        for x in range(x0, x1 + 1):
            dx = x + 0.5 - cx
            d2 = dx * dx + dy * dy
            if r2 >= d2 >= ri2:
                alpha[row + x] = max(alpha[row + x], val)


def _fill_rect(alpha: bytearray, w: int, h: int, x0: int, y0: int, x1: int, y1: int, val: int) -> None:
    x0, x1 = max(0, x0), min(w - 1, x1)
    y0, y1 = max(0, y0), min(h - 1, y1)
    for y in range(y0, y1 + 1):
        row = y * w
        for x in range(x0, x1 + 1):
            alpha[row + x] = max(alpha[row + x], val)


def _fill_round_rect(alpha: bytearray, w: int, h: int, x0: int, y0: int, x1: int, y1: int, r: float, val: int) -> None:
    x0, x1 = max(0, x0), min(w - 1, x1)
    y0, y1 = max(0, y0), min(h - 1, y1)
    for y in range(y0, y1 + 1):
        row = y * w
        for x in range(x0, x1 + 1):
            cx = min(max(x + 0.5, x0 + r), x1 - r)
            cy = min(max(y + 0.5, y0 + r), y1 - r)
            dx, dy = (x + 0.5 - cx), (y + 0.5 - cy)
            inside = (abs(dx) <= r or abs(dy) <= r)
            if inside:
                alpha[row + x] = max(alpha[row + x], val)


def _fill_line(alpha: bytearray, w: int, h: int, x0: float, y0: float, x1: float, y1: float, thick: float, val: int) -> None:
    xa, xb = max(0, int(min(x0, x1) - thick - 1)), min(w - 1, int(max(x0, x1) + thick + 1))
    ya, yb = max(0, int(min(y0, y1) - thick - 1)), min(h - 1, int(max(y0, y1) + thick + 1))
    dx, dy = x1 - x0, y1 - y0
    length_sq = dx * dx + dy * dy or 1.0
    t2 = thick * thick
    for y in range(ya, yb + 1):
        row = y * w
        for x in range(xa, xb + 1):
            px, py = x + 0.5, y + 0.5
            t = ((px - x0) * dx + (py - y0) * dy) / length_sq
            t = max(0.0, min(1.0, t))
            qx, qy = px - (x0 + t * dx), py - (y0 + t * dy)
            if qx * qx + qy * qy <= t2:
                alpha[row + x] = max(alpha[row + x], val)


# ---------- 符号（在 WxH 网格上画白色 alpha） ----------

def _symbol_play(a, w, h, s):
    cx, cy = w / 2, h / 2
    r = s * 0.30
    _fill_poly(a, w, h, [(cx - r * 0.55, cy - r), (cx - r * 0.55, cy + r), (cx + r * 0.95, cy)], 255)


def _symbol_globe(a, w, h, s):
    cx, cy = w / 2, h / 2
    r = s * 0.32
    _fill_ring(a, w, h, cx, cy, r, s * 0.10, 255)
    _fill_line(a, w, h, cx - r, cy, cx + r, cy, s * 0.10, 255)
    _fill_line(a, w, h, cx, cy - r, cx, cy + r, s * 0.10, 255)
    _fill_line(a, w, h, cx - r * 0.62, cy - r * 0.72, cx + r * 0.62, cy + r * 0.72, s * 0.10, 255)
    _fill_line(a, w, h, cx + r * 0.62, cy - r * 0.72, cx - r * 0.62, cy + r * 0.72, s * 0.10, 255)


def _symbol_gamepad(a, w, h, s):
    cx, cy = w / 2, h / 2
    bw, bh = s * 0.66, s * 0.40
    _fill_round_rect(a, w, h, int(cx - bw / 2), int(cy - bh / 2), int(cx + bw / 2), int(cy + bh / 2), s * 0.10, 255)
    _fill_circle(a, w, h, cx, cy, s * 0.13, 255)
    _fill_circle(a, w, h, cx - bw / 2 + s * 0.16, cy, s * 0.06, 255)
    _fill_circle(a, w, h, cx + bw / 2 - s * 0.16, cy, s * 0.06, 255)
    _fill_circle(a, w, h, cx, cy - bh / 2 + s * 0.14, s * 0.06, 255)
    _fill_circle(a, w, h, cx, cy + bh / 2 - s * 0.14, s * 0.06, 255)


def _symbol_chart(a, w, h, s):
    cx, cy = w / 2, h / 2
    bw, gap = s * 0.16, s * 0.09
    heights = [0.42, 0.62, 0.84]
    for i, ht in enumerate(heights):
        bx = cx - s * 0.34 + i * (bw + gap)
        _fill_rect(a, w, h, int(bx), int(cy + s * 0.36 - s * ht), int(bx + bw), int(cy + s * 0.36), 255)


def _symbol_doc(a, w, h, s):
    cx, cy = w / 2, h / 2
    dw, dh = s * 0.46, s * 0.58
    _fill_round_rect(a, w, h, int(cx - dw / 2), int(cy - dh / 2), int(cx + dw / 2), int(cy + dh / 2), s * 0.07, 255)
    for i in range(3):
        ly = int(cy - dh / 2 + s * 0.16 + i * s * 0.14)
        _fill_rect(a, w, h, int(cx - dw / 2 + s * 0.10), ly, int(cx + dw / 2 - s * 0.10), ly + int(s * 0.05), 255)


def _symbol_terminal(a, w, h, s):
    cx, cy = w / 2, h / 2
    dw, dh = s * 0.62, s * 0.46
    _fill_round_rect(a, w, h, int(cx - dw / 2), int(cy - dh / 2), int(cx + dw / 2), int(cy + dh / 2), s * 0.08, 255)
    _fill_poly(a, w, h, [(cx - dw / 2 + s * 0.12, cy - s * 0.08), (cx - dw / 2 + s * 0.24, cy), (cx - dw / 2 + s * 0.12, cy + s * 0.08)], 255)
    _fill_rect(a, w, h, int(cx - s * 0.10), int(cy + s * 0.02), int(cx + dw / 2 - s * 0.12), int(cy + s * 0.10), 255)


def _symbol_diamond(a, w, h, s):
    cx, cy = w / 2, h / 2
    r = s * 0.34
    _fill_poly(a, w, h, [(cx, cy - r), (cx + r * 0.68, cy), (cx, cy + r), (cx - r * 0.68, cy)], 255)


def _symbol_star(a, w, h, s):
    cx, cy = w / 2, h / 2
    R, r = s * 0.38, s * 0.16
    pts = []
    for i in range(10):
        ang = -math.pi / 2 + i * math.pi / 5
        rad = R if i % 2 == 0 else r
        pts.append((cx + rad * math.cos(ang), cy + rad * math.sin(ang)))
    _fill_poly(a, w, h, pts, 255)


def _symbol_gear(a, w, h, s):
    cx, cy = w / 2, h / 2
    R, r = s * 0.30, s * 0.13
    for i in range(8):
        ang = i * math.pi / 4
        tx, ty = cx + math.cos(ang) * (R + r) * 0.5, cy + math.sin(ang) * (R + r) * 0.5
        _fill_circle(a, w, h, tx, ty, s * 0.10, 255)
    _fill_ring(a, w, h, cx, cy, R, s * 0.16, 255)
    _fill_circle(a, w, h, cx, cy, r, 255)


def _symbol_book(a, w, h, s):
    cx, cy = w / 2, h / 2
    pw, ph = s * 0.28, s * 0.52
    _fill_round_rect(a, w, h, int(cx - pw - s * 0.04), int(cy - ph / 2), int(cx - s * 0.02), int(cy + ph / 2), s * 0.06, 255)
    _fill_round_rect(a, w, h, int(cx + s * 0.02), int(cy - ph / 2), int(cx + pw + s * 0.04), int(cy + ph / 2), s * 0.06, 255)
    _fill_line(a, w, h, cx, cy - ph / 2 + s * 0.05, cx, cy + ph / 2 - s * 0.05, s * 0.035, 255)


def _symbol_camera(a, w, h, s):
    cx, cy = w / 2, h / 2
    bw, bh = s * 0.62, s * 0.42
    _fill_round_rect(a, w, h, int(cx - bw / 2), int(cy - bh / 2), int(cx + bw / 2), int(cy + bh / 2), s * 0.07, 255)
    _fill_rect(a, w, h, int(cx - s * 0.13), int(cy - bh / 2 - s * 0.10), int(cx + s * 0.13), int(cy - bh / 2 + s * 0.02), 255)
    _fill_circle(a, w, h, cx, cy + s * 0.02, s * 0.11, 255)
    _fill_ring(a, w, h, cx, cy + s * 0.02, s * 0.115, s * 0.045, 255)


def _symbol_music(a, w, h, s):
    cx, cy = w / 2, h / 2
    _fill_circle(a, w, h, cx - s * 0.22, cy + s * 0.20, s * 0.11, 255)
    _fill_circle(a, w, h, cx + s * 0.10, cy + s * 0.26, s * 0.11, 255)
    _fill_line(a, w, h, cx - s * 0.11, cy + s * 0.20, cx - s * 0.11, cy - s * 0.28, s * 0.055, 255)
    _fill_line(a, w, h, cx + s * 0.21, cy + s * 0.26, cx + s * 0.21, cy - s * 0.22, s * 0.055, 255)
    _fill_line(a, w, h, cx - s * 0.11, cy - s * 0.28, cx + s * 0.21, cy - s * 0.22, s * 0.055, 255)


_SYMBOL_DRAWERS = [_symbol_play, _symbol_globe, _symbol_gamepad, _symbol_chart, _symbol_doc,
                   _symbol_terminal, _symbol_diamond, _symbol_star, _symbol_gear, _symbol_book,
                   _symbol_camera, _symbol_music]


def _rr_sdf(x: float, y: float, w: float, h: float, r: float) -> float:
    qx = abs(x - (w - 1) / 2) - ((w - 1) / 2 - r)
    qy = abs(y - (h - 1) / 2) - ((h - 1) / 2 - r)
    ox, oy = max(qx, 0.0), max(qy, 0.0)
    return math.hypot(ox, oy) + min(max(qx, qy), 0.0) - r


def make_logo_bytes(ptype: str = "其他", symbol: int | None = None, size: int = 512) -> bytes:
    """生成项目图标 PNG（RGBA）。ptype 决定渐变配色，symbol 指定符号下标（None=按类型默认）。"""
    size = max(64, min(1024, int(size)))
    ss = size * 2  # 超采样分辨率
    c1, c2 = TYPE_GRADIENTS.get(ptype, DEFAULT_GRADIENT)
    radius = ss * 0.225

    # 背景：圆角方块 + 垂直渐变 + 玻璃高光
    rgba = bytearray(ss * ss * 4)
    for y in range(ss):
        t = y / (ss - 1)
        r = int(c1[0] + (c2[0] - c1[0]) * t)
        g = int(c1[1] + (c2[1] - c1[1]) * t)
        b = int(c1[2] + (c2[2] - c1[2]) * t)
        row = y * ss
        for x in range(ss):
            d = _rr_sdf(x + 0.5, y + 0.5, ss, ss, radius)
            cov = 1.0 if d < -0.5 else (0.0 if d > 0.5 else 0.5 - d)
            if cov <= 0:
                continue
            # 玻璃高光：顶部 40% 叠加白色，越靠上越亮
            gloss = 0.0
            if y < ss * 0.42:
                gloss = (0.5 - y / (ss * 0.84)) * 0.16
            a = int(255 * cov)
            idx = row * 4 + x * 4
            rgba[idx] = min(255, int(r + (255 - r) * gloss))
            rgba[idx + 1] = min(255, int(g + (255 - g) * gloss))
            rgba[idx + 2] = min(255, int(b + (255 - b) * gloss))
            rgba[idx + 3] = a

    # 白色符号层
    alpha = bytearray(ss * ss)
    if symbol is None:
        symbol = TYPE_SYMBOL.get(ptype, 6)
    symbol = max(0, min(len(_SYMBOL_DRAWERS) - 1, int(symbol)))
    _SYMBOL_DRAWERS[symbol](alpha, ss, ss, float(ss))
    # 把符号绘制结果裁剪到中央区域并按背景 alpha 合成
    white = bytearray(ss * ss * 4)
    for y in range(ss):
        row = y * ss
        for x in range(ss):
            av = alpha[row + x]
            if not av:
                continue
            idx = row * 4 + x * 4
            white[idx] = 255
            white[idx + 1] = 255
            white[idx + 2] = 255
            white[idx + 3] = av
    # 合成：white over rgba
    out = bytearray(ss * ss * 4)
    for i in range(ss * ss):
        ba = rgba[i * 4 + 3]
        fa = white[i * 4 + 3]
        if fa == 0:
            out[i * 4:i * 4 + 4] = rgba[i * 4:i * 4 + 4]
            continue
        if ba == 0:
            out[i * 4:i * 4 + 4] = white[i * 4:i * 4 + 4]
            continue
        out[i * 4 + 3] = ba
        for c in range(3):
            out[i * 4 + c] = int((white[i * 4 + c] * fa + rgba[i * 4 + c] * (255 - fa)) / 255)

    # 2x 盒式降采样
    final = bytearray(size * size * 4)
    for y in range(size):
        for x in range(size):
            r = g = b = a = 0
            for dy in range(2):
                for dx in range(2):
                    i = ((y * 2 + dy) * ss + (x * 2 + dx)) * 4
                    r += out[i]
                    g += out[i + 1]
                    b += out[i + 2]
                    a += out[i + 3]
            fi = (y * size + x) * 4
            final[fi] = r >> 2
            final[fi + 1] = g >> 2
            final[fi + 2] = b >> 2
            final[fi + 3] = a >> 2
    return _encode_png(size, size, bytes(final))
