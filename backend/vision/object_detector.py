"""Optional local object detector used before fine-grained species classification.

The application can run without this dependency, but when an Ultralytics-compatible
YOLO/MegaDetector weight exists, this module supplies stable target boxes for photos
and videos. Fine-grained species names still come from the 10k classifier/ARK rather
than from the coarse detector.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class DetectedRegion:
    bbox: tuple[int, int, int, int]
    category: str
    confidence: float
    coarse_label: str


_ANIMAL_NAMES = {
    "animal", "bird", "cat", "dog", "horse", "sheep", "cow", "elephant",
    "bear", "zebra", "giraffe", "deer", "boar", "monkey", "fox", "wolf",
    "tiger", "leopard", "lion", "rabbit", "squirrel", "snake", "fish",
}
_PERSON_NAMES = {"person", "human", "people"}
_VEHICLE_NAMES = {
    "vehicle", "car", "truck", "bus", "motorcycle", "bicycle", "boat",
    "train", "atv", "off-road vehicle",
}
_PLANT_NAMES = {
    "plant", "tree", "flower", "leaf", "grass", "shrub", "fungus", "mushroom",
}
_FIRE_NAMES = {"fire", "flame", "wildfire"}
_SMOKE_NAMES = {"smoke", "fog"}


def _coarse_category(name: str) -> str:
    normalized = name.strip().lower().replace("_", " ")
    if normalized in _PERSON_NAMES:
        return "person"
    if normalized in _VEHICLE_NAMES:
        return "vehicle"
    if normalized in _PLANT_NAMES:
        return "plant" if normalized not in {"fungus", "mushroom"} else "fungus"
    if normalized in _FIRE_NAMES:
        return "fire"
    if normalized in _SMOKE_NAMES:
        return "smoke"
    if normalized in _ANIMAL_NAMES:
        return "bird" if normalized == "bird" else "unknown"
    # MegaDetector commonly uses exactly animal/person/vehicle. Unknown detector
    # labels are intentionally not promoted to a precise species category.
    return "unknown"


class LocalObjectDetector:
    """Lazy Ultralytics detector wrapper.

    `model_path` may be a local `.pt`/`.onnx` file or a model alias accepted by
    Ultralytics (for example `yolo11n.pt`). Network auto-download is only attempted
    for simple aliases, never for a missing absolute/project path.
    """

    def __init__(self, model_path: str, confidence: float = 0.35) -> None:
        self.model_path = model_path
        self.confidence = confidence
        self.model: Any | None = None
        self.net: Any | None = None
        self.names: dict[int, str] = {}
        self.input_size = 640
        self.error = ""
        self._load()

    def _load(self) -> None:
        value = self.model_path.strip()
        if not value:
            return
        path = Path(value)
        looks_like_path = path.is_absolute() or len(path.parts) > 1
        if looks_like_path and not path.exists():
            self.error = f"detector weight not found: {path}"
            return
        try:
            from ultralytics import YOLO

            self.model = YOLO(str(path if path.exists() else value))
            return
        except Exception as exc:  # noqa: BLE001
            self.error = str(exc)
            self.model = None
        if path.exists() and path.suffix.lower() == ".onnx":
            try:
                self.net = cv2.dnn.readNetFromONNX(str(path))
                self.names = _load_class_names(path)
                self.error = ""
                logger.info("Local object detector using OpenCV DNN: %s", path)
                return
            except Exception as exc:  # noqa: BLE001
                self.error = str(exc)
        logger.warning("Local object detector disabled: %s", self.error)

    @property
    def available(self) -> bool:
        return self.model is not None or self.net is not None

    def detect(self, image_bgr: np.ndarray, max_results: int = 30) -> list[DetectedRegion]:
        if not self.available or image_bgr.size == 0:
            return []
        if self.net is not None:
            return self._detect_opencv(image_bgr, max_results=max_results)
        try:
            result = self.model.predict(
                source=image_bgr,
                conf=self.confidence,
                verbose=False,
                max_det=max_results,
            )[0]
            names = result.names or {}
            output: list[DetectedRegion] = []
            if result.boxes is None:
                return output
            for box in result.boxes:
                cls_id = int(box.cls.item())
                confidence = float(box.conf.item())
                label = str(names.get(cls_id, cls_id))
                x1, y1, x2, y2 = [int(round(value)) for value in box.xyxy[0].tolist()]
                if x2 <= x1 or y2 <= y1:
                    continue
                output.append(
                    DetectedRegion(
                        bbox=(x1, y1, x2 - x1, y2 - y1),
                        category=_coarse_category(label),
                        confidence=confidence,
                        coarse_label=label,
                    )
                )
            return output
        except Exception as exc:  # noqa: BLE001
            logger.warning("Local detector inference failed: %s", exc)
            return []

    def _detect_opencv(self, image_bgr: np.ndarray, max_results: int = 30) -> list[DetectedRegion]:
        height, width = image_bgr.shape[:2]
        blob = cv2.dnn.blobFromImage(
            image_bgr,
            scalefactor=1 / 255.0,
            size=(self.input_size, self.input_size),
            mean=(0, 0, 0),
            swapRB=True,
            crop=False,
        )
        try:
            self.net.setInput(blob)
            outputs = self.net.forward()
        except Exception as exc:  # noqa: BLE001
            logger.warning("OpenCV DNN detector inference failed: %s", exc)
            return []
        predictions = np.asarray(outputs)
        if predictions.ndim == 3:
            predictions = predictions[0]
        if predictions.ndim != 2:
            return []
        if predictions.shape[0] < predictions.shape[1] and predictions.shape[0] in {5, 6, 84, 85}:
            predictions = predictions.T
        boxes: list[list[int]] = []
        confidences: list[float] = []
        labels: list[str] = []
        for row in predictions:
            if row.size < 5:
                continue
            values = row.astype(float)
            obj_conf = 1.0
            class_scores = values[4:]
            if row.size > 6 and values[4] <= 1.0 and values[5:].size:
                obj_conf = max(0.0, min(1.0, values[4]))
                class_scores = values[5:]
            if class_scores.size:
                class_id = int(np.argmax(class_scores))
                score = float(class_scores[class_id]) * obj_conf
            else:
                class_id = 0
                score = float(values[4])
            if score < self.confidence:
                continue
            cx, cy, box_w, box_h = values[:4]
            scale_x = width / self.input_size
            scale_y = height / self.input_size
            if max(cx, cy, box_w, box_h) <= 1.5:
                cx *= width
                box_w *= width
                cy *= height
                box_h *= height
            else:
                cx *= scale_x
                box_w *= scale_x
                cy *= scale_y
                box_h *= scale_y
            x1 = int(round(cx - box_w / 2))
            y1 = int(round(cy - box_h / 2))
            box_w_i = int(round(box_w))
            box_h_i = int(round(box_h))
            if box_w_i <= 1 or box_h_i <= 1:
                continue
            boxes.append([max(0, x1), max(0, y1), min(width - max(0, x1), box_w_i), min(height - max(0, y1), box_h_i)])
            confidences.append(score)
            labels.append(self.names.get(class_id, str(class_id)))
        selected = cv2.dnn.NMSBoxes(boxes, confidences, self.confidence, 0.45)
        if len(selected) == 0:
            return []
        output: list[DetectedRegion] = []
        for raw_index in np.array(selected).flatten()[:max_results]:
            index = int(raw_index)
            x, y, box_w, box_h = boxes[index]
            output.append(
                DetectedRegion(
                    bbox=(x, y, box_w, box_h),
                    category=_coarse_category(labels[index]),
                    confidence=float(confidences[index]),
                    coarse_label=labels[index],
                )
            )
        return output


def _load_class_names(model_path: Path) -> dict[int, str]:
    candidates = [
        model_path.with_suffix(".classes.json"),
        model_path.with_suffix(".names.json"),
        model_path.with_name(f"{model_path.stem}.json"),
    ]
    for candidate in candidates:
        if not candidate.exists():
            continue
        try:
            raw = json.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(raw, dict) and "names" in raw:
            raw = raw["names"]
        if isinstance(raw, dict):
            return {int(key): str(value) for key, value in raw.items()}
        if isinstance(raw, list):
            return {index: str(item.get("name") if isinstance(item, dict) else item) for index, item in enumerate(raw)}
    return {
        0: "person",
        1: "bicycle",
        2: "car",
        3: "motorcycle",
        5: "bus",
        7: "truck",
        14: "bird",
        15: "cat",
        16: "dog",
        17: "horse",
        18: "sheep",
        19: "cow",
        20: "elephant",
        21: "bear",
        22: "zebra",
        23: "giraffe",
    }
