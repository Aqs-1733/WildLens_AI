from __future__ import annotations

import asyncio
import hashlib
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from sqlalchemy import select

from backend.core.config import PROJECT_ROOT, get_settings
from backend.core.database import SessionLocal
from backend.models import (
    AnalysisJob,
    Detection,
    JobStatus,
    MediaVariant,
    RiskEvent,
    Species,
    TrackKeyframe,
    VideoTrack,
    now_utc,
)
from backend.services.ai import ark_ai
from backend.services.taxon_names import localize_prediction, normalize_category
from backend.services.video_transcode import (
    VideoTranscodeError,
    transcode_browser_video,
    transcode_silent_video,
)
from backend.vision.ai_correction import correction_hint, merge_ai_correction, needs_ai_correction
from backend.vision.bioclip_classifier import BIOLOGICAL_CATEGORIES, bioclip_classifier
from backend.vision.learning_feedback import learn_labeled_image
from backend.vision.object_detector import LocalObjectDetector
from backend.vision.onnx_models import LocalNatureModels
from backend.vision.species_fusion import fuse_species_results, speciesnet_bbox_to_dict, speciesnet_category
from backend.vision.speciesnet_client import speciesnet_client

settings = get_settings()


def _resolve_model_path(value: str) -> str:
    path = Path(value)
    return str(path if path.is_absolute() else PROJECT_ROOT / path)


local_detector = LocalObjectDetector(
    _resolve_model_path(settings.yolo_model_path),
    settings.detection_confidence,
)

local_models = LocalNatureModels(
    _resolve_model_path(settings.custom_wildlife_model_path),
    _resolve_model_path(settings.behavior_model_path),
    _resolve_model_path(settings.phenomena_model_path),
)


def _vision_mode_label() -> str:
    parts = ["local-detector" if local_detector.available else "opencv"]
    if local_models.species.available:
        parts.append("onnx-species")
    if speciesnet_client.enabled:
        parts.append("speciesnet")
    if bioclip_classifier.enabled:
        parts.append("bioclip")
    if ark_ai.vision_enabled:
        parts.append("ark")
    return "+".join(parts)


ANIMAL_VIDEO_CATEGORIES = {
    "unknown",
    "mammal",
    "bird",
    "reptile",
    "amphibian",
    "fish",
    "insect",
    "arachnid",
    "mollusk",
    "crustacean",
    "invertebrate",
}


def _downgrade_unreliable_video_species(
    *,
    fused: dict[str, Any],
    fusion: dict[str, Any],
    speciesnet_result: dict[str, Any] | None,
    candidate_category: str,
) -> dict[str, Any]:
    scientific_name = str(fused.get("scientific_name") or "").strip()
    if not scientific_name:
        return fused
    fusion_status = str(fusion.get("fusion_status") or fusion.get("decision") or "").lower()
    if fusion_status not in {"review", "unknown"}:
        return fused
    annotated = dict(fused)
    annotated["fusion_status"] = "review"
    annotated["fusion_decision"] = "review"
    annotated["fusion_reason"] = (
        annotated.get("fusion_reason")
        or "视频帧证据不足或模型候选存在冲突，保留具体候选并提示人工复核。"
    )
    annotated["explanation"] = (
        annotated.get("explanation")
        or "视频帧存在运动模糊、遮挡或候选冲突；系统保留当前具体候选，建议结合关键帧、地点和相邻帧确认。"
    )
    return annotated

CATEGORY_COLORS = {
    "mammal": "#F5A623",
    "bird": "#55B8FF",
    "plant": "#35E58C",
    "angiosperm": "#35E58C",
    "gymnosperm": "#54C97B",
    "fern": "#68D391",
    "moss": "#8BCB6B",
    "algae": "#27C5A8",
    "insect": "#A87CFF",
    "arachnid": "#C087FF",
    "reptile": "#D6C64C",
    "amphibian": "#2FD5C4",
    "fish": "#3AA9FF",
    "mollusk": "#E39C75",
    "crustacean": "#EF8B8B",
    "invertebrate": "#D492FF",
    "fungus": "#E7A3FF",
    "lichen": "#B3D18D",
    "person": "#FF5A67",
    "vehicle": "#D7E2DE",
    "fire": "#FF354D",
    "smoke": "#FF824D",
    "phenomenon": "#65D6FF",
    "weather": "#65D6FF",
    "unknown": "#8CA9A0",
}


@dataclass(slots=True)
class Candidate:
    bbox: tuple[int, int, int, int]
    category: str
    score: float
    coarse_label: str = ""


@dataclass(slots=True)
class TrackState:
    track_id: int
    bbox: tuple[int, int, int, int]
    last_seen_ms: int


