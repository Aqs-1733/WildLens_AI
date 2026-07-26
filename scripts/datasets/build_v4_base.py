from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import yaml


PROJECT = Path(r"C:\Users\xin20\Desktop\WildLens_AI\Shijing_handoff_full_20260722_144737")
SOURCE = PROJECT / "data" / "yolo_datasets" / "wildlens"
TARGET = PROJECT / "data" / "yolo_datasets" / "wildlens_v4"


def link_tree(relative: str) -> tuple[int, int]:
    source_root = SOURCE / relative
    target_root = TARGET / relative
    linked = skipped = 0
    for source in source_root.rglob("*"):
        if not source.is_file():
            continue
        destination = target_root / source.relative_to(source_root)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            skipped += 1
            continue
        os.link(source, destination)
        linked += 1
    return linked, skipped


TARGET.mkdir(parents=True, exist_ok=True)
stats = {}
for relative in ("images", "labels"):
    stats[relative] = link_tree(relative)
(TARGET / "metadata").mkdir(exist_ok=True)
for source in (SOURCE / "metadata").glob("*"):
    if source.is_file():
        shutil.copy2(source, TARGET / "metadata" / source.name)
config = yaml.safe_load((SOURCE / "data.yaml").read_text(encoding="utf-8"))
config["path"] = TARGET.as_posix()
(TARGET / "data.yaml").write_text(
    yaml.safe_dump(config, allow_unicode=True, sort_keys=False), encoding="utf-8"
)
(TARGET / "BASELINE_PROVENANCE.json").write_text(
    json.dumps(
        {
            "source": str(SOURCE),
            "method": "hardlink",
            "acceptance_data_included": False,
            "stats": stats,
        },
        ensure_ascii=False,
        indent=2,
    ),
    encoding="utf-8",
)
print(json.dumps(stats, ensure_ascii=False))
