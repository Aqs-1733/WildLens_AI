"""Split a JSONL manifest by camera/location/sequence without frame leakage."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def bucket(group: str, train: float, val: float) -> str:
    value = int(hashlib.sha256(group.encode("utf-8")).hexdigest()[:8], 16) / 0xFFFFFFFF
    if value < train:
        return "train"
    if value < train + val:
        return "val"
    return "test"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--output", type=Path, default=Path("data/processed/splits"))
    parser.add_argument("--group-fields", default="location,camera_id,sequence_id,seq_id")
    parser.add_argument("--train", type=float, default=0.70)
    parser.add_argument("--val", type=float, default=0.15)
    args = parser.parse_args()
    if args.train + args.val >= 1:
        raise SystemExit("train + val 必须小于 1")
    fields = [item.strip() for item in args.group_fields.split(",") if item.strip()]
    args.output.mkdir(parents=True, exist_ok=True)
    streams = {name: (args.output / f"{name}.jsonl").open("w", encoding="utf-8") for name in ("train", "val", "test")}
    counts = {name: 0 for name in streams}
    try:
        with args.manifest.open(encoding="utf-8") as source:
            for line_number, line in enumerate(source, 1):
                if not line.strip():
                    continue
                item = json.loads(line)
                group = next((str(item.get(field)) for field in fields if item.get(field) not in (None, "")), f"row-{line_number}")
                split = bucket(group, args.train, args.val)
                item["split"] = split
                item["split_group"] = group
                streams[split].write(json.dumps(item, ensure_ascii=False) + "\n")
                counts[split] += 1
    finally:
        for stream in streams.values():
            stream.close()
    print(json.dumps(counts, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
