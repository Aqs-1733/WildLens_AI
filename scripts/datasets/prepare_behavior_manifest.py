"""Normalize Animal Kingdom/MammalNet style clip metadata into one JSONL manifest."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

ALIASES = {
    "eat": "feeding", "eating": "feeding", "feed": "feeding",
    "walk": "walking", "run": "running", "rest": "resting", "sleep": "resting",
    "alert": "vigilance", "groom": "grooming", "fight": "fighting",
    "parenting": "parental_care", "court": "courtship",
}


def normalize(value: str) -> str:
    key = value.strip().lower().replace(" ", "_").replace("-", "_")
    return ALIASES.get(key, key)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("metadata", type=Path, help="CSV或JSONL，至少包含video/path与label/action")
    parser.add_argument("--output", type=Path, default=Path("data/processed/behavior/manifest.jsonl"))
    parser.add_argument("--source", default="custom")
    args = parser.parse_args()
    rows = []
    if args.metadata.suffix.lower() == ".jsonl":
        rows = [json.loads(line) for line in args.metadata.read_text(encoding="utf-8").splitlines() if line.strip()]
    else:
        with args.metadata.open(encoding="utf-8-sig", newline="") as stream:
            rows = list(csv.DictReader(stream))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    with args.output.open("w", encoding="utf-8") as stream:
        for index, row in enumerate(rows):
            video = row.get("video") or row.get("path") or row.get("file_name") or row.get("clip")
            label = row.get("label") or row.get("action") or row.get("behavior")
            if not video or not label:
                continue
            item = {
                "source": args.source,
                "video": str(video),
                "behavior": normalize(str(label)),
                "species": row.get("species") or row.get("animal"),
                "start_seconds": float(row.get("start_seconds") or row.get("start") or 0),
                "end_seconds": float(row.get("end_seconds") or row.get("end") or 0),
                "group_id": str(row.get("source_video") or row.get("video_id") or video),
                "individual_id": row.get("individual_id"),
                "location": row.get("location"),
                "row_id": index,
            }
            stream.write(json.dumps(item, ensure_ascii=False) + "\n")
            written += 1
    print(json.dumps({"written": written, "output": str(args.output)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
