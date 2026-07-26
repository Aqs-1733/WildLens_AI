from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

import yaml
from PIL import Image, UnidentifiedImageError

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}
SPLITS = ("train", "val", "test")


def image_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a YOLO detection dataset.")
    parser.add_argument("data_yaml", type=Path)
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("storage/logs/yolo_dataset_validation.json"),
    )
    args = parser.parse_args()

    config_path = args.data_yaml.resolve()
    config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    root_value = Path(str(config.get("path") or config_path.parent))
    root = root_value if root_value.is_absolute() else (config_path.parent / root_value).resolve()
    raw_names = config.get("names") or {}
    if isinstance(raw_names, list):
        names = {index: str(name) for index, name in enumerate(raw_names)}
    else:
        names = {int(index): str(name) for index, name in raw_names.items()}

    errors: list[dict[str, object]] = []
    warnings: list[dict[str, object]] = []
    class_counts: Counter[int] = Counter()
    split_counts: dict[str, dict[str, int]] = {}
    digest_to_split: dict[str, tuple[str, str]] = {}

    for split in SPLITS:
        image_value = config.get(split, f"images/{split}")
        image_dir = Path(str(image_value))
        if not image_dir.is_absolute():
            image_dir = root / image_dir
        label_dir = root / "labels" / split
        images = sorted(
            path for path in image_dir.rglob("*")
            if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
        ) if image_dir.exists() else []
        labeled_images = 0
        boxes = 0

        for image_path in images:
            relative = image_path.relative_to(image_dir)
            label_path = (label_dir / relative).with_suffix(".txt")
            try:
                with Image.open(image_path) as image:
                    image.verify()
            except (OSError, ValueError, UnidentifiedImageError) as exc:
                errors.append({"kind": "corrupt_image", "path": str(image_path), "detail": str(exc)})
                continue

            digest = image_digest(image_path)
            previous = digest_to_split.get(digest)
            if previous and previous[0] != split:
                errors.append({
                    "kind": "cross_split_duplicate",
                    "path": str(image_path),
                    "duplicate_of": previous[1],
                })
            else:
                digest_to_split[digest] = (split, str(image_path))

            if not label_path.exists():
                warnings.append({"kind": "missing_label_or_background", "path": str(image_path)})
                continue
            lines = [line.strip() for line in label_path.read_text(encoding="utf-8-sig").splitlines() if line.strip()]
            if lines:
                labeled_images += 1
            for line_number, line in enumerate(lines, start=1):
                fields = line.split()
                if len(fields) != 5:
                    errors.append({"kind": "invalid_field_count", "path": str(label_path), "line": line_number})
                    continue
                try:
                    class_id = int(fields[0])
                    coordinates = [float(value) for value in fields[1:]]
                except ValueError:
                    errors.append({"kind": "invalid_number", "path": str(label_path), "line": line_number})
                    continue
                if class_id not in names:
                    errors.append({"kind": "unknown_class", "path": str(label_path), "line": line_number, "class_id": class_id})
                if any(value < 0.0 or value > 1.0 for value in coordinates):
                    errors.append({"kind": "coordinate_out_of_range", "path": str(label_path), "line": line_number})
                if coordinates[2] <= 0.0 or coordinates[3] <= 0.0:
                    errors.append({"kind": "non_positive_box", "path": str(label_path), "line": line_number})
                class_counts[class_id] += 1
                boxes += 1

        orphan_labels = 0
        if label_dir.exists():
            image_stems = {str(path.relative_to(image_dir).with_suffix("")) for path in images}
            for label_path in label_dir.rglob("*.txt"):
                label_stem = str(label_path.relative_to(label_dir).with_suffix(""))
                if label_stem not in image_stems:
                    orphan_labels += 1
                    errors.append({"kind": "orphan_label", "path": str(label_path)})

        split_counts[split] = {
            "images": len(images),
            "labeled_images": labeled_images,
            "boxes": boxes,
            "orphan_labels": orphan_labels,
        }

    report = {
        "ok": not errors,
        "data_yaml": str(config_path),
        "root": str(root),
        "classes": names,
        "splits": split_counts,
        "class_box_counts": {names.get(index, str(index)): class_counts[index] for index in names},
        "errors": errors,
        "warnings": warnings,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key not in {"errors", "warnings"}}, ensure_ascii=False, indent=2))
    print(f"errors={len(errors)} warnings={len(warnings)} report={args.report}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
