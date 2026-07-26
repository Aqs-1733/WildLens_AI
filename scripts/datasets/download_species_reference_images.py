"""Download licensed reference thumbnails through Wikimedia/Wikipedia summaries.

The generated manifest stores source page, thumbnail URL and license fields when
available. Reference images are for encyclopedia cards, not training, unless the
individual file license explicitly permits that use and attribution is preserved.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import urllib.parse
import urllib.request
from pathlib import Path

API = "https://en.wikipedia.org/api/rest_v1/page/summary/{}"


def safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("_")


def fetch_json(url: str) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": "Shijing-AI/2.0 (education project)"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def download(url: str, target: Path) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "Shijing-AI/2.0 (education project)"})
    with urllib.request.urlopen(request, timeout=60) as response, target.open("wb") as output:
        output.write(response.read())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--taxonomy", type=Path, default=Path("data/taxonomy/target_species.csv"))
    parser.add_argument("--output", type=Path, default=Path("storage/reference_images"))
    parser.add_argument("--limit", type=int, default=60)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    rows = list(csv.DictReader(args.taxonomy.open(encoding="utf-8-sig", newline="")))[: args.limit]
    manifest: list[dict] = []
    for row in rows:
        scientific = row["scientific_name"]
        try:
            summary = fetch_json(API.format(urllib.parse.quote(scientific.replace(" ", "_"))))
            image = summary.get("thumbnail", {}).get("source") or summary.get("originalimage", {}).get("source")
            if not image:
                print(f"[SKIP] no image: {scientific}")
                continue
            suffix = Path(urllib.parse.urlparse(image).path).suffix.lower()
            if suffix not in {".jpg", ".jpeg", ".png", ".webp"}:
                suffix = ".jpg"
            target = args.output / f"{safe_name(scientific)}{suffix}"
            if not target.exists():
                download(image, target)
            manifest.append({
                "common_name": row["common_name"],
                "scientific_name": scientific,
                "local_path": str(target),
                "source_page": summary.get("content_urls", {}).get("desktop", {}).get("page", ""),
                "thumbnail_url": image,
                "attribution_required": True,
                "note": "使用前请进入source_page核对原始Wikimedia文件页许可证并保留作者署名。",
            })
            print(f"[OK] {scientific}")
        except Exception as exc:
            print(f"[WARN] {scientific}: {exc}")
    manifest_path = Path("data/manifests/species_reference_images.json")
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"saved {len(manifest)} images -> {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
