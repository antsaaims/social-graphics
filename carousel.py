"""
Carousel template: one idea per slide, bold capitals + a handwritten accent phrase,
and hand-drawn arrows that cross the edge between slides so readers keep swiping.

The whole carousel is drawn on one wide canvas (slides side by side) and then cut into
slides, so every arrow that leaves one slide continues on the next.

Slide types (a queue item with "format": "carousel" has a "slides" list):
    {"type": "cover", "title": "Handwritten title", "subtitle": "BOLD LINE UNDER IT"}
    {"type": "point", "headline": "BOLD CAPS LINE", "accent": "handwritten words",
     "body": "Regular text.", "kicker": "Bold closing line."}          # body/kicker optional
    {"type": "end", "quote": "Closing line in handwriting", "cta": "Optional small line"}
Optional on any slide: "background": path (in the repo) or https URL of a photo; it gets a navy overlay.
"""

import io
import math
import os
import urllib.request

from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
FONTS = os.path.join(HERE, "fonts")

NAVY = (10, 25, 47)
GOLD = (244, 211, 94)
SKY = (56, 189, 248)
WHITE = (255, 255, 255)
SOFT = (214, 224, 238)

W, H = 1080, 1350          # 4:5 portrait, the carousel shape Instagram and Facebook display largest
M = 96                     # side margin
SS = 2                     # supersampling for smooth hand-drawn strokes

CAPS = os.path.join(FONTS, "Inter-ExtraBold.otf")
BODY = os.path.join(FONTS, "Inter-Regular.otf")
BOLD = os.path.join(FONTS, "Inter-Bold.otf")
SEMI = os.path.join(FONTS, "Inter-SemiBold.otf")
HAND = os.path.join(FONTS, "CaveatBrush-Regular.ttf")


def font(path, size):
    return ImageFont.truetype(path, int(size))


def wrap(text, fnt, max_w):
    out = []
    for para in text.split("\n"):
        cur = ""
        for word in para.split():
            t = f"{cur} {word}".strip()
            if fnt.getlength(t) <= max_w or not cur:
                cur = t
            else:
                out.append(cur)
                cur = word
        out.append(cur)
    return out


def fit_lines(text, path, max_w, max_lines, start, stop):
    for size in range(start, stop - 1, -2):
        f = font(path, size)
        lines = wrap(text, f, max_w)
        if len(lines) <= max_lines and all(f.getlength(l) <= max_w for l in lines):
            return f, lines
    f = font(path, stop)
    return f, wrap(text, f, max_w)


# ---------------------------------------------------------------- background
def background(n, slides):
    """Continuous navy gradient with soft out-of-focus circles, or per-slide photos under a navy overlay."""
    total = W * n
    bg = Image.new("RGB", (total, H), NAVY)
    d = ImageDraw.Draw(bg)
    for y in range(H):
        t = y / H
        d.line([(0, y), (total, y)], fill=(int(14 - 6 * t), int(32 - 14 * t), int(58 - 22 * t)))
    glow = Image.new("RGBA", (total, H), (0, 0, 0, 0))
    g = ImageDraw.Draw(glow)
    # deterministic "bokeh": soft circles spread across the whole strip
    for i in range(7 * n):
        x = (i * 397) % total
        y = (i * 613) % H
        r = 40 + (i * 53) % 110
        col = (56, 189, 248, 26) if i % 3 else (244, 211, 94, 18)
        g.ellipse([(x - r, y - r), (x + r, y + r)], fill=col)
    glow = glow.filter(ImageFilter.GaussianBlur(28))
    bg = Image.alpha_composite(bg.convert("RGBA"), glow)

    for i, s in enumerate(slides):
        src = s.get("background")
        if not src:
            continue
        try:
            if src.startswith("http"):
                data = urllib.request.urlopen(src, timeout=30).read()
                photo = Image.open(io.BytesIO(data))
            else:
                photo = Image.open(os.path.join(HERE, src))
        except Exception:
            continue
        photo = photo.convert("RGB")
        scale = max(W / photo.width, H / photo.height)
        photo = photo.resize((int(photo.width * scale) + 1, int(photo.height * scale) + 1))
        left, top = (photo.width - W) // 2, (photo.height - H) // 2
        photo = photo.crop((left, top, left + W, top + H)).convert("RGBA")
        overlay = Image.new("RGBA", (W, H), NAVY + (205,))
        bg.paste(Image.alpha_composite(photo, overlay), (i * W, 0))
    return bg


