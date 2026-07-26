from __future__ import annotations

import json
import os
import random
import shutil
from collections import defaultdict, deque
from pathlib import Path

import yaml


PROJECT = Path(r"C:\Users\xin20\Desktop\WildLens_AI\Shijing_handoff_full_20260722_144737")
V3 = PROJECT / "data" / "yolo_datasets" / "wildlens"
V4 = PROJECT / "data" / "yolo_datasets" / "wildlens_v4"
V5 = PROJECT / "data" / "yolo_datasets" / "wildlens_v5"
SEED = 20260724
BIRD_TARGET = 500
NEGATIVE_TARGET = 150


def copy_base() -> None:
    for split in ("train", "val", "test"):
        for source in (V3 / "images" / split).glob("*"):
            if not source.is_file():
                continue
            destination = V5 / "images" / split / source.name
            destination.parent.mkdir(parents=True, exist_ok=True)
            if not destination.exists():
                os.link(source, destination)
        for source in (V3 / "labels" / split).glob("*.txt"):
            destination = V5 / "labels" / split / source.name
            destination.parent.mkdir(parents=True, exist_ok=True)
            if not destination.exists():
                shutil.copy2(source, destination)


def load_bird_species() -> dict[str, str]:
    result: dict[str, str] = {}
    manifest = V4 / "metadata" / "wcs_subset_bird_v4.jsonl"
    for line in manifest.read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        path = Path(record["local_image"])
        names = sorted(
            {
                str(box.get("scientific_name") or "unknown")
                for box in record.get("boxes", [])
            }
        )
        result[path.name] = "|".join(names) or "unknown"
    return result


def select_birds(new_names: set[str], species_by_name: dict[str, str]) -> list[str]:
    rng = random.Random(SEED)
    groups: dict[str, list[str]] = defaultdict(list)
    for name in sorted(new_names):
        groups[species_by_name.get(name, "unknown")].append(name)
    queues: dict[str, deque[str]] = {}
    for species, names in groups.items():
        rng.shuffle(names)
        queues[species] = deque(names)
    species_order = sorted(queues)
    rng.shuffle(species_order)
    selected: list[str] = []
    while len(selected) < BIRD_TARGET:
        progressed = False
        for species in species_order:
            if queues[species]:
                selected.append(queues[species].popleft())
                progressed = True
                if len(selected) >= BIRD_TARGET:
                    break
        if not progressed:
            break
    if len(selected) != BIRD_TARGET:
        raise RuntimeError(f"Only selected {len(selected)}/{BIRD_TARGET} birds")
    return selected


def add_training_files(names: list[str]) -> None:
    for name in names:
        source_image = V4 / "images" / "train" / name
        source_label = V4 / "labels" / "train" / f"{source_image.stem}.txt"
        destination_image = V5 / "images" / "train" / name
        destination_label = V5 / "labels" / "train" / source_label.name
        if not destination_image.exists():
            os.link(source_image, destination_image)
        if not destination_label.exists():
            shutil.copy2(source_label, destination_label)


V5.mkdir(parents=True, exist_ok=True)
copy_base()
v3_train = {path.name for path in (V3 / "images" / "train").glob("*") if path.is_file()}
v4_train = {path.name for path in (V4 / "images" / "train").glob("*") if path.is_file()}
new_names = v4_train - v3_train
new_negatives = sorted(name for name in new_names if name.startswith("wcs_empty_"))
new_birds = {name for name in new_names if not name.startswith("wcs_empty_")}
selected_birds = select_birds(new_birds, load_bird_species())
rng = random.Random(SEED)
rng.shuffle(new_negatives)
selected_negatives = new_negatives[:NEGATIVE_TARGET]
if len(selected_negatives) != NEGATIVE_TARGET:
    raise RuntimeError(f"Only selected {len(selected_negatives)}/{NEGATIVE_TARGET} negatives")
add_training_files(selected_birds + selected_negatives)
(V5 / "metadata").mkdir(exist_ok=True)
selection = {
    "baseline": str(V3),
    "source_pool": str(V4),
    "seed": SEED,
    "bird_images_added": selected_birds,
    "negative_images_added": selected_negatives,
    "validation_and_test_unchanged": True,
    "acceptance_data_included": False,
}
(V5 / "metadata" / "v5_selection.json").write_text(
    json.dumps(selection, ensure_ascii=False, indent=2), encoding="utf-8"
)
config = yaml.safe_load((V3 / "data.yaml").read_text(encoding="utf-8"))
config["path"] = V5.as_posix()
(V5 / "data.yaml").write_text(
    yaml.safe_dump(config, allow_unicode=True, sort_keys=False), encoding="utf-8"
)
print(
    json.dumps(
        {
            "base_train": len(v3_train),
            "added_birds": len(selected_birds),
            "added_negatives": len(selected_negatives),
            "v5_train": len(list((V5 / "images" / "train").glob("*"))),
        },
        ensure_ascii=False,
        indent=2,
    )
)
