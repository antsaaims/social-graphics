"""
Turn approved text notes into branded social graphics (Facebook + Instagram).

Usage:
    python render.py --queue queue/pending.json --out out
    python render.py --queue samples/samples.json --out previews --all-templates

Queue file: a JSON list of items:
    {"id": "<notion page id>", "text": "The note text",
     "template": "quote",          # optional; otherwise templates rotate
     "format": "substack",         # optional: "square" (1080x1080, Facebook/Instagram, default),
                                   #   "substack" (1456x1048 post cover / Notes image)
                                   #   or "inline" (1460x730, an image inside a newsletter)
     "label": "Dear Mom"}          # optional: shown under the name instead of the domain

If an item has no template, templates rotate in order (the last one used is kept in
state.json) so two posts in a row never look the same.

Writes one PNG per item to --out and a manifest (out/manifest.json) with the file name,
template, final font size and any warnings (for example text that needed the minimum size).
"""

import argparse
import json
import os
import re
import unicodedata

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
FONTS = os.path.join(HERE, "fonts")
STATE_FILE = os.path.join(HERE, "state.json")

# ---------------------------------------------------------------- brand
NAME = "Antsa Honeywinner"
DOMAIN = "antsaeducontent.com"

NAVY = (10, 25, 47)        # Deep Midnight Navy
GOLD = (244, 211, 94)      # Warm Golden-Yellow
SKY = (56, 189, 248)       # Vibrant Sky Blue
STEEL = (30, 41, 59)       # Muted steel blue
CREAM = (250, 246, 236)    # Soft paper white (light template)

SIZE = (1080, 1080)        # square works on both Facebook and Instagram; 1080x1350 for portrait
MARGIN = 100

SERIF = os.path.join(FONTS, "DMSerifDisplay-Regular.ttf")
SERIF_ITALIC = os.path.join(FONTS, "DMSerifDisplay-Italic.ttf")
SANS = os.path.join(FONTS, "Inter-Regular.otf")
SANS_MEDIUM = os.path.join(FONTS, "Inter-Medium.otf")
SANS_SEMIBOLD = os.path.join(FONTS, "Inter-SemiBold.otf")
SANS_BOLD = os.path.join(FONTS, "Inter-Bold.otf")

FORMATS = ("square", "substack", "inline")
TEMPLATE_ORDER = ["classic", "quote", "grid", "gold", "spotlight", "paper"]


# ---------------------------------------------------------------- helpers
def font(path, size):
    return ImageFont.truetype(path, size)


def clean_text(text):
    """Normalise quotes/spaces and drop emoji and other symbols the fonts can't draw."""
    warnings = []
    text = unicodedata.normalize("NFC", text.replace("\r\n", "\n").strip())
    kept = []
    dropped = False
    for ch in text:
        cat = unicodedata.category(ch)
        if ord(ch) >= 0x2190 and cat in ("So", "Sk", "Cn", "Co") or 0xFE00 <= ord(ch) <= 0xFE0F or ord(ch) == 0x200D:
            dropped = True
            continue
        kept.append(ch)
    text = "".join(kept)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if dropped:
        warnings.append("emoji or symbols removed (the fonts can't draw them)")
    return text, warnings


def wrap(text, fnt, max_width):
    """Wrap text to max_width, keeping the author's own line breaks and blank lines."""
    lines = []
    for paragraph in text.split("\n"):
        if not paragraph.strip():
            lines.append("")
            continue
        current = ""
        for word in paragraph.split(" "):
            test = f"{current} {word}".strip()
            if fnt.getlength(test) <= max_width or not current:
                current = test
            else:
                lines.append(current)
                current = word
        if current:
            lines.append(current)
    return lines


def fit(text, font_path, box_w, box_h, max_size, min_size, spacing=1.35):
    """Largest font size (max..min) whose wrapped text fits the box. Returns (font, lines, line_h, too_long)."""
    for size in range(max_size, min_size - 1, -2):
        fnt = font(font_path, size)
        lines = wrap(text, fnt, box_w)
        line_h = int(size * spacing)
        widest = max((fnt.getlength(l) for l in lines), default=0)
        if len(lines) * line_h <= box_h and widest <= box_w:
            return fnt, lines, line_h, False
    fnt = font(font_path, min_size)
    return fnt, wrap(text, fnt, box_w), int(min_size * spacing), True