# ---------------------------------------------------------------- hand-drawn strokes
def bezier(p0, p1, p2, p3, steps=240):
    pts = []
    for k in range(steps + 1):
        t = k / steps
        a = (1 - t) ** 3
        b = 3 * (1 - t) ** 2 * t
        c = 3 * (1 - t) * t ** 2
        e = t ** 3
        pts.append((a * p0[0] + b * p1[0] + c * p2[0] + e * p3[0],
                    a * p0[1] + b * p1[1] + c * p2[1] + e * p3[1]))
    return pts


def brush(layer, pts, w_start, w_end, color, wobble=3.0):
    """Tapered marker stroke along pts (already in supersampled coordinates)."""
    d = ImageDraw.Draw(layer)
    n = len(pts)
    for k, (x, y) in enumerate(pts):
        t = k / max(1, n - 1)
        w = (w_start + (w_end - w_start) * t) * SS
        # tiny wobble perpendicular to the path so it looks hand-drawn
        if 0 < k < n - 1:
            dx, dy = pts[k + 1][0] - pts[k - 1][0], pts[k + 1][1] - pts[k - 1][1]
            ln = math.hypot(dx, dy) or 1
            off = math.sin(k * 0.035) * wobble * SS
            x, y = x - dy / ln * off, y + dx / ln * off
        d.ellipse([(x - w / 2, y - w / 2), (x + w / 2, y + w / 2)], fill=color)


def arrow(layer, p0, p1, p2, p3, color, width=11, head=46):
    """Curved hand-drawn arrow from p0 to p3 (canvas coordinates) with an open arrowhead."""
    pts = bezier(*[(x * SS, y * SS) for x, y in (p0, p1, p2, p3)])
    brush(layer, pts, width * 0.55, width, color)
    (x1, y1), (x2, y2) = pts[-8], pts[-1]
    ang = math.atan2(y2 - y1, x2 - x1)
    for side in (-1, 1):
        a = ang + math.pi + side * 0.55
        hx, hy = x2 + math.cos(a) * head * SS, y2 + math.sin(a) * head * SS
        seg = [(x2 + (hx - x2) * s, y2 + (hy - y2) * s) for s in [i / 40 for i in range(41)]]
        brush(layer, seg, width, width * 0.5, color, wobble=0.6)


def swoosh(layer, p0, p1, p2, p3, color, width=12):
    """Open curve with no arrowhead (a brush swipe)."""
    pts = bezier(*[(x * SS, y * SS) for x, y in (p0, p1, p2, p3)])
    brush(layer, pts, width * 0.4, width, color)


# ---------------------------------------------------------------- slides
def draw_blocks(d, ox, blocks, top=None):
    """blocks: list of (font, lines, fill, line_gap, space_before, x_shift). Centred vertically unless top is given."""
    total = sum(b[4] + len(b[1]) * b[3] for b in blocks)
    y = top if top is not None else (H - total) // 2 - 30
    first_y = None
    for f, lines, fill, gap, before, dx in blocks:
        y += before
        if first_y is None:
            first_y = y
        for line in lines:
            d.text((ox + M + dx, y), line, font=f, fill=fill)
            y += gap
    return first_y, y


def slide_cover(d, ox, s):
    max_w = W - 2 * M - 60
    tf, tl = fit_lines(s.get("title", ""), HAND, max_w, 4, 150, 84)
    blocks = [(tf, tl, WHITE, int(tf.size * 0.98), 0, 0)]
    if s.get("subtitle"):
        sf, sl = fit_lines(s["subtitle"].upper(), CAPS, max_w, 3, 50, 34)
        blocks.append((sf, sl, GOLD, int(sf.size * 1.14), 40, 0))
    first, last = draw_blocks(d, ox, blocks)
    return {"exit": (ox + W - 330, min(last + 150, 1160))}


