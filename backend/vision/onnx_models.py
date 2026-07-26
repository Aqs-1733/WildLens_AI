"""Optional ONNX inference for trained species, behavior and phenomenon models."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import cv2
import numpy as np

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class Prediction:
    label: str
    confidence: float
    alternatives: list[dict[str, Any]]
    scientific_name: str = ""
    common_name: str = ""
    category: str = "unknown"
    taxonomy: dict[str, str] = field(default_factory=dict)
    is_unknown: bool = False


class ONNXImageClassifier:
    def __init__(self, model_path: Path, classes_path: Path | None = None) -> None:
        self.model_path = model_path
        self.classes_path = classes_path or model_path.with_suffix(".classes.json")
        self.session = None
        self.input_name = ""
        self.input_height = 224
        self.input_width = 224
        self.class_metadata: list[dict[str, Any]] = []
        self.unknown_threshold = 0.25
        if not model_path.exists() or not self.classes_path.exists():
            return
        try:
            import onnxruntime as ort

            available = ort.get_available_providers()
            preferred = [name for name in ("CUDAExecutionProvider", "CPUExecutionProvider") if name in available]
            self.session = ort.InferenceSession(str(model_path), providers=preferred or available)
            input_meta = self.session.get_inputs()[0]
            self.input_name = input_meta.name
            shape = input_meta.shape
            if len(shape) == 4:
                if isinstance(shape[2], int):
                    self.input_height = shape[2]
                if isinstance(shape[3], int):
                    self.input_width = shape[3]
            raw = json.loads(self.classes_path.read_text(encoding="utf-8"))
            if isinstance(raw, dict) and "classes" in raw:
                self.unknown_threshold = float(raw.get("unknown_threshold", 0.25))
                raw_classes = raw["classes"]
            else:
                raw_classes = raw
            if isinstance(raw_classes, dict):
                raw_classes = [raw_classes.get(str(index), raw_classes.get(index, str(index))) for index in range(len(raw_classes))]
            if not isinstance(raw_classes, list):
                raise ValueError("classes metadata must be a list or mapping")
            for index, item in enumerate(raw_classes):
                if isinstance(item, dict):
                    metadata = dict(item)
                    metadata.setdefault("index", index)
                    metadata.setdefault("scientific_name", str(item.get("name") or item.get("label") or index))
                    metadata.setdefault("common_name_zh", "")
                    metadata.setdefault("common_name_en", "")
                    metadata.setdefault("category", "unknown")
                else:
                    metadata = {
                        "index": index,
                        "scientific_name": str(item),
                        "common_name_zh": "",
                        "common_name_en": "",
                        "category": "unknown",
                    }
                self.class_metadata.append(metadata)
        except Exception as exc:  # noqa: BLE001
            logger.warning("ONNX model disabled (%s): %s", model_path.name, exc)
            self.session = None
            self.class_metadata = []

    @property
    def available(self) -> bool:
        return self.session is not None and bool(self.class_metadata)

    @staticmethod
    def _candidate(metadata: dict[str, Any], confidence: float) -> dict[str, Any]:
        scientific = str(metadata.get("scientific_name") or metadata.get("name") or "")
        common = str(metadata.get("common_name_zh") or metadata.get("common_name_en") or "")
        return {
            "name": common or scientific,
            "common_name": common,
            "scientific_name": scientific,
            "category": str(metadata.get("category") or "unknown"),
            "confidence": confidence,
            "taxonomy": {
                rank: str(metadata.get(rank) or "")
                for rank in ("kingdom", "phylum", "class", "order", "family", "genus")
            },
        }

    def predict(self, image_bgr: np.ndarray, top_k: int = 5) -> Prediction | None:
        if not self.available or image_bgr.size == 0:
            return None
        image = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
        image = cv2.resize(image, (self.input_width, self.input_height), interpolation=cv2.INTER_AREA)
        tensor = image.astype(np.float32) / 255.0
        tensor = (tensor - np.array([0.485, 0.456, 0.406], dtype=np.float32)) / np.array(
            [0.229, 0.224, 0.225], dtype=np.float32
        )
        tensor = np.transpose(tensor, (2, 0, 1))[None, ...]
        logits = np.asarray(self.session.run(None, {self.input_name: tensor})[0])[0].astype(np.float64)
        logits -= logits.max()
        probabilities = np.exp(logits)
        probabilities /= probabilities.sum() or 1.0
        indexes = probabilities.argsort()[::-1][: max(1, top_k)]
        best_index = int(indexes[0])
        best_confidence = float(probabilities[best_index])
        best_meta = self.class_metadata[best_index]
        candidates = [
            self._candidate(self.class_metadata[int(index)], float(probabilities[int(index)]))
            for index in indexes
            if int(index) < len(self.class_metadata)
        ]
        scientific = str(best_meta.get("scientific_name") or "")
        common = str(best_meta.get("common_name_zh") or best_meta.get("common_name_en") or "")
        is_unknown = best_confidence < self.unknown_threshold
        return Prediction(
            label="unknown" if is_unknown else scientific or common,
            confidence=best_confidence,
            alternatives=candidates if is_unknown else candidates[1:],
            scientific_name=scientific,
            common_name=common,
            category=str(best_meta.get("category") or "unknown"),
            taxonomy={
                rank: str(best_meta.get(rank) or "")
                for rank in ("kingdom", "phylum", "class", "order", "family", "genus")
            },
            is_unknown=is_unknown,
        )


class LocalNatureModels:
    def __init__(self, species_path: str, behavior_path: str, phenomena_path: str) -> None:
        self.species = ONNXImageClassifier(Path(species_path))
        self.behavior = ONNXImageClassifier(Path(behavior_path))
        self.phenomena = ONNXImageClassifier(Path(phenomena_path))

    @property
    def any_available(self) -> bool:
        return self.species.available or self.behavior.available or self.phenomena.available