def draw_block(draw, lines, fnt, line_h, box, fill, align="left", valign="center"):
    """Draw wrapped lines inside box=(x, y, w, h)."""
    x, y, w, h = box
    total = len(lines) * line_h
    if valign == "center":
        cy = y + (h - total) // 2
    elif valign == "bottom":
        cy = y + h - total
    else:
        cy = y
    ascent_fix = (line_h - fnt.size) // 2
    for line in lines:
        if line:
            lw = fnt.getlength(line)
            lx = x if align == "left" else x + (w - lw) / 2
            draw.text((lx, cy + ascent_fix), line, font=fnt, fill=fill)
        cy += line_h
    return cy


# ---------------------------------------------------------------- formats
class Frame:
    """Canvas plus the 'safe' content area. Everything important is drawn inside x0..x1, y0..y1.

    s scales type and spacing so templates look the same in every format.
    """

    def __init__(self, name, W, H, x0, y0, x1, y1, s=None):
        self.name, self.W, self.H = name, W, H
        self.x0, self.y0, self.x1, self.y1 = x0, y0, x1, y1
        self.s = s if s is not None else (y1 - y0) / 880

    @property
    def w(self):
        return self.x1 - self.x0

    def u(self, v):
        return int(round(v * self.s))


def make_frame(fmt):
    if fmt == "substack":
        # 1456x1048 (Substack's recommended post/social preview size). Substack crops this image
        # differently in the feed, app, email and link previews, so text stays in the centre
        # ~1100x780 that survives the square and 1.91:1 crops.
        W, H = 1456, 1048
        sw, sh = 1100, 780
        x0, y0 = (W - sw) // 2 + 50, (H - sh) // 2 + 40
        return Frame("substack", W, H, x0, y0, W - x0, H - y0)
    if fmt == "inline":
        # 1460x730 (2:1): an image inside a newsletter. Substack posts are 730 px wide,
        # so this is drawn at twice that width to stay sharp on high-resolution screens.
        # Inline images are not cropped, so the whole canvas is usable.
        W, H = 1460, 730
        return Frame("inline", W, H, 110, 80, W - 110, H - 80, s=0.85)
    W, H = SIZE
    return Frame("square", W, H, MARGIN, MARGIN, W - MARGIN, H - MARGIN)


def footer(d, f, name_color, domain_color, label=None, align="left", divider=None):
    """Name + domain (or publication name) signature at the bottom of the safe area."""
    f_name = font(SANS_SEMIBOLD, max(26, f.u(34)))
    f_dom = font(SANS, max(20, f.u(26)))
    second = label or DOMAIN
    y = f.y1 - f.u(70)
    cx = f.x0 + f.w / 2
    if divider:
        if align == "left":
            d.line([(f.x0, y - f.u(34)), (f.x0 + f.u(80), y - f.u(34))], fill=divider, width=4)
        else:
            d.line([(cx - f.u(40), y - f.u(34)), (cx + f.u(40), y - f.u(34))], fill=divider, width=4)
    if align == "left":
        d.text((f.x0, y), NAME, font=f_name, fill=name_color)
        d.text((f.x0, y + f.u(44)), second, font=f_dom, fill=domain_color)
    else:
        d.text((cx - f_name.getlength(NAME) / 2, y), NAME, font=f_name, fill=name_color)
        d.text((cx - f_dom.getlength(second) / 2, y + f.u(44)), second, font=f_dom, fill=domain_color)


# ---------------------------------------------------------------- templates
# Each template gets the text, a Frame and an optional label (shown instead of the domain),
# and returns (image, font_size, too_long).

