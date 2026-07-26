"""Build a small, reproducible YOLO subset from official WCS bbox metadata.

Only WCS scientific names that are present in data/taxonomy/target_species.csv
are used. Images containing an unmapped boxed category are skipped so that
unlabelled animals do not silently become background during detector training.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import shutil
import urllib.request
import zipfile
from collections import defaultdict
from pathlib import Path
from typing import Any

import yaml

IMAGE_BASE_URLS = (
    "https://storage.googleapis.com/public-datasets-lila/wcs-unzipped/",
    "https://lilawildlife.blob.core.windows.net/lila-wildlife/wcs-unzipped/",
)
LICENSE = "CDLA-Permissive-1.0"


def stable_split(group_id: str) -> str:
    bucket = int(hashlib.sha256(group_id.encode("utf-8")).hexdigest()[:8], 16) % 10
    if bucket < 7:
        return "train"
    if bucket < 9:
        return "val"
    return "test"


def download(url: str, target: Path) -> None:
    if target.exists() and target.stat().st_size > 0:
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_suffix(target.suffix + ".part")
    request = urllib.request.Request(url, headers={"User-Agent": "WildLens-AI/2.0"})
    with urllib.request.urlopen(request, timeout=120) as response, partial.open("wb") as handle:
        shutil.copyfileobj(response, handle)
    partial.replace(target)


def download_wcs_image(relative_path: str, target: Path) -> str:
    errors: list[str] = []
    for base_url in IMAGE_BASE_URLS:
        url = base_url + relative_path
        try:
            download(url, target)
            return url
        except Exception as exc:
            errors.append(f"{url}: {exc}")
    raise RuntimeError("; ".join(errors))


def load_wcs(archive: Path) -> dict[str, Any]:
    with zipfile.ZipFile(archive) as bundle:
        names = [name for name in bundle.namelist() if name.lower().endswith(".json")]
        if not names:
            raise RuntimeError("WCS bbox archive contains no JSON metadata")
        with bundle.open(names[0]) as handle:
            return json.load(handle)


def load_targets(path: Path, allowed_classes: dict[str, int]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            scientific_name = str(row.get("scientific_name") or "").strip().lower()
            category = str(row.get("category") or "").strip().lower()
            if scientific_name and category in allowed_classes:
                result[scientific_name] = {**row, "class_id": allowed_classes[category]}
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--targets", type=Path, default=Path("data/taxonomy/target_species.csv"))
    parser.add_argument("--taxonomy-map", type=Path)
    parser.add_argument("--include-categories", nargs="+")
    parser.add_argument("--max-species", type=int, default=0)
    parser.add_argument("--manifest-name")
    parser.add_argument("--data-yaml", type=Path, default=Path("data/yolo_datasets/wildlens/data.yaml"))
    parser.add_argument("--per-species", type=int, default=25)
    parser.add_argument("--seed", type=int, default=20260722)
    parser.add_argument("--manifest-only", action="store_true")
    args = parser.parse_args()

    config = yaml.safe_load(args.data_yaml.read_text(encoding="utf-8"))
    root = Path(str(config.get("path") or args.data_yaml.parent)).resolve()
    raw_names = config.get("names") or {}
    if isinstance(raw_names, list):
        class_ids = {str(name).lower(): index for index, name in enumerate(raw_names)}
    else:
        class_ids = {str(name).lower(): int(index) for index, name in raw_names.items()}
    targets = load_targets(args.targets, class_ids)
    if args.taxonomy_map:
        targets.update(load_targets(args.taxonomy_map, class_ids))
    if args.include_categories:
        included = {item.strip().lower() for item in args.include_categories}
        targets = {name: target for name, target in targets.items() if target["category"].lower() in included}
    metadata = load_wcs(args.archive)
    categories = {int(item["id"]): str(item["name"]).strip().lower() for item in metadata["categories"]}
    mapped_category_ids = {
        category_id: targets[name]
        for category_id, name in categories.items()
        if name in targets
    }
    if not mapped_category_ids:
        raise RuntimeError("No WCS categories matched target_species.csv")

    images = {str(item["id"]): item for item in metadata["images"] if not item.get("corrupt")}
    annotations_by_image: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for annotation in metadata["annotations"]:
        if annotation.get("bbox") and str(annotation.get("image_id")) in images:
            annotations_by_image[str(annotation["image_id"])].append(annotation)

    candidates: dict[int, list[tuple[dict[str, Any], list[dict[str, Any]]]]] = defaultdict(list)
    for image_id, annotations in annotations_by_image.items():
        category_ids = {int(item["category_id"]) for item in annotations}
        # Strict mode: every visible boxed category must have a trusted coarse mapping.
        if not category_ids or not category_ids.issubset(mapped_category_ids):
            continue
        image = images[image_id]
        for category_id in category_ids:
            candidates[category_id].append((image, annotations))

    if args.max_species > 0:
        ranked_ids = sorted(candidates, key=lambda item: len(candidates[item]), reverse=True)[:args.max_species]
        candidates = defaultdict(list, {item: candidates[item] for item in ranked_ids})

    rng = random.Random(args.seed)
    selected: dict[str, tuple[dict[str, Any], list[dict[str, Any]]]] = {}
    selection_counts: dict[str, int] = {}
    for category_id, records in sorted(candidates.items()):
        rng.shuffle(records)
        seen_groups: set[str] = set()
        chosen = 0
        for image, annotations in records:
            group = str(image.get("location") or image.get("seq_id") or image["id"])
            # Prefer different locations/sequences before adding near-duplicates.
            if group in seen_groups and len(seen_groups) < args.per_species:
                continue
            seen_groups.add(group)
            selected[str(image["id"])] = (image, annotations)
            chosen += 1
            if chosen >= args.per_species:
                break
        selection_counts[categories[category_id]] = chosen

    if args.manifest_name:
        manifest_name = args.manifest_name
    elif args.include_categories:
        manifest_name = "wcs_subset_" + "_".join(sorted(included)) + ".jsonl"
    else:
        manifest_name = "wcs_subset.jsonl"
    manifest_path = root / "metadata" / manifest_name
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    downloaded = 0
    failures = 0
    with manifest_path.open("w", encoding="utf-8") as manifest:
        for image_id, (image, annotations) in sorted(selected.items()):
            relative_path = str(image["file_name"]).lstrip("/")
            group = str(image.get("location") or image.get("seq_id") or image_id)
            split = stable_split(group)
            suffix = Path(relative_path).suffix.lower() or ".jpg"
            local_name = f"wcs_{image_id}{suffix}"
            image_path = root / "images" / split / local_name
            label_path = root / "labels" / split / f"wcs_{image_id}.txt"
            width = float(image["width"])
            height = float(image["height"])
            labels: list[str] = []
            source_boxes: list[dict[str, Any]] = []
            for annotation in annotations:
                category_id = int(annotation["category_id"])
                target = mapped_category_ids[category_id]
                x, y, box_width, box_height = [float(value) for value in annotation["bbox"]]
                x = max(0.0, min(x, width))
                y = max(0.0, min(y, height))
                box_width = max(0.0, min(box_width, width - x))
                box_height = max(0.0, min(box_height, height - y))
                if box_width <= 1.0 or box_height <= 1.0:
                    continue
                labels.append(
                    f"{target['class_id']} {(x + box_width / 2) / width:.6f} "
                    f"{(y + box_height / 2) / height:.6f} {box_width / width:.6f} "
                    f"{box_height / height:.6f}"
                )
                source_boxes.append({
                    "scientific_name": categories[category_id],
                    "coarse_category": target["category"],
                    "bbox": annotation["bbox"],
                })
            if not labels:
                continue
            record = {
                "dataset": "WCS Camera Traps",
                "image_id": image_id,
                "split": split,
                "group_id": group,
                "source_url": IMAGE_BASE_URLS[0] + relative_path,
                "license": LICENSE,
                "local_image": str(image_path),
                "boxes": source_boxes,
            }
            manifest.write(json.dumps(record, ensure_ascii=False) + "\n")
            if args.manifest_only:
                continue
            try:
                resolved_url = download_wcs_image(relative_path, image_path)
                record["resolved_source_url"] = resolved_url
                label_path.parent.mkdir(parents=True, exist_ok=True)
                label_path.write_text("\n".join(labels) + "\n", encoding="utf-8")
                downloaded += 1
            except Exception as exc:  # resumable; manifest retains source URL
                failures += 1
                print(f"[WARN] {relative_path}: {exc}")

    summary = {
        "matched_species": len(mapped_category_ids),
        "selection_counts": selection_counts,
        "selected_images": len(selected),
        "downloaded": downloaded,
        "failures": failures,
        "manifest": str(manifest_path),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
