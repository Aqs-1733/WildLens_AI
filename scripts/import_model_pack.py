from __future__ import annotations

import argparse
import json
import shutil
import tempfile
import zipfile
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ONNX_DIR = PROJECT_ROOT / "models" / "onnx"
PRETRAINED_DIR = PROJECT_ROOT / "models" / "pretrained"
REGISTRY_DIR = PROJECT_ROOT / "models" / "registry"
ACTIVE_CONFIG = REGISTRY_DIR / "active_model.json"


def _read_json(path: Path, fallback):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return fallback


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _iter_files(root: Path) -> Iterable[Path]:
    return (item for item in root.rglob("*") if item.is_file())


def _extract_if_zip(path: Path) -> tuple[Path, tempfile.TemporaryDirectory[str] | None]:
    if path.is_dir():
        return path, None
    if path.suffix.lower() != ".zip":
        raise SystemExit(f"Model pack must be a directory or .zip: {path}")
    temp = tempfile.TemporaryDirectory(prefix="wildlens_model_pack_")
    with zipfile.ZipFile(path) as archive:
        archive.extractall(temp.name)
    return Path(temp.name), temp


def _score_file(path: Path, positive: tuple[str, ...], negative: tuple[str, ...] = ()) -> int:
    name = path.name.lower()
    score = 0
    for token in positive:
        if token in name:
            score += 5
    for token in negative:
        if token in name:
            score -= 8
    if name.endswith(".onnx"):
        score += 2
    return score


def _find_onnx(root: Path, positive: tuple[str, ...], negative: tuple[str, ...] = ()) -> Path | None:
    candidates = [item for item in _iter_files(root) if item.suffix.lower() == ".onnx"]
    ranked = sorted(
        ((item, _score_file(item, positive, negative)) for item in candidates),
        key=lambda pair: pair[1],
        reverse=True,
    )
    return ranked[0][0] if ranked and ranked[0][1] > 0 else None


def _find_metadata(root: Path, model_path: Path, positive: tuple[str, ...]) -> Path | None:
    preferred = [
        model_path.with_suffix(".classes.json"),
        model_path.with_suffix(".names.json"),
        model_path.with_name("classes.json"),
        model_path.with_name("metadata.json"),
    ]
    for item in preferred:
        if item.exists():
            return item
    json_files = [item for item in _iter_files(root) if item.suffix.lower() == ".json"]
    ranked = sorted(
        ((item, _score_file(item, positive + ("classes", "taxonomy", "metadata"))) for item in json_files),
        key=lambda pair: pair[1],
        reverse=True,
    )
    return ranked[0][0] if ranked and ranked[0][1] > 0 else None


def _copy_optional(source: Path | None, destination: Path | None) -> str:
    if not source or not destination:
        return ""
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    return str(destination.relative_to(PROJECT_ROOT).as_posix())


def import_pack(pack: Path, *, require_species: bool = True) -> dict:
    root, temp = _extract_if_zip(pack)
    try:
        ONNX_DIR.mkdir(parents=True, exist_ok=True)
        PRETRAINED_DIR.mkdir(parents=True, exist_ok=True)
        REGISTRY_DIR.mkdir(parents=True, exist_ok=True)

        species_model = _find_onnx(
            root,
            ("wildlife_species", "species", "inat", "classifier"),
            ("detector", "yolo", "mega", "behavior", "phenomena", "fire", "smoke"),
        )
        if require_species and not species_model:
            raise SystemExit(
                "No species classifier ONNX found. Expected wildlife_species.onnx "
                "or another species/classifier .onnx file."
            )
        species_meta = _find_metadata(root, species_model, ("species", "inat")) if species_model else None
        if species_model and not species_meta:
            raise SystemExit(
                f"No classes metadata found for {species_model.name}. Expected "
                "*.classes.json or classes.json with the model classes."
            )

        detector_model = _find_onnx(
            root,
            ("detector", "megadetector", "yolo"),
            ("species", "classifier", "behavior", "phenomena"),
        )
        detector_meta = _find_metadata(root, detector_model, ("detector", "yolo", "names")) if detector_model else None
        behavior_model = _find_onnx(root, ("behavior",), ("species", "detector", "phenomena"))
        behavior_meta = _find_metadata(root, behavior_model, ("behavior",)) if behavior_model else None
        phenomena_model = _find_onnx(root, ("phenomena", "phenomenon", "weather"), ("species", "detector"))
        phenomena_meta = _find_metadata(root, phenomena_model, ("phenomena", "weather")) if phenomena_model else None

        copied = {
            "species_model": _copy_optional(species_model, ONNX_DIR / "wildlife_species.onnx"),
            "species_metadata": _copy_optional(species_meta, ONNX_DIR / "wildlife_species.classes.json"),
            "detector_model": _copy_optional(detector_model, PRETRAINED_DIR / "yolo11n.onnx"),
            "detector_metadata": _copy_optional(detector_meta, PRETRAINED_DIR / "yolo11n.classes.json"),
            "behavior_model": _copy_optional(behavior_model, ONNX_DIR / "animal_behavior.onnx"),
            "behavior_metadata": _copy_optional(behavior_meta, ONNX_DIR / "animal_behavior.classes.json"),
            "phenomena_model": _copy_optional(phenomena_model, ONNX_DIR / "natural_phenomena.onnx"),
            "phenomena_metadata": _copy_optional(phenomena_meta, ONNX_DIR / "natural_phenomena.classes.json"),
        }
        card = next((item for item in _iter_files(root) if item.name.lower() in {"model_card.json", "metrics.json"}), None)
        copied["model_card"] = _copy_optional(card, REGISTRY_DIR / "active_model_card.json")

        active = _read_json(ACTIVE_CONFIG, {})
        active.update(
            {
                "active_species_model": "./models/onnx/wildlife_species.onnx"
                if copied["species_model"]
                else active.get("active_species_model"),
                "active_detector_model": "./models/pretrained/yolo11n.onnx"
                if copied["detector_model"]
                else active.get("active_detector_model"),
                "active_behavior_model": "./models/onnx/animal_behavior.onnx"
                if copied["behavior_model"]
                else active.get("active_behavior_model"),
                "active_phenomena_model": "./models/onnx/natural_phenomena.onnx"
                if copied["phenomena_model"]
                else active.get("active_phenomena_model"),
                "runtime": "onnxruntime-cpu",
                "deployment": "local-cpu-web-and-mobile-backend",
                "updated_at": datetime.now(UTC).isoformat(),
            }
        )
        _write_json(ACTIVE_CONFIG, active)
        return {"copied": copied, "active_model_config": str(ACTIVE_CONFIG)}
    finally:
        if temp:
            temp.cleanup()


def main() -> int:
    parser = argparse.ArgumentParser(description="Import an AutoDL-exported 识境 model pack.")
    parser.add_argument("pack", type=Path, help="Directory or .zip containing ONNX model artifacts")
    parser.add_argument("--allow-missing-species", action="store_true")
    args = parser.parse_args()
    result = import_pack(args.pack, require_species=not args.allow_missing_species)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
