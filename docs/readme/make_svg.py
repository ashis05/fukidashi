"""Generate the README header: a manga panel that translates itself.

    python docs/readme/make_svg.py   (needs: pip install fonttools)

Writes header.svg (1200x460) and header-mobile.svg (600x850) next to this file.
All lettering is converted to outlines with fontTools, so the SVGs render the
same everywhere (GitHub serves them as <img>, which cannot load web fonts).
Fonts: Noto Serif CJK JP Black (Japanese) and Noto Sans CJK JP Black/Bold (Latin).
Override the folder with FUKIDASHI_FONT_DIR.
"""

import math
import os
import random
from pathlib import Path

from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTCollection

HERE = Path(__file__).parent
FONT_DIR = Path(os.environ.get("FUKIDASHI_FONT_DIR", "/usr/share/fonts/noto-cjk"))

PAPER = "#f6f1e7"
INK = "#16130f"
RED = "#e63b2e"
GREY = "#8a8276"
MONO = "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace"

LOOP = 9  # seconds per animation cycle


def load(name):
    for f in TTCollection(str(FONT_DIR / name)).fonts:
        if "JP" in f["name"].getDebugName(1):
            return f
    raise SystemExit(f"no JP face in {name}")


SERIF = load("NotoSerifCJK-Black.ttc")
SANS_BLACK = load("NotoSansCJK-Black.ttc")
SANS_BOLD = load("NotoSansCJK-Bold.ttc")


def outline(font, text, size, x, y, vertical=False, tracking=0.0, anchor="start"):
    """Return (path d, advance) for text set at baseline (x, y).

    Vertical runs advance downward one em per glyph, centred on x.
    """
    gs = font.getGlyphSet()
    cmap = font.getBestCmap()
    upm = font["head"].unitsPerEm
    k = size / upm
    names = [cmap.get(ord(ch), ".notdef") for ch in text]
    widths = [gs[n].width * k + tracking for n in names]
    total = sum(widths) - (tracking if names else 0)
    if not vertical and anchor == "middle":
        x -= total / 2
    elif not vertical and anchor == "end":
        x -= total
    pen = SVGPathPen(gs, ntos=lambda v: f"{v:.1f}")
    cx, cy = x, y
    for n, w in zip(names, widths):
        if vertical:
            # centre each glyph on the column, top of em box at cy
            gx = cx - gs[n].width * k / 2
            gy = cy + size * 0.88
            gs[n].draw(TransformPen(pen, (k, 0, 0, -k, gx, gy)))
            cy += size * 1.02
        else:
            gs[n].draw(TransformPen(pen, (k, 0, 0, -k, cx, cy)))
            cx += w
    return pen.getCommands(), (cy - y if vertical else total)


def path(d, fill=INK, cls=None, extra=""):
    c = f' class="{cls}"' if cls else ""
    return f'<path{c} d="{d}" fill="{fill}"{extra}/>'


def speed_lines(cx, cy, r_in, r_out, n, seed):
    rnd = random.Random(seed)
    out = []
    for i in range(n):
        a = (i / n) * math.tau + rnd.uniform(-0.02, 0.02)
        r0 = r_in + rnd.uniform(0, 40)
        w = rnd.uniform(0.6, 2.6)
        x0, y0 = cx + math.cos(a) * r0, cy + math.sin(a) * r0
        x1, y1 = cx + math.cos(a - w / 400) * r_out, cy + math.sin(a - w / 400) * r_out
        x2, y2 = cx + math.cos(a + w / 400) * r_out, cy + math.sin(a + w / 400) * r_out
        out.append(f"M{x0:.1f} {y0:.1f}L{x1:.1f} {y1:.1f}L{x2:.1f} {y2:.1f}Z")
    return " ".join(out)


