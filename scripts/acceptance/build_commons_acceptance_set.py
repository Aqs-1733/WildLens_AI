from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import random
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


API = "https://commons.wikimedia.org/w/api.php"
USER_AGENT = "WildLens-Acceptance-Builder/1.0 (local model evaluation)"
GROUPS = {
    "bird": [
        "Category:Featured pictures of birds",
        "Category:Quality images of birds",
    ],
    "mammal": [
        "Category:Featured pictures of mammals",
        "Category:Quality images of mammals",
    ],
    "negative": [
        "Category:Featured pictures of waterfalls",
        "Category:Featured pictures of mountains",
        "Category:Featured pictures of architecture",
        "Category:Featured pictures of flowers",
    ],
}
NEGATIVE_BLOCKLIST = {
    "bird", "eagle", "owl", "duck", "goose", "swan", "animal", "mammal",
    "deer", "fox", "bear", "cat", "dog", "horse", "cow", "sheep", "goat",
    "monkey", "elephant", "zebra", "giraffe", "lion", "tiger", "leopard",
}


def api_get(params: dict[str, str]) -> dict:
    url = API + "?" + urllib.parse.urlencode(params)
    for attempt in range(7):
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                payload = json.load(response)
            time.sleep(0.5)
            return payload
        except urllib.error.HTTPError as exc:
            if exc.code != 429 or attempt == 6:
                raise
            time.sleep(5 * (attempt + 1))
    raise RuntimeError("unreachable")


def clean_meta(value: object) -> str:
    if isinstance(value, dict):
        value = value.get("value", "")
    text = html.unescape(str(value or ""))
    while "<" in text and ">" in text:
        start, end = text.find("<"), text.find(">")
        text = text[:start] + " " + text[end + 1 :]
    return " ".join(text.split())


def candidates(category: str, limit: int = 160) -> list[dict]:
    rows: list[dict] = []
    continuation: dict[str, str] = {}
    while len(rows) < limit:
        payload = api_get(
            {
                "action": "query",
                "format": "json",
                "formatversion": "2",
                "generator": "categorymembers",
                "gcmtitle": category,
                "gcmtype": "file",
                "gcmlimit": "50",
                "prop": "imageinfo",
                "iiprop": "url|size|mime|extmetadata",
                "iiurlwidth": "1280",
                **continuation,
            }
        )
        for page in payload.get("query", {}).get("pages", []):
            info = (page.get("imageinfo") or [{}])[0]
            meta = info.get("extmetadata") or {}
            url = info.get("thumburl") or info.get("url") or ""
            if url and info.get("mime") in {"image/jpeg", "image/png", "image/webp"}:
                rows.append(
                    {
                        "title": page.get("title", ""),
                        "download_url": url,
                        "page_url": info.get("descriptionurl", ""),
                        "author": clean_meta(meta.get("Artist")),
                        "license": clean_meta(meta.get("LicenseShortName")),
                        "license_url": clean_meta(meta.get("LicenseUrl")),
                        "source_category": category,
                    }
                )
        continuation = payload.get("continue") or {}
        if not continuation:
            break
        time.sleep(0.1)
    return rows[:limit]


def deep_candidates(category: str, limit: int = 180) -> list[dict]:
    rows: list[dict] = []
    continuation: dict[str, str] = {}
    while len(rows) < limit:
        payload = api_get(
            {
                "action": "query",
                "format": "json",
                "formatversion": "2",
                "generator": "search",
                "gsrnamespace": "6",
                "gsrsearch": f'deepcategory:"{category.removeprefix("Category:")}" filetype:bitmap',
                "gsrlimit": "50",
                "prop": "imageinfo",
                "iiprop": "url|size|mime|extmetadata",
                "iiurlwidth": "1280",
                **continuation,
            }
        )
        for page in payload.get("query", {}).get("pages", []):
            info = (page.get("imageinfo") or [{}])[0]
            meta = info.get("extmetadata") or {}
            url = info.get("thumburl") or info.get("url") or ""
            if url and info.get("mime") in {"image/jpeg", "image/png", "image/webp"}:
                rows.append(
                    {
                        "title": page.get("title", ""),
                        "download_url": url,
                        "page_url": info.get("descriptionurl", ""),
                        "author": clean_meta(meta.get("Artist")),
                        "license": clean_meta(meta.get("LicenseShortName")),
                        "license_url": clean_meta(meta.get("LicenseUrl")),
                        "source_category": category,
                    }
                )
        continuation = payload.get("continue") or {}
        if not continuation:
            break
    return rows[:limit]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def training_hashes(dataset_root: Path) -> set[str]:
    result: set[str] = set()
    image_root = dataset_root / "images"
    if not image_root.exists():
        return result
    for path in image_root.rglob("*"):
        if path.is_file() and path.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}:
            result.add(sha256(path))
    return result


