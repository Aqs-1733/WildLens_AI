from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

from PIL import Image, UnidentifiedImageError

EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("--report", type=Path, default=Path("storage/logs/dataset_validation.json"))
    args = parser.parse_args()
    files = [p for p in args.root.rglob("*") if p.is_file() and p.suffix.lower() in EXTENSIONS]
    hashes: dict[str, str] = {}
    corrupt: list[str] = []
    duplicates: list[dict[str, str]] = []
    dimensions: Counter[str] = Counter()
    for path in files:
        try:
            with Image.open(path) as image:
                image.verify()
            with Image.open(path) as image:
                dimensions[f"{image.width}x{image.height}"] += 1
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if digest in hashes:
                duplicates.append({"path": str(path), "duplicate_of": hashes[digest]})
            else:
                hashes[digest] = str(path)
        except (OSError, UnidentifiedImageError, ValueError) as exc:
            corrupt.append(f"{path}: {exc}")
    report = {
        "root": str(args.root),
        "images": len(files),
        "unique": len(hashes),
        "corrupt": corrupt,
        "duplicates": duplicates,
        "top_dimensions": dimensions.most_common(20),
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key not in {"corrupt", "duplicates"}}, ensure_ascii=False, indent=2))
    return 1 if corrupt else 0


if __name__ == "__main__":
    raise SystemExit(main())
