"""
Upload the graphics listed in <out>/manifest.json to Cloudinary and record the public URLs.

Needs the CLOUDINARY_URL environment variable (cloudinary://<api_key>:<api_secret>@<cloud_name>),
stored as a GitHub Actions secret. Each image is saved as social-graphics/<notion page id>,
so re-rendering the same note replaces its old image instead of making a duplicate
(Substack banners get a "-substack" suffix).

Writes results/<run-id>.json and results/latest.json:
    [{"id": ..., "template": ..., "url": "https://res.cloudinary.com/...", "warnings": [...]}]
"""

import argparse
import datetime
import json
import os

import cloudinary
import cloudinary.uploader


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="out")
    ap.add_argument("--results", default="results")
    args = ap.parse_args()

    if not os.environ.get("CLOUDINARY_URL"):
        raise SystemExit("CLOUDINARY_URL is not set (add it as a repository secret).")
    cloudinary.config(secure=True)

    with open(os.path.join(args.out, "manifest.json"), encoding="utf-8") as f:
        manifest = json.load(f)

    results = []
    for entry in manifest:
        path = os.path.join(args.out, entry["file"])
        public_id = os.path.splitext(entry["file"])[0]
        res = cloudinary.uploader.upload(
            path,
            folder="social-graphics",
            public_id=public_id,
            overwrite=True,
            invalidate=True,
            resource_type="image",
            tags=["social-graphics", f"template-{entry['template']}", f"format-{entry.get('format', 'square')}"],
            context={"notion_id": str(entry.get("id", "")), "template": entry["template"]},
        )
        results.append({
            "id": entry.get("id"),
            "template": entry["template"],
            "format": entry.get("format", "square"),
            "url": res["secure_url"],
            "public_id": res["public_id"],
            "warnings": entry.get("warnings", []),
        })
        print(f"uploaded {entry['file']} -> {res['secure_url']}")

    os.makedirs(args.results, exist_ok=True)
    run_id = os.environ.get("GITHUB_RUN_ID") or datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    stamp = datetime.datetime.utcnow().strftime("%Y-%m-%d")
    for name in (f"{stamp}-run{run_id}.json", "latest.json"):
        with open(os.path.join(args.results, name), "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
            f.write("\n")
    print(f"Uploaded {len(results)} graphic(s).")


if __name__ == "__main__":
    main()
