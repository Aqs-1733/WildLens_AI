"""Create a target-species subset from an already downloaded Pl@ntNet-300K v1.1.

The complete archive is downloaded from Zenodo DOI 10.5281/zenodo.5645731.
This script avoids guessing an unstable file URL and works with the official
metadata shipped by the dataset.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
from collections import defaultdict
from pathlib import Path


def load_targets(csv_path: Path) -> set[str]:
    with csv_path.open(encoding="utf-8-sig", newline="") as stream:
        return {
            row["scientific_name"].strip().lower()
            for row in csv.DictReader(stream)
            if row.get("kingdom") == "Plantae" and row.get("scientific_name")
        }


def link_or_copy(source: Path, target: Path, copy: bool) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        return
    if copy:
        shutil.copy2(source, target)
    else:
        try:
            os.link(source, target)
        except OSError:
            shutil.copy2(source, target)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset_root", type=Path)
    parser.add_argument("--targets", type=Path, default=Path("data/taxonomy/target_species.csv"))
    parser.add_argument("--output", type=Path, default=Path("data/processed/plantnet_subset"))
    parser.add_argument("--per-species", type=int, default=500)
    parser.add_argument("--copy", action="store_true", help="复制而不是硬链接")
    args = parser.parse_args()

    species_map = json.loads((args.dataset_root / "plantnet300K_species_id_2_name.json").read_text(encoding="utf-8"))
    metadata = json.loads((args.dataset_root / "plantnet300K_metadata.json").read_text(encoding="utf-8"))
    targets = load_targets(args.targets)
    allowed_ids = {
        str(species_id): name
        for species_id, name in species_map.items()
        if str(name).strip().lower() in targets
    }
    counts: dict[str, int] = defaultdict(int)
    manifest = args.output / "manifest.jsonl"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    with manifest.open("w", encoding="utf-8") as out:
        for image_id, item in metadata.items():
            species_id = str(item.get("species_id", ""))
            if species_id not in allowed_ids or counts[species_id] >= args.per_species:
                continue
            split = str(item.get("split", "train"))
            candidates = [
                args.dataset_root / split / species_id / f"{image_id}.jpg",
                args.dataset_root / str(item.get("path", "")),
            ]
            source = next((path for path in candidates if path.exists()), None)
            if source is None:
                continue
            target = args.output / split / species_id / source.name
            link_or_copy(source, target, args.copy)
            counts[species_id] += 1
            out.write(json.dumps({
                "image_id": image_id,
                "species_id": species_id,
                "scientific_name": allowed_ids[species_id],
                "split": split,
                "path": str(target),
                "author": item.get("author"),
                "license": item.get("license"),
            }, ensure_ascii=False) + "\n")
    print(json.dumps({allowed_ids[key]: value for key, value in counts.items()}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
