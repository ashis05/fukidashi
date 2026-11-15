"""Draw translated text over speech bubbles."""
from __future__ import annotations

import functools
import os
from typing import Iterable, Sequence

from PIL import Image, ImageDraw, ImageFont

_FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/noto/NotoSans-Bold.ttf",
    "/Library/Fonts/Arial Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
    "C:\\Windows\\Fonts\\arialbd.ttf",
    "C:\\Windows\\Fonts\\arial.ttf",
]


def find_font_path(custom: str | None = None) -> str | None:
    for p in [custom or os.environ.get("FUKIDASHI_FONT", ""), *_FONT_CANDIDATES]:
        if p and os.path.isfile(p):
            return p
    return None


@functools.lru_cache(maxsize=128)
def get_font(size: int, path: str | None = None):
    size = max(1, int(size))
    p = path if path else find_font_path()
    if p:
        try:
            return ImageFont.truetype(p, size)
        except OSError:
            pass
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # Pillow < 10.1: fixed-size bitmap font
        return ImageFont.load_default()


def _width(font, text: str) -> float:
    if hasattr(font, "getlength"):
        return font.getlength(text)
    return font.getbbox(text)[2]


def wrap_text(text: str, font, max_width: float) -> list[str]:
    """Greedy word wrap; words longer than the width are split by character."""
    lines: list[str] = []
    for para in text.split("\n"):
        cur = ""
        for word in para.split():
            while _width(font, word) > max_width and len(word) > 1:
                # break an overlong word
                n = len(word)
                while n > 1 and _width(font, word[:n]) > max_width:
                    n -= 1
                if cur:
                    lines.append(cur)
                    cur = ""
                lines.append(word[:n])
                word = word[n:]
            trial = f"{cur} {word}".strip()
            if cur and _width(font, trial) > max_width:
                lines.append(cur)
                cur = word
            else:
                cur = trial
        lines.append(cur)
    return lines or [""]


def _line_height(font) -> int:
    l, t, r, b = font.getbbox("Ag")
    return int((b - t) * 1.2) + 1


def fit_text(text: str, box_w: float, box_h: float, font_path: str | None = None,
             max_size: int = 40, min_size: int = 8):
    """Find the biggest font size whose wrapped text fits. Returns (font, lines, fits)."""
    lo, hi = min_size, max(min_size, int(min(max_size, box_h)))
    best = None
    while lo <= hi:
        mid = (lo + hi) // 2
        font = get_font(mid, font_path)
        lines = wrap_text(text, font, box_w)
        if len(lines) * _line_height(font) <= box_h and all(_width(font, l) <= box_w + 0.5 for l in lines):
            best = (font, lines)
            lo = mid + 1
        else:
            hi = mid - 1
    if best:
        return best[0], best[1], True
    font = get_font(min_size, font_path)
    return font, wrap_text(text, font, box_w), False


def draw_translations(
    image: Image.Image,
    items: Iterable[tuple[Sequence[int], str]],
    font_path: str | None = None,
    padding_ratio: float = 0.08,
) -> Image.Image:
    """Return a copy of `image` with each (box, text) painted white with centered wrapped text."""
    out = image.convert("RGB").copy()
    draw = ImageDraw.Draw(out)
    for box, text in items:
        x1, y1, x2, y2 = (int(v) for v in box)
        w, h = x2 - x1, y2 - y1
        if w < 4 or h < 4:
            continue
        radius = max(2, int(min(w, h) * 0.2))
        draw.rounded_rectangle([x1, y1, x2, y2], radius=radius, fill="white")
        if not text:
            continue
        pad = max(2, int(min(w, h) * padding_ratio))
        # an inscribed ellipse's text area is ~70% of the box; use a bit less padding on big boxes
        inner_w, inner_h = max(1, w - 2 * pad - radius // 2), max(1, h - 2 * pad - radius // 2)
        font, lines, _ = fit_text(text, inner_w, inner_h, font_path)
        lh = _line_height(font)
        y = y1 + (h - lh * len(lines)) / 2
        for line in lines:
            lw = _width(font, line)
            draw.text((x1 + (w - lw) / 2, y), line, fill="black", font=font)
            y += lh
    return out