def t_classic(text, f, label=None):
    """The original layout: name + domain header, divider, centred body."""
    img = Image.new("RGB", (f.W, f.H), NAVY)
    d = ImageDraw.Draw(img)
    d.text((f.x0, f.y0 + f.u(10)), NAME, font=font(SANS_SEMIBOLD, max(26, f.u(36))), fill=GOLD)
    d.text((f.x0, f.y0 + f.u(58)), label or DOMAIN, font=font(SANS, max(20, f.u(28))), fill=SKY)
    d.line([(f.x0, f.y0 + f.u(125)), (f.x1, f.y0 + f.u(125))], fill=STEEL, width=3)
    box = (f.x0, f.y0 + f.u(170), f.w, f.y1 - f.y0 - f.u(170))
    fnt, lines, lh, long_ = fit(text, SANS_MEDIUM, box[2], box[3], f.u(58), f.u(30))
    draw_block(d, lines, fnt, lh, box, GOLD)
    return img, fnt.size, long_


def t_quote(text, f, label=None):
    """Big gold quotation mark, serif text, signature bottom-left."""
    img = Image.new("RGB", (f.W, f.H), NAVY)
    d = ImageDraw.Draw(img)
    d.text((f.x0 - f.u(12), f.y0 - f.u(60)), "“", font=font(SERIF, f.u(300)), fill=GOLD)
    box = (f.x0, f.y0 + f.u(170), f.w, f.y1 - f.y0 - f.u(170) - f.u(140))
    fnt, lines, lh, long_ = fit(text, SERIF, box[2], box[3], f.u(72), f.u(34), spacing=1.28)
    draw_block(d, lines, fnt, lh, box, (255, 255, 255))
    footer(d, f, GOLD, SKY, label, divider=SKY)
    return img, fnt.size, long_


def t_grid(text, f, label=None):
    """Graph-paper grid (a nod to math), sky-blue accent bar, bold sans text."""
    img = Image.new("RGB", (f.W, f.H), NAVY)
    d = ImageDraw.Draw(img)
    step = 54
    for x in range(0, f.W + 1, step):
        d.line([(x, 0), (x, f.H)], fill=(19, 36, 62), width=1)
    for y in range(0, f.H + 1, step):
        d.line([(0, y), (f.W, y)], fill=(19, 36, 62), width=1)
    bar = f.u(44)
    box = (f.x0 + bar, f.y0 + f.u(50), f.w - bar, f.y1 - f.y0 - f.u(50) - f.u(160))
    fnt, lines, lh, long_ = fit(text, SANS_SEMIBOLD, box[2], box[3], f.u(60), f.u(30), spacing=1.32)
    end = draw_block(d, lines, fnt, lh, box, GOLD)
    top = box[1] + (box[3] - len(lines) * lh) // 2
    d.rounded_rectangle([(f.x0, top + 6), (f.x0 + max(6, f.u(10)), end - 6)], radius=5, fill=SKY)
    footer(d, f, (255, 255, 255), SKY, label, divider=GOLD)
    return img, fnt.size, long_


def t_gold(text, f, label=None):
    """Inverted: gold background, navy serif text, thin navy frame."""
    img = Image.new("RGB", (f.W, f.H), GOLD)
    d = ImageDraw.Draw(img)
    pad = f.u(56)
    d.rectangle([(f.x0 - pad, f.y0 - pad), (f.x1 + pad, f.y1 + pad)], outline=NAVY, width=3)
    box = (f.x0 + f.u(10), f.y0 + f.u(50), f.w - f.u(20), f.y1 - f.y0 - f.u(50) - f.u(150))
    fnt, lines, lh, long_ = fit(text, SERIF, box[2], box[3], f.u(70), f.u(34), spacing=1.28)
    draw_block(d, lines, fnt, lh, box, NAVY, align="center")
    footer(d, f, NAVY, (25, 92, 140), label, align="center", divider=NAVY)
    return img, fnt.size, long_


def t_spotlight(text, f, label=None):
    """Soft blue circle in the lower right, small gold dot, bold white text."""
    img = Image.new("RGB", (f.W, f.H), NAVY)
    d = ImageDraw.Draw(img)
    r = f.u(330)
    cx, cy = f.x1 + f.u(40), f.y1 + f.u(60)
    d.ellipse([(cx - r, cy - r), (cx + r, cy + r)], fill=(16, 52, 84))
    dot = max(16, f.u(26))
    d.ellipse([(f.x0, f.y0 + f.u(20)), (f.x0 + dot, f.y0 + f.u(20) + dot)], fill=GOLD)
    box = (f.x0, f.y0 + f.u(90), f.w, f.y1 - f.y0 - f.u(90) - f.u(150))
    fnt, lines, lh, long_ = fit(text, SANS_BOLD, box[2], box[3], f.u(64), f.u(30), spacing=1.3)
    draw_block(d, lines, fnt, lh, box, (255, 255, 255))
    footer(d, f, GOLD, SKY, label, divider=GOLD)
    return img, fnt.size, long_


