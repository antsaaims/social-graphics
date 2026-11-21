# social-graphics

Turns Antsa's approved text notes into branded graphics (1080×1080 squares for Facebook and
Instagram, 1456×1048 banners for Substack),
uploads them to Cloudinary, and records the public links so Claude can schedule them in Buffer.

## How it works

1. A note in the Notion **Social Media Content Planner** is set to **Approved**, with Platform
   Facebook and/or Instagram and no Media URLs yet.
2. Claude writes those notes to `queue/pending.json` and pushes:
   ```json
   [{"id": "<notion page id>", "text": "The note text",
     "template": "quote", "format": "substack", "label": "Dear Mom"}]
   ```
   `template`, `format` (`square` by default, or `substack`) and `label` (shown under the name
   instead of the domain, e.g. the Substack publication) are optional. Without it, templates rotate in order so two posts in a row never look alike
   (the last one used is kept in `state.json`).
3. The GitHub Action renders one PNG per note, uploads it to Cloudinary as
   `social-graphics/<notion page id>`, writes the links to `results/latest.json`
   (plus a dated copy), archives the queue in `queue/done/`, and empties `queue/pending.json`.
4. Claude copies each link into the note's **Media URLs**, schedules the post in Buffer, and sets
   Status to **Scheduled**.

## Templates

| Name | Look |
|---|---|
| `classic` | Name and domain at the top, divider, gold text (the original design) |
| `quote` | Large gold quotation mark, white serif text |
| `grid` | Faint graph-paper grid, sky-blue accent bar, gold text |
| `gold` | Gold background, navy serif text, thin navy frame |
| `spotlight` | Bold white text, gold dot, soft blue circle in the corner |
| `paper` | Light paper background, navy serif text, gold underline |

Text size adjusts to fit each note. Notes too long for the smallest size get a warning in the results.
Emoji are removed because the fonts can't draw them.

## Formats

| Format | Size | Use |
|---|---|---|
| `square` | 1080×1080 | Facebook and Instagram |
| `substack` | 1456×1048 | Substack post covers and Notes images. Substack crops this image differently in the feed, app, email and link previews, so all text stays inside the centre area that survives both a square crop and a 1.91:1 crop. |

Brand colours, name, domain and the square size are at the top of `render.py`
(set `SIZE = (1080, 1350)` for Instagram portrait).

## Preview locally

```bash
pip install -r requirements.txt
python render.py --queue samples/samples.json --out previews --all-templates --no-state
python render.py --queue samples/samples-substack.json --out previews --all-templates --no-state
```

## Setup (once)

Repository secret **`CLOUDINARY_URL`**: in Cloudinary, open *Settings → API Keys* and copy the
*API environment variable* (`cloudinary://<key>:<secret>@<cloud name>`). In GitHub: *Settings →
Secrets and variables → Actions → New repository secret*.

## Fonts

DM Serif Display and Inter, both under the SIL Open Font License (licences in `fonts/`).
