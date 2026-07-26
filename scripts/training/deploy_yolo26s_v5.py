from __future__ import annotations

import hashlib
import shutil
from pathlib import Path


PROJECT = Path(r"C:\Users\xin20\Desktop\WildLens_AI\Shijing_handoff_full_20260722_144737")
SOURCE = (
    PROJECT
    / "models"
    / "trained"
    / "runs"
    / "detect"
    / "wildlens_wcs_mammal_bird_v5"
    / "weights"
)
TARGET = PROJECT / "models" / "trained"
FILES = {
    "best.onnx": "wildlens_yolo26s_mammal_bird_v5.onnx",
    "best.pt": "wildlens_yolo26s_mammal_bird_v5.pt",
    "best.classes.json": "wildlens_yolo26s_mammal_bird_v5.classes.json",
}


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


for source_name, target_name in FILES.items():
    source = SOURCE / source_name
    target = TARGET / target_name
    if not source.exists():
        raise FileNotFoundError(source)
    shutil.copy2(source, target)
    if digest(source) != digest(target):
        raise RuntimeError(f"Hash mismatch after copy: {target}")

env_path = PROJECT / ".env"
backup = PROJECT / ".env.pre_v5.bak"
if not backup.exists():
    shutil.copy2(env_path, backup)
lines = env_path.read_text(encoding="utf-8").splitlines()
old = "YOLO_MODEL_PATH=./models/trained/wildlens_yolo26s_mammal_bird_v3.onnx"
new = "YOLO_MODEL_PATH=./models/trained/wildlens_yolo26s_mammal_bird_v5.onnx"
replaced = False
for index, line in enumerate(lines):
    if line.startswith("YOLO_MODEL_PATH="):
        if line not in {old, new}:
            raise RuntimeError(f"Unexpected YOLO_MODEL_PATH: {line}")
        lines[index] = new
        replaced = True
if not replaced:
    raise RuntimeError("YOLO_MODEL_PATH not found")
env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
print(new)
print(f"backup={backup}")
