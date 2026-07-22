"""Download a reproducible, license-tracked subset of WCS Camera Traps.

The script intentionally downloads metadata first, then samples by category and
location/sequence. It does not attempt to mirror the 1.4M-image dataset.
"""
from __future__ import annotations

import argparse
import json
import random
import shutil
import urllib.request
import zipfile
from collections import defaultdict
from pathlib import Path
from typing import Any

METADATA_URL = "https://storage.googleapis.com/public-datasets-lila/wcs_camera_traps.json.zip"
IMAGE_BASE_URL = "https://storage.googleapis.com/public-datasets-lila/wcs-unzipped/"


def download(url: str, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_suffix(target.suffix + ".part")
    if target.exists():
        return
    request = urllib.request.Request(url, headers={"User-Agent": "Shijing-AI/2.0"})
    with urllib.request.urlopen(request, timeout=90) as response, partial.open("wb") as out:
        shutil.copyfileobj(response, out)
    partial.replace(target)


def load_metadata(root: Path) -> dict[str, Any]:
    archive = root / "wcs_camera_traps.json.zip"
    download(METADATA_URL, archive)
    with zipfile.ZipFile(archive) as zf:
        json_names = [name for name in zf.namelist() if name.lower().endswith(".json")]
        if not json_names:
            raise RuntimeError("WCS 元数据压缩包中未找到 JSON")
        with zf.open(json_names[0]) as src:
            return json.load(src)


def choose_images(
    metadata: dict[str, Any], categories: set[str], per_class: int, seed: int
) -> list[dict[str, Any]]:
    category_by_id = {item["id"]: item["name"] for item in metadata.get("categories", [])}
    image_by_id = {item["id"]: item for item in metadata.get("images", [])}
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for ann in metadata.get("annotations", []):
        name = str(category_by_id.get(ann.get("category_id"), "")).strip()
        if categories and name.lower() not in categories:
            continue
        image = image_by_id.get(ann.get("image_id"))
        if not image:
            continue
        grouped[name].append(image)

    rng = random.Random(seed)
    selected: list[dict[str, Any]] = []
    for name, records in sorted(grouped.items()):
        # Deduplicate, then interleave locations/sequences when metadata provides them.
        unique = {str(item["id"]): item for item in records}.values()
        by_group: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for item in unique:
            group = str(item.get("location") or item.get("seq_id") or item.get("id"))
            by_group[group].append(item)
        groups = list(by_group.values())
        rng.shuffle(groups)
        class_selection: list[dict[str, Any]] = []
        cursor = 0
        while groups and len(class_selection) < per_class:
            group = groups[cursor % len(groups)]
            if group:
                class_selection.append(group.pop(rng.randrange(len(group))))
            groups = [value for value in groups if value]
            cursor += 1
        for item in class_selection:
            selected.append({"category": name, **item})
    return selected


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("data/raw/wcs_subset"))
    parser.add_argument("--categories", nargs="*", default=[])
    parser.add_argument("--per-class", type=int, default=250)
    parser.add_argument("--seed", type=int, default=20260713)
    parser.add_argument("--metadata-only", action="store_true")
    args = parser.parse_args()

    metadata = load_metadata(args.output)
    requested = {item.strip().lower() for item in args.categories if item.strip()}
    selected = choose_images(metadata, requested, max(1, args.per_class), args.seed)
    manifest_path = args.output / "subset_manifest.jsonl"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with manifest_path.open("w", encoding="utf-8") as manifest:
        for item in selected:
            relative = str(item.get("file_name", "")).lstrip("/")
            record = {
                "dataset": "WCS Camera Traps",
                "category": item["category"],
                "image_id": item.get("id"),
                "location": item.get("location"),
                "sequence_id": item.get("seq_id"),
                "relative_path": relative,
                "source_url": IMAGE_BASE_URL + relative,
                "license": "CDLA-Permissive-1.0",
            }
            manifest.write(json.dumps(record, ensure_ascii=False) + "\n")
            if not args.metadata_only and relative:
                target = args.output / "images" / relative
                try:
                    download(record["source_url"], target)
                except Exception as exc:  # keep resumable manifest even when individual URLs fail
                    print(f"[WARN] {relative}: {exc}")
    print(f"已选择 {len(selected)} 张；清单：{manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
