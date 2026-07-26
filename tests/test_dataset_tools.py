from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_dataset_manifests_are_nonempty():
    root = Path(__file__).resolve().parents[1]
    sources = json.loads((root / "data/manifests/dataset_sources.json").read_text(encoding="utf-8"))
    taxonomy = json.loads((root / "data/taxonomy/target_species.json").read_text(encoding="utf-8"))
    assert len(sources) >= 7
    assert len(taxonomy) >= 50
    assert {item["kingdom"] for item in taxonomy} >= {"Animalia", "Plantae"}


def test_model_asset_checker_runs():
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, "scripts/models/check_model_assets.py"],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "opencv-motion-v1" in result.stdout