def panel(ox, oy, w, h):
    """The manga panel: speed lines, screentone, a bubble that gets translated."""
    cx, cy = ox + w * 0.5, oy + h * 0.5
    bw, bh = min(w * 0.34, 190), min(h * 0.40, 150)  # bubble radii
    s = []
    s.append(f'<clipPath id="pc"><rect x="{ox}" y="{oy}" width="{w}" height="{h}"/></clipPath>')
    s.append(f'<g clip-path="url(#pc)">')
    s.append(f'<rect x="{ox}" y="{oy}" width="{w}" height="{h}" fill="url(#tone)"/>')
    s.append(f'<path d="{speed_lines(cx, cy, bw * 0.9, max(w, h), 150, 7)}" fill="{INK}"/>')
    s.append("</g>")
    s.append(f'<rect x="{ox}" y="{oy}" width="{w}" height="{h}" fill="none" stroke="{INK}" stroke-width="5"/>')

    # bubble with tail
    tail = f"M{cx - bw * 0.35:.1f} {cy + bh * 0.82:.1f}L{cx - bw * 0.75:.1f} {cy + bh * 1.32:.1f}L{cx - bw * 0.05:.1f} {cy + bh * 0.95:.1f}"
    s.append(f'<path d="{tail}" fill="{PAPER}" stroke="{INK}" stroke-width="4" stroke-linejoin="round"/>')
    s.append(f'<ellipse cx="{cx}" cy="{cy}" rx="{bw}" ry="{bh}" fill="{PAPER}" stroke="{INK}" stroke-width="4"/>')
    s.append(f'<path d="M{cx - bw * 0.42:.1f} {cy + bh * 0.80:.1f}L{cx - bw * 0.02:.1f} {cy + bh * 0.93:.1f}" stroke="{PAPER}" stroke-width="6"/>')

    # Japanese, vertical, right column first: 続きが / 読みたい！
    size = bh * 0.27
    col_gap = size * 1.3
    top = cy - size * 1.02 * 2.5
    jp = []
    for i, col in enumerate(["続きが", "読みたい！"]):
        d, _ = outline(SERIF, col, size, cx + col_gap / 2 - i * col_gap, top, vertical=True)
        jp.append(d)
    s.append(path(" ".join(jp), cls="jp"))

    # detection box around the text
    bx0, by0 = cx - col_gap - size * 0.15, top - size * 0.2
    bx0 = cx - col_gap - size * 0.2
    bx1, by1 = cx + col_gap + size * 0.2, top + size * 5.3
    per = 2 * ((bx1 - bx0) + (by1 - by0))
    s.append(
        f'<rect class="det" x="{bx0:.1f}" y="{by0:.1f}" width="{bx1 - bx0:.1f}" height="{by1 - by0:.1f}" '
        f'fill="none" stroke="{RED}" stroke-width="2.5" stroke-dasharray="{per:.0f}" stroke-dashoffset="{per:.0f}" style="--per:{per:.0f}"/>'
    )
    lbl = f'<g class="tag"><rect x="{bx0:.1f}" y="{by0 - 22:.1f}" width="132" height="20" fill="{RED}"/>'
    lbl += f'<text x="{bx0 + 6:.1f}" y="{by0 - 8:.1f}" font-family="{MONO}" font-size="12" fill="{PAPER}">text_bubble 0.96</text></g>'
    s.append(lbl)
    # OCR scan line
    s.append(f'<rect class="scan" x="{bx0:.1f}" y="{by0:.1f}" width="{bx1 - bx0:.1f}" height="3" fill="{RED}" opacity="0"/>')

    # English lettering, uppercase like manga lettering
    en = ["I HAVE TO", "READ WHAT", "HAPPENS", "NEXT!"]
    esz = bh * 0.205
    lh = esz * 1.18
    y0 = cy - lh * (len(en) - 1) / 2 + esz * 0.36
    ed = [outline(SANS_BLACK, line, esz, cx, y0 + i * lh, anchor="middle", tracking=0.4)[0] for i, line in enumerate(en)]
    s.append(path(" ".join(ed), cls="en"))
    return "\n".join(s)


STEPS = [
    ("01", "DETECT", "RT-DETR finds bubbles"),
    ("02", "READ", "manga-ocr reads them"),
    ("03", "TRANSLATE", "Gemini, or Google Translate"),
    ("04", "DRAW", "English over each bubble"),
]