def download(url: str, destination: Path) -> None:
    for attempt in range(6):
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(request, timeout=90) as response:
                destination.write_bytes(response.read())
            time.sleep(0.65)
            return
        except urllib.error.HTTPError as exc:
            if exc.code != 429 or attempt == 5:
                raise
            time.sleep(3 * (attempt + 1))


def safe(value: object) -> str:
    return str(value).encode("ascii", "backslashreplace").decode("ascii")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--count-per-positive", type=int, default=25)
    parser.add_argument("--count-negative", type=int, default=20)
    args = parser.parse_args()
    output = args.project / "data" / "acceptance" / "real_world_v1"
    output.mkdir(parents=True, exist_ok=True)
    known_hashes = training_hashes(
        args.project / "data" / "yolo_datasets" / "wildlens"
    )
    chosen_hashes: set[str] = set()
    manifest: list[dict] = []
    rng = random.Random(20260723)
    targets = {
        "mammal": args.count_per_positive,
        "bird": args.count_per_positive,
        "negative": args.count_negative,
    }
    for expected, target in targets.items():
        pool: list[dict] = []
        for category in GROUPS[expected]:
            try:
                pool.extend(deep_candidates(category))
            except Exception as exc:
                print(f"WARN category failed: {safe(category)}: {safe(exc)}", flush=True)
        unique = {item["title"]: item for item in pool}
        pool = list(unique.values())
        rng.shuffle(pool)
        target_dir = output / expected
        target_dir.mkdir(exist_ok=True)
        index = 0
        for item in pool:
            if len([row for row in manifest if row["expected"] == expected]) >= target:
                break
            lowered = item["title"].lower()
            if expected == "negative" and any(word in lowered for word in NEGATIVE_BLOCKLIST):
                continue
            if not item["license"]:
                continue
            suffix = Path(urllib.parse.urlparse(item["download_url"]).path).suffix.lower()
            if suffix not in {".jpg", ".jpeg", ".png", ".webp"}:
                suffix = ".jpg"
            temp = target_dir / f"candidate_{index:04d}{suffix}"
            index += 1
            try:
                download(item["download_url"], temp)
                if temp.stat().st_size > 20 * 1024 * 1024:
                    temp.unlink()
                    continue
                digest = sha256(temp)
                if digest in known_hashes or digest in chosen_hashes:
                    temp.unlink()
                    continue
                final = target_dir / f"{expected}_{len([r for r in manifest if r['expected'] == expected]) + 1:03d}{suffix}"
                temp.replace(final)
                chosen_hashes.add(digest)
                manifest.append(
                    {
                        "sample_id": final.stem,
                        "expected": expected,
                        "local_path": final.relative_to(output).as_posix(),
                        "sha256": digest,
                        "training_hash_match": "false",
                        **item,
                    }
                )
                print(f"{expected}: {len([r for r in manifest if r['expected'] == expected])}/{target}", flush=True)
            except Exception as exc:
                if temp.exists():
                    temp.unlink()
                print(
                    f"WARN download failed: {safe(item['title'])}: {safe(exc)}",
                    flush=True,
                )
        actual = len([row for row in manifest if row["expected"] == expected])
        if actual < target:
            raise RuntimeError(f"Only collected {actual}/{target} for {expected}")
    fields = list(manifest[0])
    with (output / "manifest.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(manifest)
    (output / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"DONE {len(manifest)} images at {output}", flush=True)


if __name__ == "__main__":
    main()
