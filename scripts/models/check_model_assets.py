from __future__ import annotations
import json
from pathlib import Path

registry = json.loads(Path("data/manifests/model_registry.json").read_text(encoding="utf-8"))
missing = []
for item in registry:
    path = item.get("path", "")
    exists = path.startswith("backend/") or path.startswith("ARK ") or Path(path).exists()
    print(f"[{'READY' if exists else 'OPTIONAL'}] {item['id']}: {path}")
    if item["status"] == "builtin" and not exists:
        missing.append(path)
raise SystemExit(1 if missing else 0)