def slide_point(d, ox, s, layer):
    max_w = W - 2 * M - 70
    hf, hl = fit_lines(s.get("headline", "").upper(), CAPS, max_w, 3, 68, 44)
    blocks = [(hf, hl, WHITE, int(hf.size * 1.1), 0, 0)]
    if s.get("accent"):
        af, al = fit_lines(s["accent"], HAND, max_w, 2, 118, 70)
        blocks.append((af, al, GOLD, int(af.size * 0.95), -int(af.size * 0.12), 4))
    if s.get("body"):
        bf, bl = fit_lines(s["body"], BODY, max_w, 7, 44, 32)
        blocks.append((bf, bl, SOFT, int(bf.size * 1.34), 46, 0))
    if s.get("kicker"):
        kf, kl = fit_lines(s["kicker"], BOLD, max_w, 3, 44, 32)
        blocks.append((kf, kl, WHITE, int(kf.size * 1.3), 18, 0))
    first, last = draw_blocks(d, ox, blocks)
    return {"target": (ox + M - 24, first + hf.size // 2 + 4), "exit": (ox + W - 330, min(last + 120, 1170))}


def slide_end(d, ox, s, name, label):
    max_w = W - 2 * M
    qf, ql = fit_lines(s.get("quote", ""), HAND, max_w, 5, 130, 70)
    blocks = [(qf, ql, WHITE, int(qf.size * 0.98), 0, 0)]
    first, last = draw_blocks(d, ox, blocks, top=None)
    y = last + 60
    d.line([(ox + M, y), (ox + M + 90, y)], fill=GOLD, width=5)
    d.text((ox + M, y + 34), name, font=font(SEMI, 40), fill=GOLD)
    d.text((ox + M, y + 88), label, font=font(BODY, 32), fill=SKY)
    if s.get("cta"):
        d.text((ox + M, y + 160), s["cta"], font=font(BOLD, 36), fill=WHITE)
    return {"target": (ox + M - 24, first + qf.size // 2)}


def render_carousel(slides, name, label):
    """Returns a list of PIL images, one per slide."""
    n = len(slides)
    canvas = background(n, slides)
    d = ImageDraw.Draw(canvas)
    layer = Image.new("RGBA", (W * n * SS, H * SS), (0, 0, 0, 0))

    anchors = []
    for i, s in enumerate(slides):
        ox = i * W
        kind = s.get("type", "point")
        if kind == "cover":
            anchors.append(slide_cover(d, ox, s))
        elif kind == "end":
            anchors.append(slide_end(d, ox, s, name, label))
        else:
            anchors.append(slide_point(d, ox, s, layer))

    # connectors: a small curl below the text, then a long arc across the slide edge
    # that lands as an arrowhead pointing at the next slide's headline
    for i in range(n - 1):
        sx, sy = anchors[i].get("exit", (i * W + W - 330, 1100))
        ex, ey = anchors[i + 1].get("target", ((i + 1) * W + M - 24, 420))
        # curl: a little loop drawn first
        r = 34
        loop = [(sx + r * math.cos(a), sy - r + r * math.sin(a)) for a in [math.pi / 2 + k * (2 * math.pi) / 80 for k in range(81)]]
        brush(layer, [(x * SS, y * SS) for x, y in loop], 6, 9, GOLD, wobble=0.8)
        arrow(layer, (sx, sy), (sx + 260, sy + 30), (ex - 220, ey + 300), (ex - 14, ey + 6), GOLD, width=10, head=40)

    layer = layer.resize((W * n, H), Image.LANCZOS)
    canvas = Image.alpha_composite(canvas, layer).convert("RGB")
    return [canvas.crop((i * W, 0, (i + 1) * W, H)) for i in range(n)]
