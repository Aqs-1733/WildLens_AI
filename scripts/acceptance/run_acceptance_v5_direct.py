from __future__ import annotations

import csv
import json
import statistics
import time
from pathlib import Path

import cv2

from backend.vision.object_detector import LocalObjectDetector


PROJECT = Path(r"C:\Users\xin20\Desktop\WildLens_AI\Shijing_handoff_full_20260722_144737")
ROOT = PROJECT / "data" / "acceptance" / "real_world_v1"
MODEL = (
    PROJECT
    / "models"
    / "trained"
    / "runs"
    / "detect"
    / "wildlens_wcs_mammal_bird_v5"
    / "weights"
    / "best.onnx"
)


def is_pass(expected: str, categories: list[str]) -> bool:
    if expected == "negative":
        return not any(category in {"mammal", "bird"} for category in categories)
    return expected in categories


manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
detector = LocalObjectDetector(str(MODEL), confidence=0.35)
if not detector.available:
    raise RuntimeError(detector.error)
rows = []
for index, sample in enumerate(manifest, 1):
    image = cv2.imread(str(ROOT / sample["local_path"]))
    started = time.perf_counter()
    detections = detector.detect(image)
    seconds = time.perf_counter() - started
    categories = [item.category for item in detections]
    row = {
        "sample_id": sample["sample_id"],
        "expected": sample["expected"],
        "local_path": sample["local_path"],
        "pass": is_pass(sample["expected"], categories),
        "categories": "|".join(categories),
        "confidences": "|".join(f"{item.confidence:.4f}" for item in detections),
        "boxes": json.dumps([item.bbox for item in detections]),
        "seconds": round(seconds, 4),
    }
    rows.append(row)
    print(
        f"[{index:02d}/{len(manifest)}] {sample['sample_id']} "
        f"{'PASS' if row['pass'] else 'FAIL'} {categories} {seconds:.3f}s",
        flush=True,
    )
with (ROOT / "results_v5.csv").open("w", encoding="utf-8-sig", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
summary = {
    "model": str(MODEL),
    "threshold": 0.35,
    "total": len(rows),
    "pass": sum(bool(row["pass"]) for row in rows),
    "by_expected": {
        expected: {
            "total": sum(row["expected"] == expected for row in rows),
            "pass": sum(row["expected"] == expected and bool(row["pass"]) for row in rows),
        }
        for expected in ("mammal", "bird", "negative")
    },
    "latency_seconds": {
        "median": round(statistics.median(row["seconds"] for row in rows), 4),
        "mean": round(statistics.mean(row["seconds"] for row in rows), 4),
    },
}
(ROOT / "summary_v5.json").write_text(
    json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
)
print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
