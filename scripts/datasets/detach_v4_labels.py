from __future__ import annotations

import os
import shutil
from pathlib import Path


PROJECT = Path(r"C:\Users\xin20\Desktop\WildLens_AI\Shijing_handoff_full_20260722_144737")
SOURCE = PROJECT / "data" / "yolo_datasets" / "wildlens" / "labels"
TARGET = PROJECT / "data" / "yolo_datasets" / "wildlens_v4" / "labels"


detached = 0
for source in SOURCE.rglob("*"):
    if not source.is_file():
        continue
    destination = TARGET / source.relative_to(SOURCE)
    if not destination.exists():
        continue
    # Remove only the v4 directory entry, leaving the v3 hard-link entry intact.
    destination.unlink()
    shutil.copy2(source, destination)
    if os.stat(source).st_ino == os.stat(destination).st_ino:
        raise RuntimeError(f"Label is still linked: {destination}")
    detached += 1
print(f"detached_labels={detached}")
