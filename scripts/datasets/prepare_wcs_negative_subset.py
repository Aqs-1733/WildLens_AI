"""Add reproducible WCS images explicitly labelled empty as YOLO negatives."""
from __future__ import annotations

import argparse
import json
import random
from collections import defaultdict
from pathlib import Path

import yaml

from prepare_wcs_yolo_subset import LICENSE, IMAGE_BASE_URLS, download_wcs_image, load_wcs, stable_split


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--data-yaml", type=Path, required=True)
    parser.add_argument("--count", type=int, default=300)
    parser.add_argument("--seed", type=int, default=20260722)
    parser.add_argument("--manifest-only", action="store_true")
    args = parser.parse_args()

    config = yaml.safe_load(args.data_yaml.read_text(encoding="utf-8"))
    root = Path(str(config.get("path") or args.data_yaml.parent)).resolve()
    metadata = load_wcs(args.archive)
    categories = {int(item["id"]): str(item["name"]).strip().lower() for item in metadata["categories"]}
    annotations_by_image: dict[str, list[dict]] = defaultdict(list)
    for annotation in metadata["annotations"]:
        annotations_by_image[str(annotation["image_id"])].append(annotation)

    candidates = []
    for image in metadata["images"]:
        image_id = str(image["id"])
        if image.get("corrupt"):
            continue
        annotations = annotations_by_image.get(image_id, [])
        if annotations and all(
            categories.get(int(item["category_id"])) == "empty" and not item.get("bbox")
            for item in annotations
        ):
            candidates.append(image)

    rng = random.Random(args.seed)
    rng.shuffle(candidates)
    selected = []
    seen_groups: set[str] = set()
    for image in candidates:
        group = str(image.get("location") or image.get("seq_id") or image["id"])
        if group in seen_groups and len(seen_groups) < args.count:
            continue
        seen_groups.add(group)
        selected.append(image)
        if len(selected) >= args.count:
            break

    manifest_path = root / "metadata" / "wcs_subset_empty_v2.jsonl"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    downloaded = failures = 0
    with manifest_path.open("w", encoding="utf-8") as manifest:
        for image in selected:
            image_id = str(image["id"])
            relative_path = str(image["file_name"]).lstrip("/")
            group = str(image.get("location") or image.get("seq_id") or image_id)
            split = stable_split(group)
            suffix = Path(relative_path).suffix.lower() or ".jpg"
            image_path = root / "images" / split / f"wcs_empty_{image_id}{suffix}"
            label_path = root / "labels" / split / f"wcs_empty_{image_id}.txt"
            manifest.write(json.dumps({
                "dataset": "WCS Camera Traps",
                "image_id": image_id,
                "split": split,
                "group_id": group,
                "source_url": IMAGE_BASE_URLS[0] + relative_path,
                "license": LICENSE,
                "local_image": str(image_path),
                "boxes": [],
                "negative": True,
            }, ensure_ascii=False) + "\n")
            if args.manifest_only:
                continue
            try:
                download_wcs_image(relative_path, image_path)
                label_path.parent.mkdir(parents=True, exist_ok=True)
                label_path.touch(exist_ok=True)
                downloaded += 1
            except Exception as exc:
                failures += 1
                print(f"[WARN] {relative_path}: {exc}")

    print(json.dumps({
        "available_empty": len(candidates),
        "selected": len(selected),
        "downloaded": downloaded,
        "failures": failures,
        "manifest": str(manifest_path),
    }, ensure_ascii=False, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