def t_paper(text, f, label=None):
    """Light version: paper white, navy serif text, gold underline, sky-blue domain."""
    img = Image.new("RGB", (f.W, f.H), CREAM)
    d = ImageDraw.Draw(img)
    bar_y = 0 if f.name == "square" else f.y0 - f.u(90)
    d.rectangle([(0, bar_y), (f.W, bar_y + 18)], fill=NAVY)
    box = (f.x0, f.y0 + f.u(50), f.w, f.y1 - f.y0 - f.u(50) - f.u(190))
    fnt, lines, lh, long_ = fit(text, SERIF, box[2], box[3], f.u(70), f.u(34), spacing=1.28)
    end = draw_block(d, lines, fnt, lh, box, NAVY)
    d.line([(f.x0, end + f.u(28)), (f.x0 + f.u(140), end + f.u(28))], fill=GOLD, width=max(5, f.u(8)))
    footer(d, f, NAVY, (14, 116, 166), label)
    return img, fnt.size, long_


TEMPLATES = {
    "classic": t_classic,
    "quote": t_quote,
    "grid": t_grid,
    "gold": t_gold,
    "spotlight": t_spotlight,
    "paper": t_paper,
}


# ---------------------------------------------------------------- rotation state
def load_state():
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {"last_template": None}


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)
        f.write("\n")


def next_template(last):
    if last not in TEMPLATE_ORDER:
        return TEMPLATE_ORDER[0]
    return TEMPLATE_ORDER[(TEMPLATE_ORDER.index(last) + 1) % len(TEMPLATE_ORDER)]


def safe_name(s):
    return re.sub(r"[^A-Za-z0-9_-]+", "-", s).strip("-")[:80] or "post"


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--queue", required=True)
    ap.add_argument("--out", default="out")
    ap.add_argument("--all-templates", action="store_true", help="preview: render every item in every template")
    ap.add_argument("--no-state", action="store_true", help="don't read or update state.json")
    ap.add_argument("--format", default="square", choices=list(FORMATS),
                    help="default format for items that don't set one")
    args = ap.parse_args()

    with open(args.queue, encoding="utf-8") as f:
        items = json.load(f)
    os.makedirs(args.out, exist_ok=True)

    state = {"last_template": None} if args.no_state else load_state()
    manifest = []
    for item in items:
        text, warnings = clean_text(item.get("text", ""))
        if not text:
            continue
        item_id = safe_name(str(item.get("id", f"post-{len(manifest) + 1}")))
        if args.all_templates:
            chosen = TEMPLATE_ORDER
        else:
            t = item.get("template")
            if t not in TEMPLATES:
                t = next_template(state.get("last_template"))
            state["last_template"] = t
            chosen = [t]
        fmt = item.get("format", args.format)
        if fmt not in FORMATS:
            fmt = "square"
        frame = make_frame(fmt)
        label = item.get("label")
        suffix = "" if fmt == "square" else f"-{fmt}"
        for t in chosen:
            img, size, too_long = TEMPLATES[t](text, frame, label)
            filename = f"{item_id}{suffix}__{t}.png" if args.all_templates else f"{item_id}{suffix}.png"
            img.save(os.path.join(args.out, filename), "PNG", optimize=True)
            w = list(warnings)
            if too_long:
                w.append("text is long: drawn at the minimum size and may overflow; consider shortening")
            manifest.append({"id": item.get("id"), "file": filename, "format": fmt, "template": t,
                             "font_size": size, "warnings": w})

    with open(os.path.join(args.out, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    if not args.no_state and not args.all_templates:
        save_state(state)
    print(f"Rendered {len(manifest)} graphic(s) into {args.out}")


if __name__ == "__main__":
    main()
