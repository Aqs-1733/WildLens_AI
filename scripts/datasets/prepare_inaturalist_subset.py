"""Build a class-balanced iNaturalist 2021 subset without copying the full dataset.

Expected official files:
- train.json or train_mini.json
- train/ or train_mini/ image tree

The script reads COCO-style categories/images/annotations, selects classes by image
count, and creates a manifest plus optional hard links/copies. It never downloads
unlicensed files and preserves the source image id/category metadata.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
from collections import Counter, defaultdict
from pathlib import Path


def link_or_copy(source: Path, target: Path, copy: bool) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        return
    if copy:
        shutil.copy2(source, target)
        return
    try:
        os.link(source, target)
    except OSError:
        shutil.copy2(source, target)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset_root", type=Path)
    parser.add_argument("--annotations", type=Path)
    parser.add_argument("--output", type=Path, default=Path("data/processed/inaturalist_subset"))
    parser.add_argument("--max-classes", type=int, default=500)
    parser.add_argument("--min-images", type=int, default=300)
    parser.add_argument("--per-class", type=int, default=1200)
    parser.add_argument("--kingdom", action="append", default=[], help="可重复：Animalia / Plantae")
    parser.add_argument("--copy", action="store_true")
    parser.add_argument("--manifest-only", action="store_true")
    args = parser.parse_args()

    annotation_path = args.annotations or next(
        (p for p in (args.dataset_root / "train.json", args.dataset_root / "train_mini.json") if p.exists()),
        None,
    )
    if annotation_path is None:
        raise SystemExit("未找到 train.json/train_mini.json，请用 --annotations 指定官方标注文件")

    payload = json.loads(annotation_path.read_text(encoding="utf-8"))
    categories = {int(item["id"]): item for item in payload["categories"]}
    images = {int(item["id"]): item for item in payload["images"]}
    image_categories: dict[int, set[int]] = defaultdict(set)
    counts: Counter[int] = Counter()
    for annotation in payload["annotations"]:
        category_id = int(annotation["category_id"])
        image_id = int(annotation["image_id"])
        image_categories[image_id].add(category_id)
        counts[category_id] += 1

    kingdoms = {value.lower() for value in args.kingdom}
    eligible = []
    for category_id, count in counts.most_common():
        category = categories.get(category_id, {})
        kingdom = str(category.get("kingdom", "")).lower()
        if count < args.min_images or (kingdoms and kingdom not in kingdoms):
            continue
        eligible.append(category_id)
        if len(eligible) >= args.max_classes:
            break
    eligible_set = set(eligible)
    selected_counts: Counter[int] = Counter()
    manifest_path = args.output / "manifest.jsonl"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)

    with manifest_path.open("w", encoding="utf-8") as stream:
        for image_id, category_ids in image_categories.items():
            matching = [cid for cid in category_ids if cid in eligible_set and selected_counts[cid] < args.per_class]
            if not matching:
                continue
            item = images[image_id]
            source = args.dataset_root / item["file_name"]
            if not source.exists():
                continue
            for category_id in matching:
                category = categories[category_id]
                class_name = str(category.get("name") or category.get("scientific_name") or category_id)
                safe_class = class_name.replace("/", "_").replace("\\", "_")
                target = args.output / "all" / safe_class / source.name
                if not args.manifest_only:
                    link_or_copy(source, target, args.copy)
                selected_counts[category_id] += 1
                stream.write(json.dumps({
                    "source": "iNaturalist 2021",
                    "image_id": image_id,
                    "category_id": category_id,
                    "scientific_name": class_name,
                    "common_name": category.get("common_name"),
                    "kingdom": category.get("kingdom"),
                    "family": category.get("family"),
                    "genus": category.get("genus"),
                    "source_path": str(source),
                    "local_path": str(target),
                    "license": item.get("license"),
                    "url": item.get("url"),
                    "group_id": item.get("observation_id", image_id),
                }, ensure_ascii=False) + "\n")

    summary = {
        "classes": len(selected_counts),
        "images": sum(selected_counts.values()),
        "minimum": min(selected_counts.values(), default=0),
        "maximum": max(selected_counts.values(), default=0),
        "manifest": str(manifest_path),
    }
    (args.output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