class SimpleIoUTracker:
    """Small dependency-free tracker used when ByteTrack/BoT-SORT extras are unavailable."""

    def __init__(self, max_age_ms: int = 2200, iou_threshold: float = 0.15) -> None:
        self.max_age_ms = max_age_ms
        self.iou_threshold = iou_threshold
        self.next_id = 1
        self.tracks: dict[int, TrackState] = {}

    @staticmethod
    def _iou(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> float:
        ax, ay, aw, ah = a
        bx, by, bw, bh = b
        left, top = max(ax, bx), max(ay, by)
        right, bottom = min(ax + aw, bx + bw), min(ay + ah, by + bh)
        intersection = max(0, right - left) * max(0, bottom - top)
        union = aw * ah + bw * bh - intersection
        return intersection / union if union > 0 else 0.0

    @staticmethod
    def _center_distance(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> float:
        ax, ay, aw, ah = a
        bx, by, bw, bh = b
        return math.hypot((ax + aw / 2) - (bx + bw / 2), (ay + ah / 2) - (by + bh / 2))

    def assign(self, bbox: tuple[int, int, int, int], timestamp_ms: int) -> int:
        self.tracks = {
            track_id: track
            for track_id, track in self.tracks.items()
            if timestamp_ms - track.last_seen_ms <= self.max_age_ms
        }
        best_id: int | None = None
        best_score = -1.0
        diagonal = max(1.0, math.hypot(bbox[2], bbox[3]))
        for track_id, track in self.tracks.items():
            iou = self._iou(bbox, track.bbox)
            distance_score = max(
                0.0,
                1.0 - self._center_distance(bbox, track.bbox) / (diagonal * 2.5),
            )
            score = iou * 0.7 + distance_score * 0.3
            if (iou >= self.iou_threshold or distance_score >= 0.62) and score > best_score:
                best_id, best_score = track_id, score
        if best_id is None:
            best_id = self.next_id
            self.next_id += 1
        self.tracks[best_id] = TrackState(best_id, bbox, timestamp_ms)
        return best_id


def _normalized_bbox(x: int, y: int, w: int, h: int, fw: int, fh: int) -> dict[str, float]:
    return {"x": x / fw, "y": y / fh, "width": w / fw, "height": h / fh}


def _plant_candidates(frame: np.ndarray) -> list[Candidate]:
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, np.array([25, 35, 25]), np.array([100, 255, 255]))
    kernel = np.ones((9, 9), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    area = frame.shape[0] * frame.shape[1]
    results: list[Candidate] = []
    for contour in sorted(contours, key=cv2.contourArea, reverse=True)[:5]:
        contour_area = cv2.contourArea(contour)
        if contour_area / area < settings.plant_min_area_ratio:
            continue
        x, y, w, h = cv2.boundingRect(contour)
        if w < 80 or h < 80:
            continue
        results.append(Candidate((x, y, w, h), "plant", min(0.85, 0.45 + contour_area / area)))
    return results[:2]


def _motion_candidates(frame: np.ndarray, subtractor: Any) -> list[Candidate]:
    foreground = subtractor.apply(frame)
    foreground = cv2.medianBlur(foreground, 5)
    _, foreground = cv2.threshold(foreground, 220, 255, cv2.THRESH_BINARY)
    contours, _ = cv2.findContours(foreground, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    frame_area = frame.shape[0] * frame.shape[1]
    output: list[Candidate] = []
    for contour in sorted(contours, key=cv2.contourArea, reverse=True)[:8]:
        area = cv2.contourArea(contour)
        if area / frame_area < 0.01:
            continue
        x, y, w, h = cv2.boundingRect(contour)
        if w < 40 or h < 40:
            continue
        output.append(Candidate((x, y, w, h), "unknown", min(0.75, 0.35 + area / frame_area)))
    return output[:3]


def _fire_score(frame: np.ndarray) -> float:
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    mask1 = cv2.inRange(hsv, np.array([0, 130, 150]), np.array([20, 255, 255]))
    mask2 = cv2.inRange(hsv, np.array([165, 130, 150]), np.array([179, 255, 255]))
    ratio = float(np.count_nonzero(mask1 | mask2)) / (frame.shape[0] * frame.shape[1])
    return min(1.0, ratio * 12)


def _crop_jpeg(frame: np.ndarray, bbox: tuple[int, int, int, int]) -> bytes:
    x, y, w, h = bbox
    crop = frame[max(0, y) : y + h, max(0, x) : x + w]
    ok, encoded = cv2.imencode(".jpg", crop, [int(cv2.IMWRITE_JPEG_QUALITY), 88])
    return encoded.tobytes() if ok else b""


def _context_crop_jpeg(
    frame: np.ndarray,
    bbox: tuple[int, int, int, int],
    padding_ratio: float = 0.45,
) -> bytes:
    """Crop with surrounding context so video AI review sees the whole animal when possible."""
    frame_height, frame_width = frame.shape[:2]
    x, y, w, h = bbox
    pad_x = int(w * padding_ratio)
    pad_y = int(h * padding_ratio)
    x1 = max(0, x - pad_x)
    y1 = max(0, y - pad_y)
    x2 = min(frame_width, x + w + pad_x)
    y2 = min(frame_height, y + h + pad_y)
    if x2 <= x1 or y2 <= y1:
        return _crop_jpeg(frame, bbox)
    crop = frame[y1:y2, x1:x2]
    ok, encoded = cv2.imencode(".jpg", crop, [int(cv2.IMWRITE_JPEG_QUALITY), 88])
    return encoded.tobytes() if ok else _crop_jpeg(frame, bbox)


def _result_confidence(result: dict[str, Any] | None) -> float:
    try:
        return float((result or {}).get("confidence") or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _unresolved_text(value: Any) -> bool:
    text = str(value or "").strip().lower()
    if not text:
        return True
    markers = (
        "待确认",
        "未确定",
        "低置信度",
        "不确定",
        "无法确定",
        "unknown",
        "unresolved",
        "no cv",
        "blank",
    )
    return any(marker in text for marker in markers)


def _usable_ai_video_result(result: dict[str, Any] | None) -> bool:
    if not result:
        return False
    source = str(result.get("model_source") or result.get("source") or "").lower()
    if "ark" not in source and "ai" not in source:
        return False
    confidence = _result_confidence(result)
    name = result.get("common_name") or result.get("label") or result.get("scientific_name")
    return confidence >= 0.55 and not _unresolved_text(name)


def _weak_bioclip_video_result(result: dict[str, Any] | None) -> bool:
    if not result:
        return False
    if bool(result.get("bioclip_is_weak")):
        return True
    similarity = float(result.get("bioclip_similarity") or 0.0)
    margin = float(result.get("bioclip_top1_margin") or 0.0)
    support = int(result.get("prototype_image_count") or 0)
    return (
        similarity < max(float(settings.bioclip_min_similarity), 0.62)
        or margin < max(float(settings.bioclip_min_margin), 0.02)
        or support < 2
    )


def _prefer_ai_video_result(
    *,
    ai_result: dict[str, Any] | None,
    bioclip_result: dict[str, Any] | None,
    fused_result: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not _usable_ai_video_result(ai_result) or not _weak_bioclip_video_result(bioclip_result):
        return None
    ai_confidence = _result_confidence(ai_result)
    fused_confidence = _result_confidence(fused_result)
    if ai_confidence + 0.08 < min(fused_confidence, 0.72):
        return None
    output = dict(ai_result or {})
    common_name = str(output.get("common_name") or output.get("label") or "").strip()
    if "（" in common_name:
        common_name = common_name.split("（", 1)[0].strip()
    if "(" in common_name:
        common_name = common_name.split("(", 1)[0].strip()
    if common_name:
        output["common_name"] = common_name
        output["label"] = common_name
    output["confidence"] = max(ai_confidence, min(fused_confidence, 0.68))
    output["model_source"] = "ark+bioclip-weak-review"
    output["fusion_status"] = "ai_corrected"
    output["fusion_decision"] = "ai_corrected"
    output["fusion_reason"] = (
        "ARK vision review provided a clearer visible-species candidate than the weak BioCLIP video-frame prototype match."
    )
    alternatives = list(output.get("alternatives") or [])
    if bioclip_result:
        alternatives.append(
            {
                "name": bioclip_result.get("common_name") or bioclip_result.get("scientific_name"),
                "scientific_name": bioclip_result.get("scientific_name") or "",
                "confidence": bioclip_result.get("confidence") or bioclip_result.get("bioclip_similarity") or 0.0,
                "source": "weak_bioclip_candidate",
            }
        )
    output["alternatives"] = alternatives[:5]
    evidence = list(output.get("evidence") or [])
    evidence.append(
        {
            "kind": "ai_video_override",
            "reason": "weak_bioclip_video_candidate",
            "ai_confidence": round(ai_confidence, 6),
            "bioclip_similarity": (bioclip_result or {}).get("bioclip_similarity"),
            "bioclip_top1_margin": (bioclip_result or {}).get("bioclip_top1_margin"),
        }
    )
    output["evidence"] = evidence
    return output


def _has_reliable_speciesnet_animal_evidence(result: dict[str, Any] | None) -> bool:
    if not result:
        return False
    if str(result.get("scientific_name") or "").strip():
        return True
    for item in result.get("detections") or []:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label") or item.get("category") or "").strip().lower()
        try:
            confidence = float(item.get("conf") or item.get("confidence") or 0.0)
        except (TypeError, ValueError):
            confidence = 0.0
        if label == "animal" and confidence >= 0.20:
            return True
    return False


def _skip_unverified_weak_video_species(
    *,
    result: dict[str, Any] | None,
    bioclip_result: dict[str, Any] | None,
    speciesnet_result: dict[str, Any] | None,
) -> bool:
    if not _weak_bioclip_video_result(bioclip_result):
        return False
    if _usable_ai_video_result(result):
        return False
    return not _has_reliable_speciesnet_animal_evidence(speciesnet_result)


def _speciesnet_detection_candidates(
    result: dict[str, Any] | None,
    frame_width: int,
    frame_height: int,
    enabled_targets: list[str],
) -> list[Candidate]:
    if not result:
        return []
    output: list[Candidate] = []
    min_confidence = max(0.20, min(settings.detection_confidence, 0.55))
    for item in result.get("detections") or []:
        if not isinstance(item, dict):
            continue
        confidence = float(item.get("conf") or item.get("confidence") or 0.0)
        if confidence < min_confidence:
            continue
        label = str(item.get("label") or item.get("category") or "animal").lower()
        if label == "human":
            category = "person"
        elif label == "vehicle":
            category = "vehicle"
        else:
            category = "unknown"
        if category == "person" and "people" not in enabled_targets:
            continue
        if category == "vehicle" and "people" not in enabled_targets:
            continue
        if category == "unknown" and "animals" not in enabled_targets:
            continue
        bbox = speciesnet_bbox_to_dict(item.get("bbox"))
        if not bbox:
            continue
        x = int(float(bbox["x"]) * frame_width)
        y = int(float(bbox["y"]) * frame_height)
        width = int(float(bbox["width"]) * frame_width)
        height = int(float(bbox["height"]) * frame_height)
        x = max(0, min(frame_width - 1, x))
        y = max(0, min(frame_height - 1, y))
        width = max(1, min(frame_width - x, width))
        height = max(1, min(frame_height - y, height))
        output.append(Candidate((x, y, width, height), category, confidence, label))
    return output[:3]


def _find_species(db, result: dict[str, Any]) -> Species | None:
    common = str(result.get("common_name", "")).strip().removeprefix("疑似")
    scientific = str(result.get("scientific_name", "")).strip()
    if common:
        item = db.scalar(select(Species).where(Species.common_name == common))
        if item:
            return item
    if scientific:
        return db.scalar(select(Species).where(Species.scientific_name == scientific))
    return None


def _counts_as_species(common_name: str, scientific_name: str) -> bool:
    normalized_scientific = scientific_name.strip().lower()
    if "no cv" in normalized_scientific or normalized_scientific in {"unknown", "animal"}:
        return False
    if normalized_scientific:
        return True
    normalized = common_name.strip().lower()
    if not normalized:
        return False
    unresolved_prefixes = ("低置信度", "待确认", "疑似")
    unresolved_values = {
        "animal",
        "unknown",
        "no cv",
        "no cv result",
        "低置信度候选",
        "低置信度动物候选",
    }
    return not normalized.startswith(unresolved_prefixes) and normalized not in unresolved_values


def _model_evidence_item(
    fusion: dict[str, Any], detections: list[dict[str, Any]]
) -> dict[str, Any]:
    return {
        "kind": "model_evidence",
        "fusion_decision": fusion.get("decision"),
        "fusion_status": fusion.get("fusion_status"),
        "fusion_reason": fusion.get("fusion_reason"),
        "speciesnet_evidence": fusion.get("speciesnet_evidence"),
        "bioclip_evidence": fusion.get("bioclip_evidence"),
        "active_learning_evidence": fusion.get("active_learning_evidence"),
        "local_prototype_evidence": fusion.get("local_prototype_evidence"),
        "bioclip_top_k": fusion.get("bioclip_top_k") or [],
        "bioclip_similarity": fusion.get("bioclip_similarity"),
        "bioclip_top1_margin": fusion.get("bioclip_top1_margin"),
        "prototype_image_count": fusion.get("prototype_image_count"),
        "model_warnings": fusion.get("warnings") or [],
        "detections": detections,
    }


def _evidence_items(raw_items: Any) -> list[Any]:
    items: list[Any] = []
    for item in raw_items or []:
        items.append(item if isinstance(item, dict) else str(item))
    return items[:10]


def _hex_to_bgr(hex_color: str) -> tuple[int, int, int]:
    value = hex_color.lstrip("#")
    if len(value) != 6:
        return 0, 255, 120
    red, green, blue = int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)
    return blue, green, red


def _upsert_variant(db, media_id: int, kind: str, path: Path, codec: str = "h264") -> MediaVariant:
    item = db.scalar(
        select(MediaVariant).where(MediaVariant.media_id == media_id, MediaVariant.kind == kind)
    )
    if item:
        item.stored_path = str(path)
        item.codec = codec
        return item
    item = MediaVariant(media_id=media_id, kind=kind, stored_path=str(path), codec=codec)
    db.add(item)
    db.flush()
    return item


def _bbox_at(keyframes: list[TrackKeyframe], timestamp_ms: int) -> dict[str, float] | None:
    if (
        not keyframes
        or timestamp_ms < keyframes[0].timestamp_ms
        or timestamp_ms > keyframes[-1].timestamp_ms
    ):
        return None
    previous = keyframes[0]
    for current in keyframes[1:]:
        if timestamp_ms <= current.timestamp_ms:
            span = max(1, current.timestamp_ms - previous.timestamp_ms)
            ratio = (timestamp_ms - previous.timestamp_ms) / span
            return {
                key: float(previous.bbox.get(key, 0.0))
                + (float(current.bbox.get(key, 0.0)) - float(previous.bbox.get(key, 0.0))) * ratio
                for key in ("x", "y", "width", "height")
            }
        previous = current
    return {key: float(previous.bbox.get(key, 0.0)) for key in ("x", "y", "width", "height")}


def _render_annotated_video(db, job: AnalysisJob, playback_path: Path) -> str | None:
    cap = cv2.VideoCapture(str(playback_path))
    if not cap.isOpened():
        return None
    fps = cap.get(cv2.CAP_PROP_FPS) or 24.0
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 960)
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 540)
    temporary = settings.annotated_dir / f"job_{job.id}_annotated_raw.avi"
    output = settings.annotated_dir / f"job_{job.id}_annotated.mp4"
    writer = cv2.VideoWriter(str(temporary), cv2.VideoWriter_fourcc(*"MJPG"), fps, (width, height))
    tracks = db.scalars(select(VideoTrack).where(VideoTrack.job_id == job.id)).all()
    track_frames = {
        track.id: list(
            db.scalars(
                select(TrackKeyframe)
                .where(TrackKeyframe.video_track_id == track.id)
                .order_by(TrackKeyframe.timestamp_ms)
            ).all()
        )
        for track in tracks
    }
    frame_index = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        timestamp_ms = int(frame_index / fps * 1000)
        for track in tracks:
            bbox = _bbox_at(track_frames.get(track.id, []), timestamp_ms)
            if not bbox:
                continue
            x = int(bbox["x"] * width)
            y = int(bbox["y"] * height)
            w = int(bbox["width"] * width)
            h = int(bbox["height"] * height)
            color = _hex_to_bgr(track.color)
            cv2.rectangle(frame, (x, y), (x + w, y + h), color, 3)
            label = f"{track.label} #{track.track_id} {track.confidence:.0%}"
            cv2.rectangle(frame, (x, max(0, y - 28)), (min(width, x + 350), y), color, -1)
            cv2.putText(
                frame,
                label,
                (x + 5, max(18, y - 7)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                (8, 20, 15),
                2,
                cv2.LINE_AA,
            )
        writer.write(frame)
        frame_index += 1
    cap.release()
    writer.release()
    if not temporary.exists():
        return None
    try:
        transcode_silent_video(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)
    _upsert_variant(db, job.media_id, "annotated", output)
    return f"/media/annotated/{output.name}" if output.exists() else None


async def process_job(job_id: int) -> None:
    db = SessionLocal()
    try:
        job = db.get(AnalysisJob, job_id)
        if not job:
            return
        if job.status == JobStatus.CANCELLED.value:
            return
        job.status = JobStatus.PREPROCESSING.value
        job.progress = 2
        db.commit()

        original_path = Path(job.media.stored_path)
        playback_path = settings.playback_dir / f"media_{job.media_id}_playback.mp4"
        if not playback_path.exists():
            probe = transcode_browser_video(original_path, playback_path)
        else:
            from backend.services.video_transcode import probe_video

            probe = probe_video(playback_path)
        _upsert_variant(db, job.media_id, "playback", playback_path)
        job.media.duration_seconds = probe.duration_seconds
        job.status = JobStatus.EXTRACTING_FRAMES.value
        job.progress = 8
        db.commit()

        cap = cv2.VideoCapture(str(playback_path))
        if not cap.isOpened():
            raise RuntimeError("转码后的视频仍无法读取")
        fps = cap.get(cv2.CAP_PROP_FPS) or probe.fps or 25.0
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        duration = frame_count / fps if frame_count else probe.duration_seconds
        sample_every = max(1, int(fps / max(settings.video_sample_fps, 0.2)))
        subtractor = cv2.createBackgroundSubtractorMOG2(
            history=200, varThreshold=40, detectShadows=True
        )
        frame_index = 0
        tracker = SimpleIoUTracker()
        ai_calls = 0
        max_ai_calls = max(0, int(getattr(settings, "video_ai_max_calls", 1) or 0))
        seen_hashes: set[str] = set()
        category_counts: dict[str, int] = {}
        species_counts: dict[str, int] = {}
        fire_peak = 0.0
        track_rows: dict[int, VideoTrack] = {}
        saved_keyframes: set[tuple[int, int]] = set()
        local_species_used = 0
        local_behavior_used = 0
        speciesnet_used = 0
        speciesnet_cache: dict[str, dict[str, Any] | None] = {}
        speciesnet_warnings: set[str] = set()
        bioclip_used = 0
        bioclip_cache: dict[str, dict[str, Any] | None] = {}
        bioclip_warnings: set[str] = set()
        ai_correction_used = 0
        ai_correction_warnings: set[str] = set()

        while True:
            db.refresh(job)
            if job.status == JobStatus.CANCELLED.value:
                db.commit()
                return
            ok, frame = cap.read()
            if not ok:
                break
            if frame_index % sample_every != 0:
                frame_index += 1
                continue
            timestamp_ms = int(frame_index / fps * 1000)
            job.status = JobStatus.DETECTING.value
            frame_height, frame_width = frame.shape[:2]
            candidates: list[Candidate] = []
            detector_regions = local_detector.detect(frame) if local_detector.available else []
            for region in detector_regions:
                if region.category in {"person", "vehicle"} and "people" not in job.enabled_targets:
                    continue
                if region.category in {"fire", "smoke"} and "fire" not in job.enabled_targets:
                    continue
                if region.category == "plant" and "plants" not in job.enabled_targets:
                    continue
                if (
                    region.category not in {"person", "vehicle", "fire", "smoke", "plant"}
                    and "animals" not in job.enabled_targets
                ):
                    continue
                candidates.append(
                    Candidate(region.bbox, region.category, region.confidence, region.coarse_label)
                )

            # Fallback candidates keep the project usable before a detector weight is installed.
            if not detector_regions:
                if "plants" in job.enabled_targets and "animals" not in job.enabled_targets:
                    candidates.extend(_plant_candidates(frame))
                if "animals" in job.enabled_targets or "people" in job.enabled_targets:
                    candidates.extend(_motion_candidates(frame, subtractor))
                if (
                    not candidates
                    and speciesnet_client.enabled
                    and ("animals" in job.enabled_targets or "people" in job.enabled_targets)
                ):
                    full_frame_bytes = _crop_jpeg(frame, (0, 0, frame_width, frame_height))
                    (
                        speciesnet_payload,
                        speciesnet_error,
                    ) = await speciesnet_client.safe_predict_image_bytes(
                        full_frame_bytes,
                        filename=f"job_{job.id}_{timestamp_ms}_full_frame.jpg",
                        mime_type="image/jpeg",
                        top_k=5,
                    )
                    if speciesnet_error:
                        speciesnet_warnings.add(speciesnet_error)
                    else:
                        payload_result = (
                            speciesnet_payload.get("result") if speciesnet_payload else None
                        )
                        candidates.extend(
                            _speciesnet_detection_candidates(
                                payload_result if isinstance(payload_result, dict) else None,
                                frame_width,
                                frame_height,
                                job.enabled_targets,
                            )
                        )

            for candidate in candidates:
                job.status = JobStatus.CLASSIFYING.value
                x, y, width, height = candidate.bbox
                result: dict[str, Any] | None = None
                x2, y2 = min(frame_width, x + width), min(frame_height, y + height)
                crop_bgr = frame[max(0, y) : y2, max(0, x) : x2]
                crop_bytes = _crop_jpeg(frame, candidate.bbox)
                crop_hash = hashlib.sha1(crop_bytes).hexdigest()[:12] if crop_bytes else ""
                ai_image_bytes = _context_crop_jpeg(frame, candidate.bbox) or crop_bytes
                ai_image_hash = (
                    hashlib.sha1(ai_image_bytes).hexdigest()[:12] if ai_image_bytes else crop_hash
                )

                biological_categories = {
                    "unknown",
                    "mammal",
                    "bird",
                    "reptile",
                    "amphibian",
                    "fish",
                    "insect",
                    "arachnid",
                    "mollusk",
                    "crustacean",
                    "invertebrate",
                    "plant",
                    "angiosperm",
                    "gymnosperm",
                    "fern",
                    "moss",
                    "algae",
                    "fungus",
                    "lichen",
                }
                speciesnet_result: dict[str, Any] | None = None
                if (
                    speciesnet_client.enabled
                    and candidate.category in biological_categories
                    and crop_bytes
                ):
                    if crop_hash in speciesnet_cache:
                        speciesnet_result = speciesnet_cache[crop_hash]
                    else:
                        (
                            speciesnet_payload,
                            speciesnet_error,
                        ) = await speciesnet_client.safe_predict_image_bytes(
                            crop_bytes,
                            filename=f"job_{job.id}_{timestamp_ms}_{crop_hash}.jpg",
                            mime_type="image/jpeg",
                            top_k=5,
                        )
                        if speciesnet_error:
                            speciesnet_warnings.add(speciesnet_error)
                            speciesnet_cache[crop_hash] = None
                        else:
                            payload_result = (
                                speciesnet_payload.get("result") if speciesnet_payload else None
                            )
                            speciesnet_result = (
                                payload_result if isinstance(payload_result, dict) else None
                            )
                            speciesnet_cache[crop_hash] = speciesnet_result
                            if speciesnet_result:
                                speciesnet_used += 1

                local_species = (
                    local_models.species.predict(crop_bgr, top_k=5)
                    if candidate.category in biological_categories
                    else None
                )
                # A trained local 10k-class model is the primary species classifier when available.
                # It returns Top-5 candidates and can reject unknown/low-confidence inputs.
                if local_species and not local_species.is_unknown:
                    result = {
                        "common_name": local_species.common_name or local_species.scientific_name,
                        "scientific_name": local_species.scientific_name,
                        "category": local_species.category,
                        "confidence": local_species.confidence,
                        "alternatives": local_species.alternatives,
                        "taxonomy": local_species.taxonomy,
                        "evidence": ["本地一万类 ONNX 物种模型"],
                        "explanation": (
                            "本地细粒度物种模型完成初步识别，"
                            "低置信度结果会保持为候选而非强制定种。"
                        ),
                        "model_source": "onnx",
                    }
                    local_species_used += 1
                elif local_species:
                    result = {
                        "common_name": "低置信度植物候选"
                        if candidate.category == "plant"
                        else "低置信度候选",
                        "scientific_name": "",
                        "category": candidate.category,
                        "confidence": max(candidate.score, local_species.confidence),
                        "alternatives": local_species.alternatives,
                        "taxonomy": local_species.taxonomy,
                        "evidence": ["本地模型判定为开放集未知或置信度不足"],
                        "explanation": "模型未达到可靠定种阈值，保留 Top-5 候选供人工复核。",
                        "model_source": "onnx-unknown",
                    }

                # ARK is used as a bounded visual verifier when the local model is absent/unknown.
                if (
                    ark_ai.vision_enabled
                    and (not result or result.get("model_source") == "onnx-unknown")
                    and ai_image_bytes
                    and ai_image_hash not in seen_hashes
                    and ai_calls < max_ai_calls
                ):
                    seen_hashes.add(ai_image_hash)
                    ark_result = await ark_ai.classify_image(
                        ai_image_bytes,
                        hint=(
                            f"video frame target={candidate.category}. "
                            "Return the most specific visible species or concrete Chinese animal/plant name; "
                            "do not use pending/unconfirmed placeholders."
                        ),
                    )
                    ai_calls += 1
                    if ark_result:
                        if result and result.get("alternatives"):
                            ark_result["alternatives"] = (
                                list(ark_result.get("alternatives") or [])
                                + list(result["alternatives"])
                            )[:5]
                        ark_result["model_source"] = "ark+onnx-candidates" if result else "ark"
                        result = ark_result

                if not result:
                    coarse_names = {
                        "person": "人员",
                        "vehicle": "车辆",
                        "fire": "疑似火焰",
                        "smoke": "疑似烟雾",
                        "plant": "低置信度植物候选",
                    }
                    result = {
                        "common_name": coarse_names.get(
                            candidate.category, candidate.coarse_label or "低置信度候选"
                        ),
                        "scientific_name": "",
                        "category": candidate.category,
                        "confidence": candidate.score,
                        "alternatives": [],
                        "model_source": "local-detector" if local_detector.available else "opencv",
                            "evidence": [f"粗检测类别：{candidate.coarse_label}"]
                        if candidate.coarse_label
                        else [],
                    }

                bioclip_result: dict[str, Any] | None = None
                if bioclip_classifier.enabled and candidate.category in ANIMAL_VIDEO_CATEGORIES:
                    if crop_hash and crop_hash in bioclip_cache:
                        bioclip_result = bioclip_cache[crop_hash]
                    else:
                        bioclip_image = (
                            crop_bgr if crop_bgr is not None and crop_bgr.size else frame
                        )
                        bioclip_result, bioclip_error = bioclip_classifier.safe_predict(
                            bioclip_image,
                            category=candidate.category,
                            top_k=settings.bioclip_top_k,
                        )
                        if bioclip_error:
                            bioclip_warnings.add(bioclip_error)
                            if crop_hash:
                                bioclip_cache[crop_hash] = None
                        else:
                            if crop_hash:
                                bioclip_cache[crop_hash] = bioclip_result
                            if bioclip_result:
                                bioclip_used += 1

                fusion = fuse_species_results(
                    speciesnet_result=speciesnet_result,
                    existing_result=bioclip_result or result,
                    original_category=candidate.category,
                    min_score=settings.speciesnet_min_score,
                    strong_score=settings.speciesnet_strong_score,
                )
                fused = fusion.get("result") if isinstance(fusion.get("result"), dict) else None
                if fused:
                    ai_override = _prefer_ai_video_result(
                        ai_result=result,
                        bioclip_result=bioclip_result,
                        fused_result=fused,
                    )
                    if ai_override:
                        fused = ai_override
                        ai_correction_used += 1
                    fused = _downgrade_unreliable_video_species(
                        fused=fused,
                        fusion=fusion,
                        speciesnet_result=speciesnet_result,
                        candidate_category=candidate.category,
                    )
                    skip_ai_correction = bool(fused.pop("_skip_ai_correction", False))
                    if (
                        not skip_ai_correction
                        and settings.ai_correction_enabled
                        and ai_calls < max_ai_calls
                        and ai_image_hash not in seen_hashes
                        and needs_ai_correction(
                            result=fused,
                            fusion=fusion,
                            category=str(fused.get("category") or candidate.category),
                            min_confidence=settings.ai_correction_min_confidence,
                            statuses=settings.ai_correction_status_set,
                        )
                    ):
                        if ark_ai.vision_enabled and (ai_image_bytes or crop_bytes):
                            seen_hashes.add(ai_image_hash)
                            ai_corrected = await ark_ai.classify_image(
                                ai_image_bytes or crop_bytes,
                                hint=(
                                    correction_hint(
                                        category=candidate.category,
                                        result=fused,
                                        fusion=fusion,
                                    )
                                    + " Return the best concrete Chinese result; avoid pending/unconfirmed placeholders."
                                ),
                            )
                            if ai_corrected:
                                fused = merge_ai_correction(
                                    local_result=fused,
                                    ai_result=ai_corrected,
                                    min_accept_confidence=settings.ai_correction_min_confidence,
                                )
                                if fused.get("ai_correction_status") == "accepted" and fused.get(
                                    "scientific_name"
                                ):
                                    learning_result = learn_labeled_image(
                                        crop_bgr
                                        if crop_bgr is not None and crop_bgr.size
                                        else frame,
                                        scientific_name=str(fused.get("scientific_name") or ""),
                                        common_name=str(fused.get("common_name") or ""),
                                        category=str(fused.get("category") or candidate.category),
                                        label_source="ai-correction",
                                        label_confidence=float(
                                            ai_corrected.get("confidence") or 0.0
                                        ),
                                        notes="accepted AI correction during video recognition",
                                    )
                                    fused["evidence"] = list(fused.get("evidence") or []) + [
                                        {"kind": "active_learning_update", **learning_result}
                                    ]
                                ai_correction_used += 1
                            else:
                                ai_correction_warnings.add(
                                    "AI correction was requested but returned no usable result."
                                )
                            ai_calls += 1
                        elif ark_ai.vision_enabled:
                            ai_correction_warnings.add(
                                "AI correction skipped because no crop bytes were available."
                            )
                        else:
                            ai_correction_warnings.add(
                                "AI correction skipped because ARK_API_KEY is not configured."
                            )
                    result = localize_prediction(db, fused)
                    result["evidence"] = list(result.get("evidence") or []) + [
                        _model_evidence_item(
                            fusion,
                            speciesnet_result.get("detections") if speciesnet_result else [],
                        )
                    ]
                    if fusion.get("warnings"):
                        speciesnet_warnings.update(str(item) for item in fusion["warnings"])

                if _skip_unverified_weak_video_species(
                    result=result,
                    bioclip_result=bioclip_result,
                    speciesnet_result=speciesnet_result,
                ):
                    bioclip_warnings.add(
                        "Weak BioCLIP video-frame species candidate skipped because neither AI review nor SpeciesNet supplied reliable animal evidence."
                    )
                    continue

                category = normalize_category(result.get("category") or candidate.category or "unknown")
                if category == "unknown" and candidate.category == "plant":
                    category = "plant"
                confidence = float(result.get("confidence") or candidate.score)
                common_name = str(result.get("common_name") or "低置信度候选")
                scientific_name = str(result.get("scientific_name") or "")
                alternatives = list(result.get("alternatives") or [])[:5]
                behavior = str(result.get("behavior") or "")[:120]
                animal_categories = {
                    "mammal",
                    "bird",
                    "reptile",
                    "amphibian",
                    "fish",
                    "insect",
                    "arachnid",
                    "mollusk",
                    "crustacean",
                    "invertebrate",
                }
                if category in animal_categories and local_models.behavior.available:
                    local_behavior = local_models.behavior.predict(crop_bgr, top_k=3)
                    if (
                        local_behavior
                        and not local_behavior.is_unknown
                        and local_behavior.confidence >= 0.60
                    ):
                        behavior = (
                            local_behavior.common_name
                            or local_behavior.scientific_name
                            or local_behavior.label
                        )
                        local_behavior_used += 1
                species = _find_species(db, result)
                if species:
                    common_name = species.common_name
                    scientific_name = species.scientific_name
                    category = normalize_category(species.category)
                if (
                    confidence < 0.55
                    and not scientific_name
                    and not common_name.startswith(("疑似", "待确认", "低置信度"))
                ):
                    common_name = f"疑似{common_name}"
                track_id = tracker.assign(candidate.bbox, timestamp_ms)
                normalized = _normalized_bbox(x, y, width, height, frame_width, frame_height)
                detection = Detection(
                    job_id=job.id,
                    species_id=species.id if species else None,
                    track_id=track_id,
                    category=category,
                    label=common_name,
                    scientific_name=scientific_name,
                    confidence=max(0.01, min(confidence, 0.99)),
                    timestamp_ms=timestamp_ms,
                    bbox=normalized,
                    color=CATEGORY_COLORS.get(category, CATEGORY_COLORS["unknown"]),
                    source=str(
                        result.get("model_source")
                        or ("ark+opencv" if ark_ai.vision_enabled else "opencv")
                    ),
                    behavior=behavior,
                    phenomenon=str(result.get("phenomenon") or "")[:120],
                    explanation=str(result.get("explanation") or "")[:3000],
                    evidence=_evidence_items(result.get("evidence")),
                    alternatives=alternatives,
                )
                db.add(detection)

                track_row = track_rows.get(track_id)
                if not track_row:
                    track_row = VideoTrack(
                        job_id=job.id,
                        track_id=track_id,
                        species_id=species.id if species else None,
                        category=category,
                        label=common_name,
                        scientific_name=scientific_name,
                        confidence=detection.confidence,
                        color=detection.color,
                        start_ms=timestamp_ms,
                        end_ms=timestamp_ms,
                        source=detection.source,
                        alternatives=alternatives,
                    )
                    db.add(track_row)
                    db.flush()
                    track_rows[track_id] = track_row
                else:
                    track_row.end_ms = timestamp_ms
                    if detection.confidence >= track_row.confidence:
                        track_row.species_id = detection.species_id
                        track_row.category = category
                        track_row.label = common_name
                        track_row.scientific_name = scientific_name
                        track_row.confidence = detection.confidence
                        track_row.color = detection.color
                        track_row.alternatives = alternatives
                keyframe_key = (track_row.id, timestamp_ms)
                if keyframe_key not in saved_keyframes:
                    db.add(
                        TrackKeyframe(
                            video_track_id=track_row.id,
                            timestamp_ms=timestamp_ms,
                            bbox=normalized,
                            confidence=detection.confidence,
                        )
                    )
                    saved_keyframes.add(keyframe_key)
                category_counts[category] = category_counts.get(category, 0) + 1
                if _counts_as_species(common_name, scientific_name):
                    species_counts[common_name] = species_counts.get(common_name, 0) + 1

            if "fire" in job.enabled_targets:
                job.status = JobStatus.RISK_ANALYSIS.value
                score = _fire_score(frame)
                fire_peak = max(fire_peak, score)
                if score > 0.7:
                    exists = db.scalar(
                        select(RiskEvent).where(
                            RiskEvent.job_id == job.id,
                            RiskEvent.event_type == "fire_candidate",
                        )
                    )
                    if not exists:
                        db.add(
                            RiskEvent(
                                job_id=job.id,
                                event_type="fire_candidate",
                                title="疑似火焰或高温亮区",
                                severity="high",
                                description="颜色与亮度初筛发现疑似火焰区域，需要人工复核。",
                                timestamp_ms=timestamp_ms,
                                confidence=score,
                                evidence={"method": "HSV 颜色与面积初筛"},
                                ai_advice="优先查看事件前后连续画面，确认后再联系专业人员。",
                            )
                        )
            if frame_count:
                job.progress = min(91, 10 + math.floor(frame_index / frame_count * 81))
            if frame_index % max(1, sample_every * 5) == 0:
                db.commit()
            frame_index += 1
            await asyncio.sleep(0)

        cap.release()
        db.commit()
        detections_count = db.query(Detection).filter(Detection.job_id == job.id).count()
        job.status = JobStatus.RENDERING.value
        job.progress = 94
        db.commit()
        annotated_url = _render_annotated_video(db, job, playback_path)
        job.summary = {
            "detections": detections_count,
            "tracks": len(track_rows),
            "categories": category_counts,
            "species": species_counts,
            "duration_seconds": round(duration, 2),
            "sample_fps": settings.video_sample_fps,
            "playback_url": f"/media/playback/{playback_path.name}",
            "annotated_url": annotated_url,
            "video_codec": "h264",
            "vision_mode": _vision_mode_label(),
            "speciesnet_predictions": speciesnet_used,
            "speciesnet_enabled": speciesnet_client.enabled,
            "speciesnet_warnings": sorted(speciesnet_warnings),
            "bioclip_predictions": bioclip_used,
            "bioclip_enabled": bioclip_classifier.enabled,
            "bioclip_warnings": sorted(bioclip_warnings),
            "ai_correction_predictions": ai_correction_used,
            "ai_correction_enabled": settings.ai_correction_enabled,
            "ai_correction_min_confidence": settings.ai_correction_min_confidence,
            "ai_correction_warnings": sorted(ai_correction_warnings),
            "local_species_predictions": local_species_used,
            "local_behavior_predictions": local_behavior_used,
            "fire_peak": round(fire_peak, 3),
            "limitations": [
                "个人图鉴只在用户确认识别后写入，不会因为模型预测自动点亮。",
                "植物只对明显前景或近景区域进行候选检测。",
                "低置信度结果必须人工复核。",
                "未安装一万类自训练模型时，不宣称覆盖全部物种。",
            ],
        }
        job.progress = 100
        job.status = JobStatus.COMPLETED.value
        job.completed_at = now_utc()
        db.commit()
    except VideoTranscodeError as exc:
        job = db.get(AnalysisJob, job_id)
        if job:
            job.status = JobStatus.FAILED.value
            job.error_message = str(exc)
            db.commit()
    except Exception as exc:  # noqa: BLE001
        job = db.get(AnalysisJob, job_id)
        if job:
            job.status = JobStatus.FAILED.value
            job.error_message = str(exc)
            db.commit()
    finally:
        db.close()