def steps(x, y, w, vertical):
    s = []
    if True:  # 2x2 grid reads better than four cramped columns
        cw, ch = w / 2, 62
        for i, (n, t, sub) in enumerate(STEPS):
            sx, sy = x + (i % 2) * cw, y + (i // 2) * ch
            s.append(step(sx, sy, cw - 14, i, n, t, sub))
    else:
        cw = w / 4
        for i, (n, t, sub) in enumerate(STEPS):
            s.append(step(x + i * cw, y, cw - 12, i, n, t, sub))
    return "\n".join(s)


def step(x, y, w, i, n, t, sub):
    d, _ = outline(SANS_BLACK, t, 17, x + 34, y + 19, tracking=0.6)
    return (
        f'<g class="st st{i}"><rect class="nb" x="{x}" y="{y}" width="26" height="26" fill="{PAPER}" stroke="{INK}" stroke-width="2"/>'
        f'<text class="nt" x="{x + 13}" y="{y + 18}" text-anchor="middle" font-family="{MONO}" font-size="12" font-weight="700" fill="{INK}">{n}</text>'
        f'{path(d)}'
        f'<text x="{x}" y="{y + 46}" font-family="{MONO}" font-size="11.5" fill="{GREY}">{sub}</text></g>'
    )


def seal(x, y, s):
    d, _ = outline(SERIF, "吹", s * 0.72, x + s / 2, y + s * 0.10, vertical=True)
    return (
        f'<g transform="rotate(-4 {x + s / 2} {y + s / 2})"><rect x="{x}" y="{y}" width="{s}" height="{s}" rx="5" fill="{RED}"/>'
        f'<rect x="{x + 4}" y="{y + 4}" width="{s - 8}" height="{s - 8}" rx="3" fill="none" stroke="{PAPER}" stroke-width="1.5"/>'
        f'{path(d, fill=PAPER)}</g>'
    )


def style():
    # Timeline (fraction of LOOP): detect 12-24%, scan 26-40%, swap 42-48%, hold, reset 92-100%.
    return f"""<style>
.det{{animation:det {LOOP}s infinite}} .tag{{animation:tag {LOOP}s infinite}}
.scan{{animation:scan {LOOP}s infinite}} .jp{{animation:jp {LOOP}s infinite}} .en{{animation:en {LOOP}s infinite}}
.st .nb{{animation:nb {LOOP}s infinite}} .st .nt{{animation:nt {LOOP}s infinite}}
.st1 .nb,.st1 .nt{{animation-delay:{LOOP * 0.14:.2f}s}} .st2 .nb,.st2 .nt{{animation-delay:{LOOP * 0.30:.2f}s}} .st3 .nb,.st3 .nt{{animation-delay:{LOOP * 0.44:.2f}s}}
@keyframes det{{0%,10%{{stroke-dashoffset:var(--per);opacity:1}}24%,46%{{stroke-dashoffset:0;opacity:1}}52%,100%{{stroke-dashoffset:0;opacity:0}}}}
@keyframes tag{{0%,20%{{opacity:0}}24%,46%{{opacity:1}}52%,100%{{opacity:0}}}}
@keyframes scan{{0%,25%{{opacity:0;transform:translateY(0)}}27%{{opacity:.85}}40%{{opacity:.85;transform:translateY(var(--scan))}}41%,100%{{opacity:0;transform:translateY(var(--scan))}}}}
@keyframes jp{{0%,42%{{opacity:1}}48%,92%{{opacity:0}}98%,100%{{opacity:1}}}}
@keyframes en{{0%,44%{{opacity:0}}50%,90%{{opacity:1}}96%,100%{{opacity:0}}}}
@keyframes nb{{0%,10%{{fill:{PAPER}}}12%,30%{{fill:{RED}}}36%,100%{{fill:{PAPER}}}}}
@keyframes nt{{0%,10%{{fill:{INK}}}12%,30%{{fill:{PAPER}}}36%,100%{{fill:{INK}}}}}
@media (prefers-reduced-motion:reduce){{.det,.tag,.scan,.jp,.st .nb,.st .nt{{animation:none}}.jp,.tag,.det{{opacity:0}}.en{{animation:none;opacity:1}}}}
</style>"""


def defs():
    return (
        f'<defs><pattern id="tone" width="7" height="7" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">'
        f'<circle cx="3.5" cy="3.5" r="1.25" fill="{INK}" opacity=".5"/></pattern></defs>'
    )


def build(mobile):
    W, H = (600, 850) if mobile else (1200, 460)
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" '
         f'aria-label="Fukidashi: a manga speech bubble reading 続きが読みたい！ is detected, read and replaced with I HAVE TO READ WHAT HAPPENS NEXT!">']
    o.append(defs())
    o.append(f'<rect width="{W}" height="{H}" fill="{PAPER}"/>')

    if mobile:
        px, py, pw, ph = 28, 28, W - 56, 380
        tx, ty = 28, 470
    else:
        px, py, pw, ph = 36, 36, 520, H - 72
        tx, ty = 610, 70
    o.append(panel(px, py, pw, ph))

    # scan travel distance depends on the bubble size; expose it to CSS
    bh = min(ph * 0.40, 150)
    size = bh * 0.27
    o.append(style().replace("var(--scan)", f"{size * 5.5:.0f}px"))

    # wordmark block
    o.append(f'<text x="{tx}" y="{ty}" font-family="{MONO}" font-size="13" fill="{GREY}" letter-spacing="1">吹き出し · fukidashi · n. speech bubble</text>')
    wsz = 74 if mobile else 92
    d, wlen = outline(SANS_BLACK, "FUKIDASHI", wsz, tx - 3, ty + wsz * 0.98, tracking=-1)
    o.append(path(d))
    o.append(f'<rect x="{tx}" y="{ty + wsz * 1.12:.0f}" width="{wlen:.0f}" height="6" fill="{RED}"/>')
    tag_y = ty + wsz * 1.12 + 44
    for i, line in enumerate(["Raw manga, translated on the page", "you are already reading."]):
        d, _ = outline(SANS_BOLD, line, 25 if mobile else 27, tx, tag_y + i * 36)
        o.append(path(d))
    sy = tag_y + 36 + 40
    o.append(steps(tx, sy, W - tx - 28 if mobile else W - tx - 36, mobile))

    foot_y = H - (26 if mobile else 30)
    o.append(f'<text x="{tx}" y="{foot_y}" font-family="{MONO}" font-size="12" fill="{GREY}">Chrome extension (MV3) · FastAPI · PyTorch · runs on your own GPU</text>')
    o.append(seal(W - (96 if mobile else 104), (ty - 34) if mobile else (sy + 8), 62))
    o.append("</svg>")
    return "\n".join(o)


if __name__ == "__main__":
    for mobile, name in [(False, "header.svg"), (True, "header-mobile.svg")]:
        (HERE / name).write_text(build(mobile), encoding="utf-8")
        print("wrote", HERE / name, f"{(HERE / name).stat().st_size / 1024:.0f} KB")
