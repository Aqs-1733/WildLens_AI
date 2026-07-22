from __future__ import annotations
import csv, json
from pathlib import Path

source = Path("data/taxonomy/target_species.csv")
target = Path("data/taxonomy/target_species.json")
with source.open(encoding="utf-8-sig", newline="") as stream:
    rows = list(csv.DictReader(stream))
target.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"exported {len(rows)} taxa -> {target}")
