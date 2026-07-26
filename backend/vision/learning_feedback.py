from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.core.config import get_settings
from backend.models import AnalysisJob, Detection, MediaVariant
from backend.vision.active_learning_memory import active_learning_memory
from backend.vision.bioclip_classifier import bioclip_classifier

logger = logging.getLogger(__name__)


def _safe_crop(image: np.ndarray, bbox: dict[str, Any] | None) -> np.ndarray:
    if image is None or image.size == 0:
        return image
    if not isinstance(bbox, dict):
        return image
    height, width = image.shape[:2]
    try:
        x = max(0, min(width - 1, int(float(bbox.get("x", 0.0)) * width)))
        y = max(0, min(height - 1, int(float(bbox.get("y", 0.0)) * height)))
        w = max(1, int(float(bbox.get("width", 1.0)) * width))
        h = max(1, int(float(bbox.get("height", 1.0)) * height))
    except (TypeError, ValueError):
        return image
    x2 = max(x + 1, min(width, x + w))
    y2 = max(y + 1, min(height, y + h))
    crop = image[y:y2, x:x2]
    return crop if crop is not None and crop.size else image


def _load_detection_image(db: Session, detection: Detection) -> np.ndarray | None:
    job = db.get(AnalysisJob, detection.job_id)
    if not job or not job.media:
        return None
    source = Path(job.media.stored_path)
    if job.media.media_type == "image":
        return cv2.imread(str(source), cv2.IMREAD_COLOR)

    playback = db.scalar(
        select(MediaVariant).where(
            MediaVariant.media_id == job.media.id,
            MediaVariant.kind == "playback",
        )
    )
    video_path = Path(playback.stored_path) if playback else source
    if not video_path.exists():
        return None
    capture = cv2.VideoCapture(str(video_path))
    try:
        if not capture.isOpened():
            return None
        capture.set(cv2.CAP_PROP_POS_MSEC, max(0, int(detection.timestamp_ms or 0)))
        ok, frame = capture.read()
        return frame if ok else None
    finally:
        capture.release()


def learn_labeled_image(
    image_bgr: np.ndarray,
    *,
    scientific_name: str,
    common_name: str = "",
    category: str = "unknown",
    label_source: str,
    label_confidence: float,
    source_detection_id: int | None = None,
    validator: str = "",
    notes: str = "",
) -> dict[str, Any]:
    settings = get_settings()
    if not active_learning_memory.enabled:
        return {"stored": False, "reason": "active learning disabled"}
    if not scientific_name.strip():
        return {"stored": False, "reason": "missing scientific name"}
    accepted = float(label_confidence or 0.0) >= float(settings.active_learning_accept_min_confidence)
    if image_bgr is None or image_bgr.size == 0:
        return {"stored": False, "reason": "empty image"}
    try:
        vector = bioclip_classifier.encode_image(image_bgr)
        row_id = active_learning_memory.store_labeled_vector(
            vector,
            scientific_name=scientific_name,
            common_name=common_name,
            category=category,
            label_source=label_source,
            label_confidence=label_confidence,
            accepted_for_runtime=accepted,
            source_detection_id=source_detection_id,
            validator=validator,
            notes=notes,
        )
        return {
            "stored": row_id is not None,
            "row_id": row_id,
            "accepted_for_runtime": accepted,
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("Active-learning feedback was not stored: %s", exc)
        return {"stored": False, "error": str(exc)}


def learn_from_detection_correction(
    db: Session,
    detection: Detection,
    *,
    scientific_name: str,
    common_name: str = "",
    category: str = "unknown",
    label_source: str,
    label_confidence: float,
    validator: str = "",
    notes: str = "",
) -> dict[str, Any]:
    frame = _load_detection_image(db, detection)
    if frame is None:
        return {"stored": False, "reason": "source media unavailable"}
    crop = _safe_crop(frame, detection.bbox if isinstance(detection.bbox, dict) else None)
    return learn_labeled_image(
        crop,
        scientific_name=scientific_name,
        common_name=common_name,
        category=category,
        label_source=label_source,
        label_confidence=label_confidence,
        source_detection_id=detection.id,
        validator=validator,
        notes=notes,
    )
