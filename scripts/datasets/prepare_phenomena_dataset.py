"""Index a licensed folder dataset for natural-phenomenon multi-label training.

Folder names may be classes such as fog/rain/snow/lightning/rainbow. A sidecar
CSV can later add multiple labels; this script creates a license-aware baseline manifest.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("--output", type=Path, default=Path("data/processed/phenomena/manifest.jsonl"))
    parser.add_argument("--source", required=True)
    parser.add_argument("--license", required=True)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with args.output.open("w", encoding="utf-8") as stream:
        for path in sorted(args.root.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in EXTENSIONS:
                continue
            relative = path.relative_to(args.root)
            label = relative.parts[0].lower().replace(" ", "_") if len(relative.parts) > 1 else "unknown"
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            stream.write(json.dumps({
                "source": args.source,
                "license": args.license,
                "path": str(path),
                "label": label,
                "group_id": str(relative.parent),
                "sha256": digest,
            }, ensure_ascii=False) + "\n")
            count += 1
    print(json.dumps({"images": count, "output": str(args.output)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
