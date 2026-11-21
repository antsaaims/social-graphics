"""
Turn approved text notes into branded social graphics (Facebook + Instagram).

Usage:
    python render.py --queue queue/pending.json --out out
    python render.py --queue samples/samples.json --out previews --all-templates

Queue file: a JSON list of items:
    {"id": "<notion page id>", "text": "The note text", "template": "quote"}   # template optional

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


def footer(draw, W, H, name_color, domain_color, align="left", y=None, divider=None):
    """Name + domain signature at the bottom."""
    f_name = font(SANS_SEMIBOLD, 34)
    f_dom = font(SANS, 26)
    y = y if y is not None else H - MARGIN - 70
    if divider:
        if align == "left":
            draw.line([(MARGIN, y - 34), (MARGIN + 80, y - 34)], fill=divider, width=4)
        else:
            draw.line([(W / 2 - 40, y - 34), (W / 2 + 40, y - 34)], fill=divider, width=4)
    if align == "left":
        draw.text((MARGIN, y), NAME, font=f_name, fill=name_color)
        draw.text((MARGIN, y + 44), DOMAIN, font=f_dom, fill=domain_color)
    else:
        draw.text(((W - f_name.getlength(NAME)) / 2, y), NAME, font=f_name, fill=name_color)
        draw.text(((W - f_dom.getlength(DOMAIN)) / 2, y + 44), DOMAIN, font=f_dom, fill=domain_color)


# ---------------------------------------------------------------- templates
# Each template draws on a fresh canvas and returns (image, font_size, too_long).

def t_classic(text):
    """The original layout: name + domain header, divider, centred body."""
    W, H = SIZE
    img = Image.new("RGB", SIZE, NAVY)
    d = ImageDraw.Draw(img)
    d.text((MARGIN, 110), NAME, font=font(SANS_SEMIBOLD, 36), fill=GOLD)
    d.text((MARGIN, 158), DOMAIN, font=font(SANS, 28), fill=SKY)
    d.line([(MARGIN, 225), (W - MARGIN, 225)], fill=STEEL, width=3)
    box = (MARGIN, 270, W - 2 * MARGIN, H - 270 - MARGIN)
    fnt, lines, lh, long_ = fit(text, SANS_MEDIUM, box[2], box[3], 58, 30)
    draw_block(d, lines, fnt, lh, box, GOLD)
    return img, fnt.size, long_


def t_quote(text):
    """Big gold quotation mark, serif text, signature bottom-left."""
    W, H = SIZE
    img = Image.new("RGB", SIZE, NAVY)
    d = ImageDraw.Draw(img)
    d.text((MARGIN - 12, 40), "“", font=font(SERIF, 300), fill=GOLD)
    box = (MARGIN, 270, W - 2 * MARGIN, H - 270 - 240)
    fnt, lines, lh, long_ = fit(text, SERIF, box[2], box[3], 72, 34, spacing=1.28)
    draw_block(d, lines, fnt, lh, box, (255, 255, 255))
    footer(d, W, H, GOLD, SKY, divider=SKY)
    return img, fnt.size, long_


def t_grid(text):
    """Graph-paper grid (a nod to math), sky-blue accent bar, bold sans text."""
    W, H = SIZE
    img = Image.new("RGB", SIZE, NAVY)
    d = ImageDraw.Draw(img)
    step = 54
    for x in range(0, W + 1, step):
        d.line([(x, 0), (x, H)], fill=(19, 36, 62), width=1)
    for y in range(0, H + 1, step):
        d.line([(0, y), (W, y)], fill=(19, 36, 62), width=1)
    box = (MARGIN + 44, 150, W - 2 * MARGIN - 44, H - 150 - 260)
    fnt, lines, lh, long_ = fit(text, SANS_SEMIBOLD, box[2], box[3], 60, 30, spacing=1.32)
    end = draw_block(d, lines, fnt, lh, box, GOLD)
    top = box[1] + (box[3] - len(lines) * lh) // 2
    d.rounded_rectangle([(MARGIN, top + 6), (MARGIN + 10, end - 6)], radius=5, fill=SKY)
    footer(d, W, H, (255, 255, 255), SKY, divider=GOLD)
    return img, fnt.size, long_


def t_gold(text):
    """Inverted: gold background, navy serif text, thin navy frame."""
    W, H = SIZE
    img = Image.new("RGB", SIZE, GOLD)
    d = ImageDraw.Draw(img)
    inset = 44
    d.rectangle([(inset, inset), (W - inset, H - inset)], outline=NAVY, width=3)
    box = (MARGIN + 10, 150, W - 2 * MARGIN - 20, H - 150 - 250)
    fnt, lines, lh, long_ = fit(text, SERIF, box[2], box[3], 70, 34, spacing=1.28)
    draw_block(d, lines, fnt, lh, box, NAVY, align="center")
    footer(d, W, H, NAVY, (25, 92, 140), align="center", divider=NAVY)
    return img, fnt.size, long_


def t_spotlight(text):
    """Soft sky-blue circle in the corner, small gold dot, left-aligned text."""
    W, H = SIZE
    img = Image.new("RGB", SIZE, NAVY)
    d = ImageDraw.Draw(img)
    r = 330
    cx, cy = W - 60, H - 40
    d.ellipse([(cx - r, cy - r), (cx + r, cy + r)], fill=(16, 52, 84))
    d.ellipse([(MARGIN, 120), (MARGIN + 26, 146)], fill=GOLD)
    box = (MARGIN, 190, W - 2 * MARGIN, H - 190 - 250)
    fnt, lines, lh, long_ = fit(text, SANS_BOLD, box[2], box[3], 64, 30, spacing=1.3)
    draw_block(d, lines, fnt, lh, box, (255, 255, 255))
    footer(d, W, H, GOLD, SKY, divider=GOLD)
    return img, fnt.size, long_


def t_paper(text):
    """Light version: paper white, navy serif text, gold underline, sky-blue domain."""
    W, H = SIZE
    img = Image.new("RGB", SIZE, CREAM)
    d = ImageDraw.Draw(img)
    d.rectangle([(0, 0), (W, 18)], fill=NAVY)
    box = (MARGIN, 150, W - 2 * MARGIN, H - 150 - 290)
    fnt, lines, lh, long_ = fit(text, SERIF, box[2], box[3], 70, 34, spacing=1.28)
    end = draw_block(d, lines, fnt, lh, box, NAVY)
    d.line([(MARGIN, end + 28), (MARGIN + 140, end + 28)], fill=GOLD, width=8)
    footer(d, W, H, NAVY, (14, 116, 166))
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
        for t in chosen:
            img, size, too_long = TEMPLATES[t](text)
            filename = f"{item_id}__{t}.png" if args.all_templates else f"{item_id}.png"
            img.save(os.path.join(args.out, filename), "PNG", optimize=True)
            w = list(warnings)
            if too_long:
                w.append("text is long: drawn at the minimum size and may overflow; consider shortening")
            manifest.append({"id": item.get("id"), "file": filename, "template": t, "font_size": size, "warnings": w})

    with open(os.path.join(args.out, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    if not args.no_state and not args.all_templates:
        save_state(state)
    print(f"Rendered {len(manifest)} graphic(s) into {args.out}")


if __name__ == "__main__":
    main()
