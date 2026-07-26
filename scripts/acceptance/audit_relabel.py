from __future__ import annotations

import csv
import json
from pathlib import Path


ROOT = Path(
    r"C:\Users\xin20\Desktop\WildLens_AI\Shijing_handoff_full_20260722_144737"
    r"\data\acceptance\real_world_v1"
)
NON_TARGET = {
    "mammal_002",
    "mammal_005",
    "mammal_008",
    "mammal_017",
    "mammal_019",
}


rows = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
for row in rows:
    if row["sample_id"] in NON_TARGET:
        row["expected"] = "negative"
        row["audit_note"] = "人工总览确认：无可验收的哺乳动物或鸟类目标"
    else:
        row["audit_note"] = ""
(ROOT / "manifest.json").write_text(
    json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8"
)
with (ROOT / "manifest.csv").open("w", encoding="utf-8-sig", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
