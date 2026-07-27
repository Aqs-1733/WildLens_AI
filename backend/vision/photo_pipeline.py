from __future__ import annotations

import asyncio
import math
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from backend.core.config import PROJECT_ROOT, get_settings
from backend.models import (
    AnalysisJob,
    Detection,
    MediaFile,
    RiskEvent,
    Species,
    User,
    now_utc,
)
from backend.services.ai import ark_ai
from backend.services.species_profile import ensure_species_profile
from backend.services.taxon_names import localize_prediction, normalize_category
from backend.vision.ai_correction import correction_hint, merge_ai_correction, needs_ai_correction
from backend.vision.object_detector import LocalObjectDetector
from backend.vision.onnx_models import LocalNatureModels
from backend.vision.bioclip_classifier import BIOLOGICAL_CATEGORIES, bioclip_classifier
from backend.vision.learning_feedback import learn_labeled_image
from backend.vision.pipeline import CATEGORY_COLORS
from backend.vision.species_fusion import fuse_species_results, speciesnet_bbox_to_dict
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


def _clamp(value: Any, low: float = 0.0, high: float = 1.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return low
    if not math.isfinite(number):
        return low
    return max(low, min(high, number))


def _normalize_bbox(raw: Any) -> dict[str, float]:
    if not isinstance(raw, dict):
        return {"x": 0.08, "y": 0.08, "width": 0.84, "height": 0.84}
    x = _clamp(raw.get("x", 0.08))
    y = _clamp(raw.get("y", 0.08))
    width = _clamp(raw.get("width", 0.84), 0.03, 1.0)
    height = _clamp(raw.get("height", 0.84), 0.03, 1.0)
    if x + width > 1:
        width = max(0.03, 1 - x)
    if y + height > 1:
        height = max(0.03, 1 - y)
    return {"x": x, "y": y, "width": width, "height": height}


def _bbox_iou(a: dict[str, Any], b: dict[str, Any]) -> float:
    ax1 = _clamp(a.get("x", 0.0))
    ay1 = _clamp(a.get("y", 0.0))
    ax2 = _clamp(ax1 + _clamp(a.get("width", 0.0)))
    ay2 = _clamp(ay1 + _clamp(a.get("height", 0.0)))
    bx1 = _clamp(b.get("x", 0.0))
    by1 = _clamp(b.get("y", 0.0))
    bx2 = _clamp(bx1 + _clamp(b.get("width", 0.0)))
    by2 = _clamp(by1 + _clamp(b.get("height", 0.0)))
    intersection_width = max(0.0, min(ax2, bx2) - max(ax1, bx1))
    intersection_height = max(0.0, min(ay2, by2) - max(ay1, by1))
    intersection = intersection_width * intersection_height
    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    union = area_a + area_b - intersection
    return intersection / union if union > 0 else 0.0


def _speciesnet_category(result: dict[str, Any]) -> str:
    common_name = str(result.get("common_name") or "").strip().lower()
    if common_name == "human":
        return "person"
    if common_name == "vehicle":
        return "vehicle"
    class_name = str((result.get("taxonomy") or {}).get("class_name") or "").strip().lower()
    return {
        "mammalia": "mammal",
        "aves": "bird",
        "reptilia": "reptile",
        "amphibia": "amphibian",
        "actinopterygii": "fish",
    }.get(class_name, "mammal" if result.get("scientific_name") else "unknown")


def _speciesnet_raw_object(result: dict[str, Any]) -> dict[str, Any]:
    detections = [
        item
        for item in (result.get("detections") or [])
        if isinstance(item, dict) and item.get("bbox")
    ]
    best_detection = max(detections, key=lambda item: float(item.get("conf") or 0.0), default={})
    bbox = speciesnet_bbox_to_dict(best_detection.get("bbox")) or {
        "x": 0.04,
        "y": 0.04,
        "width": 0.92,
        "height": 0.92,
    }
    return {
        "common_name": result.get("common_name") or result.get("scientific_name") or "SpeciesNet animal",
        "scientific_name": result.get("scientific_name") or "",
        "category": _speciesnet_category(result),
        "confidence": float(result.get("score") or 0.0),
        "bbox": bbox,
        "behavior": "",
        "phenomenon": "",
        "explanation": "SpeciesNet animal-specialist branch supplied this candidate.",
        "evidence": ["SpeciesNet classifier/detector candidate"],
        "alternatives": result.get("top_k") or [],
    }


def _bioclip_raw_object(result: dict[str, Any]) -> dict[str, Any]:
    category = str(result.get("category") or "unknown").lower()
    if category not in BIOLOGICAL_CATEGORIES:
        category = "unknown"
    return {
        "common_name": result.get("common_name") or result.get("scientific_name") or "BioCLIP candidate",
        "scientific_name": result.get("scientific_name") or "",
        "category": category,
        "confidence": float(result.get("confidence") or result.get("bioclip_similarity") or 0.0),
        "bbox": {"x": 0.0, "y": 0.0, "width": 1.0, "height": 1.0},
        "behavior": "",
        "phenomenon": "",
        "explanation": result.get("explanation") or "BioCLIP searched the full image against local prototypes.",
        "evidence": result.get("evidence") or ["BioCLIP full-image prototype search"],
        "alternatives": result.get("alternatives") or result.get("bioclip_top_k") or [],
        "taxonomy": result.get("taxonomy") or {},
        "_bioclip_result": result,
    }


def _has_biological_candidate(raw_objects: Any) -> bool:
    return any(
        isinstance(item, dict) and str(item.get("category") or "").lower() in BIOLOGICAL_CATEGORIES
        for item in (raw_objects or [])
    )


def _is_weak_scene_heuristic(item: Any, hint: str = "") -> bool:
    if not isinstance(item, dict):
        return False
    category = str(item.get("category") or "").lower()
    confidence = _clamp(item.get("confidence") or 0.0)
    if category in {"fire", "smoke"}:
        hint_lower = str(hint or "").lower()
        explicit_risk_hint = any(token in hint_lower for token in ("fire", "smoke", "火", "烟", "燃", "烧"))
        return confidence < 0.80 and not explicit_risk_hint
    if category == "unknown" and confidence <= 0.45:
        bbox = item.get("bbox") if isinstance(item.get("bbox"), dict) else {}
        return (
            _clamp(bbox.get("x", 0.0)) <= 0.12
            and _clamp(bbox.get("y", 0.0)) <= 0.12
            and _clamp(bbox.get("width", 1.0)) >= 0.75
            and _clamp(bbox.get("height", 1.0)) >= 0.75
        )
    if category != "phenomenon":
        return False
    if confidence > 0.60:
        return False
    bbox = item.get("bbox") if isinstance(item.get("bbox"), dict) else {}
    return (
        _clamp(bbox.get("x", 0.0)) <= 0.02
        and _clamp(bbox.get("y", 0.0)) <= 0.02
        and _clamp(bbox.get("width", 1.0)) >= 0.95
        and _clamp(bbox.get("height", 1.0)) >= 0.95
    )


def _phenomenon_from_hint(hint: str) -> dict[str, Any] | None:
    text = str(hint or "").lower()
    patterns = [
        (("闪电", "雷电", "雷暴", "lightning", "thunderstorm"), "闪电/雷暴天气", "weather"),
        (("彩虹", "rainbow"), "彩虹", "weather"),
        (("雾", "低能见度", "fog", "mist"), "雾/低能见度", "phenomenon"),
        (("云海", "积雨云", "云", "cloud"), "云层或云系现象", "weather"),
        (("日落", "晚霞", "朝霞", "sunset", "sunrise"), "霞光/日落光照", "phenomenon"),
        (("海浪", "浪", "wave"), "海浪", "phenomenon"),
    ]
    for tokens, label, category in patterns:
        if any(token in text for token in tokens):
            return {
                "common_name": label,
                "scientific_name": "",
                "category": category,
                "confidence": 0.86,
                "bbox": {"x": 0.0, "y": 0.0, "width": 1.0, "height": 1.0},
                "behavior": "",
                "phenomenon": label,
                "explanation": "用户提示词明确指向自然现象，系统按全图自然现象候选保存，避免误归入动物或植物。",
                "evidence": ["用户自然现象提示", "全图场景候选"],
                "alternatives": [],
            }
    return None


def _usable_speciesnet_candidate(result: dict[str, Any] | None) -> bool:
    if not result:
        return False
    score = _clamp(result.get("score") or 0.0)
    return bool(result.get("detections") or result.get("scientific_name") or result.get("common_name")) and (
        score >= settings.speciesnet_min_score or bool(result.get("detections"))
    )


def _should_prefer_full_bioclip(
    crop_result: dict[str, Any] | None,
    full_result: dict[str, Any] | None,
) -> bool:
    if not full_result:
        return False
    if bool(full_result.get("active_learning_applied")):
        return True
    if not crop_result:
        return True
    crop_similarity = _clamp(crop_result.get("bioclip_similarity") or 0.0)
    full_similarity = _clamp(full_result.get("bioclip_similarity") or 0.0)
    crop_weak = bool(crop_result.get("bioclip_is_weak"))
    full_weak = bool(full_result.get("bioclip_is_weak"))
    return (crop_weak and not full_weak) or full_similarity >= crop_similarity + 0.03


def _model_evidence_item(fusion: dict[str, Any], detections: list[dict[str, Any]]) -> dict[str, Any]:
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


def _jpeg_bytes(image: np.ndarray) -> bytes:
    if image is None or image.size == 0:
        return b""
    ok, encoded = cv2.imencode(".jpg", image, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
    return encoded.tobytes() if ok else b""


def _final_model_mode(engines: set[str], fallback: str) -> str:
    if "speciesnet" in engines and "bioclip" in engines:
        return "speciesnet+bioclip"
    if "speciesnet" in engines:
        return "speciesnet"
    if "bioclip" in engines:
        return "bioclip"
    if "ark" in engines:
        return "ark"
    if "onnx" in engines:
        return "onnx+heuristic"
    return fallback or "heuristic"


def _category_allowed(category: str, targets: set[str]) -> bool:
    category = normalize_category(category)
    if category in {"person", "vehicle"}:
        return "people" in targets
    if category in {"phenomenon", "weather", "fire", "smoke"}:
        return "phenomena" in targets or "fire" in targets
    if category in {"plant", "angiosperm", "gymnosperm", "fern", "moss", "algae"}:
        return "plants" in targets
    if category in {"fungus", "lichen"}:
        return "fungi" in targets or "plants" in targets
    if category in BIOLOGICAL_CATEGORIES or category == "unknown":
        return "animals" in targets or "plants" in targets or "fungi" in targets
    return True


def _find_species(db: Session, common_name: str, scientific_name: str) -> Species | None:
    common_name = common_name.strip().removeprefix("疑似").removeprefix("待确认").removeprefix("低置信度")
    scientific_name = scientific_name.strip()
    if common_name:
        item = db.scalar(select(Species).where(Species.common_name == common_name))
        if item:
            return item
        item = db.scalar(
            select(Species).where(
                or_(
                    Species.common_name.contains(common_name),
                    Species.english_name.contains(common_name),
                )
            )
        )
        if item:
            return item
    if scientific_name:
        return db.scalar(select(Species).where(Species.scientific_name == scientific_name))
    return None


def _heuristic_objects(image: np.ndarray) -> tuple[str, str, list[dict[str, Any]], list[str]]:
    """Lightweight offline fallback; it intentionally avoids claiming exact species."""
    height, width = image.shape[:2]
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    objects: list[dict[str, Any]] = []
    warnings = ["当前使用离线启发式模式，具体物种与自然现象需要 AI 或本地训练模型复核。"]

    green_mask = cv2.inRange(hsv, np.array([25, 35, 20]), np.array([100, 255, 255]))
    contours, _ = cv2.findContours(green_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if contours:
        contour = max(contours, key=cv2.contourArea)
        ratio = cv2.contourArea(contour) / max(1, height * width)
        if ratio > 0.06:
            x, y, w, h = cv2.boundingRect(contour)
            objects.append(
                {
                    "common_name": "低置信度植物候选",
                    "scientific_name": "",
                    "category": "plant",
                    "confidence": min(0.68, 0.42 + ratio),
                    "bbox": {"x": x / width, "y": y / height, "width": w / width, "height": h / height},
                    "behavior": "",
                    "phenomenon": "",
                    "explanation": "画面中存在连续绿色植被区域，但离线启发式无法可靠确定具体种类。",
                    "evidence": ["连续绿色区域", "植物形态候选"],
                    "alternatives": [],
                }
            )

    fire_mask = cv2.inRange(hsv, np.array([0, 145, 145]), np.array([24, 255, 255]))
    fire_ratio = float(np.count_nonzero(fire_mask)) / max(1, height * width)
    if fire_ratio > 0.025:
        ys, xs = np.where(fire_mask > 0)
        x1, x2 = int(xs.min()), int(xs.max())
        y1, y2 = int(ys.min()), int(ys.max())
        objects.append(
            {
                "common_name": "疑似火焰色区域",
                "scientific_name": "",
                "category": "fire",
                "confidence": min(0.72, 0.45 + fire_ratio * 4),
                "bbox": {"x": x1 / width, "y": y1 / height, "width": (x2 - x1) / width, "height": (y2 - y1) / height},
                "behavior": "",
                "phenomenon": "疑似火焰",
                "explanation": "检测到高饱和橙红区域，仅作为风险候选，可能是花朵、灯光或日落。",
                "evidence": ["橙红色高饱和区域"],
                "alternatives": [{"name": "暖色物体或光照", "scientific_name": "", "confidence": 0.4}],
            }
        )

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    contrast = float(gray.std())
    brightness = float(gray.mean())
    if contrast < 33 and brightness > 105:
        objects.append(
            {
                "common_name": "疑似雾或低能见度",
                "scientific_name": "",
                "category": "phenomenon",
                "confidence": 0.58,
                "bbox": {"x": 0, "y": 0, "width": 1, "height": 1},
                "behavior": "",
                "phenomenon": "雾/低能见度",
                "explanation": "整幅画面对比度较低且亮度较均匀，可能存在雾、云气或曝光影响。",
                "evidence": ["全局低对比度", "远景细节减少"],
                "alternatives": [{"name": "镜头曝光或薄云", "scientific_name": "", "confidence": 0.35}],
            }
        )

    if not objects:
        objects.append(
            {
                "common_name": "低置信度自然候选",
                "scientific_name": "",
                "category": "unknown",
                "confidence": 0.35,
                "bbox": {"x": 0.08, "y": 0.08, "width": 0.84, "height": 0.84},
                "behavior": "",
                "phenomenon": "",
                "explanation": "未检测到可由离线规则可靠描述的目标，请启用 ARK 视觉或下载本地模型。",
                "evidence": [],
                "alternatives": [],
            }
        )
    return "自然观察照片", "other", objects[:8], warnings


async def analyze_photo(
    db: Session,
    user: User,
    media: MediaFile,
    image_bytes: bytes,
    mime_type: str,
    hint: str,
    enabled_targets: list[str] | None = None,
) -> tuple[AnalysisJob, list[Detection], str, str, list[str], str]:
    image = cv2.imdecode(np.frombuffer(image_bytes, np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("无法解码图片，请使用清晰的 JPG、PNG 或 WebP 文件")

    target_set = set(enabled_targets or ["animals", "plants", "phenomena", "behaviors"])
    job = AnalysisJob(
        owner_id=user.id,
        media_id=media.id,
        status="processing",
        progress=20,
        mode="photo",
        enabled_targets=[item for item in ["animals", "plants", "fungi", "phenomena", "behaviors"] if item in target_set],
        summary={},
    )
    db.add(job)
    db.flush()

    speciesnet_task = None
    if speciesnet_client.enabled and "animals" in target_set:
        speciesnet_task = asyncio.create_task(
            speciesnet_client.safe_predict_image_bytes(
                image_bytes,
                filename=media.filename,
                mime_type=mime_type,
                top_k=5,
            )
        )

    local_first_available = speciesnet_client.enabled or bioclip_classifier.enabled
    ai_result = None if local_first_available else await ark_ai.analyze_nature_image(image_bytes, mime_type, hint)
    model_mode = "ark" if ai_result else "heuristic"
    used_engines: set[str] = {"ark"} if ai_result else {"heuristic"}
    if ai_result:
        scene_summary = str(ai_result.get("scene_summary") or "自然观察照片")
        scene_type = str(ai_result.get("scene_type") or "other")
        raw_objects = ai_result.get("objects") if isinstance(ai_result.get("objects"), list) else []
        warnings = [str(item) for item in (ai_result.get("warnings") or [])][:8]
    else:
        scene_summary, scene_type, raw_objects, warnings = _heuristic_objects(image)

    hint_phenomenon = _phenomenon_from_hint(hint) if "phenomena" in target_set else None
    if hint_phenomenon:
        raw_objects = [hint_phenomenon]
        scene_summary = str(hint_phenomenon["common_name"])
        scene_type = "phenomenon"
        model_mode = _final_model_mode(used_engines, model_mode)

    speciesnet_result: dict[str, Any] | None = None
    if speciesnet_task and not hint_phenomenon:
        speciesnet_payload, speciesnet_error = await speciesnet_task
        if speciesnet_error:
            warnings.append(f"SpeciesNet unavailable; original recognition flow continued: {speciesnet_error}")
        elif speciesnet_payload:
            result = speciesnet_payload.get("result")
            if isinstance(result, dict):
                speciesnet_result = result
                used_engines.add("speciesnet")
                if _usable_speciesnet_candidate(speciesnet_result):
                    raw_objects = [_speciesnet_raw_object(speciesnet_result), *raw_objects]
                    model_mode = _final_model_mode(used_engines, model_mode)

    if (
        bioclip_classifier.enabled
        and not hint_phenomenon
        and not _has_biological_candidate(raw_objects)
        and bool(target_set & {"animals", "plants", "fungi"})
    ):
        whole_bioclip_result, bioclip_error = bioclip_classifier.safe_predict(
            image,
            category="unknown",
            top_k=settings.bioclip_top_k,
        )
        if bioclip_error:
            warnings.append(f"BioCLIP unavailable; full-image recognition skipped: {bioclip_error}")
        elif whole_bioclip_result:
            whole_bioclip_result = localize_prediction(db, whole_bioclip_result)
            similarity = _clamp(whole_bioclip_result.get("bioclip_similarity") or 0.0)
            active_learning_applied = bool(whole_bioclip_result.get("active_learning_applied"))
            if active_learning_applied or similarity >= float(settings.bioclip_min_similarity):
                raw_objects = [_bioclip_raw_object(whole_bioclip_result), *raw_objects]
                used_engines.add("bioclip")
                model_mode = _final_model_mode(used_engines, model_mode)
            else:
                warnings.append(
                    "BioCLIP full-image search was below the local similarity threshold; "
                    "the weak species candidate was not shown."
                )

    if _has_biological_candidate(raw_objects):
        raw_objects = [item for item in raw_objects if not _is_weak_scene_heuristic(item, hint)]
    raw_objects = [
        item
        for item in raw_objects
        if not isinstance(item, dict) or _category_allowed(str(item.get("category") or "unknown"), target_set)
    ]

    # If ARK did not provide usable boxes, use a local YOLO/MegaDetector-compatible
    # model and let the fine-grained 10k classifier identify every crop.
    if not raw_objects and local_detector.available:
        height, width = image.shape[:2]
        raw_objects = []
        for region in local_detector.detect(image):
            x, y, box_width, box_height = region.bbox
            raw_objects.append(
                {
                    "common_name": {
                        "person": "人员",
                        "vehicle": "车辆",
                        "fire": "疑似火焰",
                        "smoke": "疑似烟雾",
                        "plant": "低置信度植物候选",
                    }.get(region.category, "低置信度自然候选"),
                    "scientific_name": "",
                    "category": region.category,
                    "confidence": region.confidence,
                    "bbox": {
                        "x": x / width,
                        "y": y / height,
                        "width": box_width / width,
                        "height": box_height / height,
                    },
                    "behavior": "",
                    "phenomenon": "",
                    "explanation": "本地检测器定位目标，具体物种由细粒度分类模型复核。",
                    "evidence": [f"粗检测类别：{region.coarse_label}"],
                    "alternatives": [],
                }
            )
        if raw_objects:
            raw_objects = [
                item
                for item in raw_objects
                if not isinstance(item, dict) or _category_allowed(str(item.get("category") or "unknown"), target_set)
            ]
        if raw_objects:
            model_mode = "detector"
            warnings.append("当前目标框来自本地检测器，具体物种结果仍需结合分类置信度。")

    if not raw_objects:
        scene_summary, scene_type, raw_objects, fallback_warnings = _heuristic_objects(image)
        warnings.extend(fallback_warnings)
        raw_objects = [
            item
            for item in raw_objects
            if not isinstance(item, dict) or _category_allowed(str(item.get("category") or "unknown"), target_set)
        ]
        model_mode = "heuristic"

    if "phenomena" in target_set and local_models.phenomena.available:
        prediction = local_models.phenomena.predict(image)
        has_phenomenon = any(
            isinstance(item, dict) and str(item.get("category", "")).lower() in {"phenomenon", "fire", "smoke"}
            for item in raw_objects
        )
        if prediction and prediction.confidence >= 0.60 and not has_phenomenon:
            raw_objects.append(
                {
                    "common_name": prediction.label,
                    "scientific_name": "",
                    "category": "phenomenon",
                    "confidence": prediction.confidence,
                    "bbox": {"x": 0, "y": 0, "width": 1, "height": 1},
                    "behavior": "",
                    "phenomenon": prediction.label,
                    "explanation": "本地自然现象 ONNX 模型对整幅场景进行多类别判断。",
                    "evidence": ["本地训练模型输出"],
                    "alternatives": prediction.alternatives,
                }
            )
            used_engines.add("onnx")
            model_mode = "ark+onnx" if model_mode == "ark" else "onnx+heuristic"

    if not raw_objects:
        selected_labels = {
            "animals": "动物",
            "plants": "植物",
            "fungi": "真菌",
            "phenomena": "自然现象",
            "behaviors": "动物行为",
        }
        warnings.append(
            "未识别到符合当前选择范围的目标："
            + "、".join(selected_labels[item] for item in ["animals", "plants", "fungi", "phenomena", "behaviors"] if item in target_set)
        )

    detections: list[Detection] = []
    counts: dict[str, int] = {}
    ai_correction_used = 0
    image_url = f"/media/uploads/{Path(media.stored_path).name}"
    image_height, image_width = image.shape[:2]
    full_bioclip_result: dict[str, Any] | None = None
    full_bioclip_error: str | None = None
    full_bioclip_attempted = False
    for index, raw in enumerate(raw_objects[:8], start=1):
        if not isinstance(raw, dict):
            continue
        raw = dict(raw)
        precomputed_bioclip_result = raw.pop("_bioclip_result", None)
        bbox = _normalize_bbox(raw.get("bbox"))
        x1 = max(0, int(bbox["x"] * image_width))
        y1 = max(0, int(bbox["y"] * image_height))
        x2 = min(image_width, int((bbox["x"] + bbox["width"]) * image_width))
        y2 = min(image_height, int((bbox["y"] + bbox["height"]) * image_height))
        crop = image[y1:y2, x1:x2]
        category = normalize_category(raw.get("category") or "unknown")
        if category not in CATEGORY_COLORS:
            category = "unknown"
        color = CATEGORY_COLORS.get(category, CATEGORY_COLORS["unknown"])
        confidence = _clamp(raw.get("confidence", 0.0))
        common_name = str(raw.get("common_name") or "低置信度自然候选").strip()
        scientific_name = str(raw.get("scientific_name") or "").strip()
        alternatives = list(raw.get("alternatives") or [])[:5]
        behavior = str(raw.get("behavior") or "")[:120]

        if category in {"mammal", "bird", "reptile", "amphibian", "fish", "insect", "arachnid", "mollusk", "crustacean", "invertebrate", "plant", "angiosperm", "gymnosperm", "fern", "moss", "algae", "fungus", "lichen", "unknown"}:
            local_species = local_models.species.predict(crop)
            if local_species and local_species.confidence >= 0.55:
                matched = _find_species(db, "", local_species.label)
                if matched:
                    common_name = matched.common_name
                    scientific_name = matched.scientific_name
                    category = normalize_category(matched.category)
                elif not scientific_name:
                    scientific_name = local_species.label
                confidence = max(confidence, local_species.confidence)
                alternatives = (local_species.alternatives + alternatives)[:5]
                used_engines.add("onnx")
                model_mode = "ark+onnx" if model_mode == "ark" else "onnx+heuristic"

        if "behaviors" in target_set and category in {"mammal", "bird", "reptile", "amphibian", "fish", "insect", "arachnid", "mollusk", "crustacean", "invertebrate"}:
            local_behavior = local_models.behavior.predict(crop)
            if local_behavior and local_behavior.confidence >= 0.60:
                behavior = local_behavior.label
                used_engines.add("onnx")
                model_mode = "ark+onnx" if model_mode == "ark" else "onnx+heuristic"

        if (
            confidence < 0.55
            and not scientific_name
            and not common_name.startswith(("疑似", "待确认", "低置信度"))
        ):
            common_name = f"疑似{common_name}"
        existing_result = {
            "common_name": common_name,
            "scientific_name": scientific_name,
            "category": category,
            "confidence": confidence,
            "alternatives": alternatives,
            "taxonomy": raw.get("taxonomy") or {},
            "model_source": model_mode,
            "evidence": raw.get("evidence") or [],
        }
        bioclip_result: dict[str, Any] | None = (
            precomputed_bioclip_result if isinstance(precomputed_bioclip_result, dict) else None
        )
        if bioclip_result:
            bioclip_result = localize_prediction(db, bioclip_result)
            used_engines.add("bioclip")
        elif category in BIOLOGICAL_CATEGORIES and bioclip_classifier.enabled:
            bioclip_image = crop if crop is not None and crop.size else image
            bioclip_result, bioclip_error = bioclip_classifier.safe_predict(
                bioclip_image,
                category=category,
                top_k=settings.bioclip_top_k,
            )
            crop_area_ratio = float(bbox["width"] * bbox["height"])
            crop_similarity = _clamp((bioclip_result or {}).get("bioclip_similarity") or 0.0)
            needs_full_fallback = (
                bool(getattr(settings, "bioclip_full_image_fallback", True))
                and crop_area_ratio < 0.92
                and (
                    not bool(getattr(settings, "bioclip_full_image_fallback_weak_only", True))
                    or not bioclip_result
                    or bool(bioclip_result.get("bioclip_is_weak"))
                    or crop_similarity < float(settings.bioclip_min_similarity) + 0.03
                )
            )
            if needs_full_fallback:
                if not full_bioclip_attempted:
                    full_bioclip_attempted = True
                    full_bioclip_result, full_bioclip_error = bioclip_classifier.safe_predict(
                        image,
                        category=category,
                        top_k=settings.bioclip_top_k,
                    )
                    if full_bioclip_result:
                        full_bioclip_result = localize_prediction(db, full_bioclip_result)
                if _should_prefer_full_bioclip(bioclip_result, full_bioclip_result):
                    bioclip_result = full_bioclip_result
                    bioclip_error = None
                elif full_bioclip_error and not bioclip_error:
                    warnings.append(
                        f"BioCLIP full-image fallback unavailable; crop result kept: {full_bioclip_error}"
                    )
            if bioclip_error:
                warnings.append(f"BioCLIP unavailable; local fusion continued: {bioclip_error}")
            elif bioclip_result:
                bioclip_result = localize_prediction(db, bioclip_result)
                used_engines.add("bioclip")
        fusion_input = bioclip_result or existing_result
        fusion = fuse_species_results(
            speciesnet_result=speciesnet_result,
            existing_result=fusion_input,
            original_category=category,
            min_score=settings.speciesnet_min_score,
            strong_score=settings.speciesnet_strong_score,
        )
        fused = fusion.get("result") if isinstance(fusion.get("result"), dict) else None
        if fused:
            fused = localize_prediction(db, fused)
            skip_ai_correction = bool(fused.pop("_skip_ai_correction", False))
            speciesnet_evidence = fusion.get("speciesnet_evidence") or {}
            bioclip_evidence = fusion.get("bioclip_evidence") or {}
            if (
                not skip_ai_correction
                and isinstance(speciesnet_evidence, dict)
                and isinstance(bioclip_evidence, dict)
                and speciesnet_evidence.get("rank") == "object"
                and str(bioclip_evidence.get("scientific_name") or "").strip().casefold()
                == str(fused.get("scientific_name") or "").strip().casefold()
                and _clamp(fused.get("confidence")) >= settings.ai_correction_min_confidence
            ):
                skip_ai_correction = True
            if (
                settings.ai_correction_enabled
                and not skip_ai_correction
                and needs_ai_correction(
                result=fused,
                fusion=fusion,
                category=str(fused.get("category") or category),
                min_confidence=settings.ai_correction_min_confidence,
                statuses=settings.ai_correction_status_set,
                )
            ):
                if ark_ai.vision_enabled:
                    correction_bytes = _jpeg_bytes(crop) or image_bytes
                    ai_corrected = await ark_ai.classify_image(
                        correction_bytes,
                        hint=correction_hint(category=category, result=fused, fusion=fusion),
                    )
                    if ai_corrected:
                        fused = merge_ai_correction(
                            local_result=fused,
                            ai_result=ai_corrected,
                            min_accept_confidence=settings.ai_correction_min_confidence,
                        )
                        if (
                            fused.get("ai_correction_status") == "accepted"
                            and fused.get("scientific_name")
                        ):
                            learning_result = learn_labeled_image(
                                crop if crop is not None and crop.size else image,
                                scientific_name=str(fused.get("scientific_name") or ""),
                                common_name=str(fused.get("common_name") or ""),
                                category=str(fused.get("category") or category),
                                label_source="ai-correction",
                                label_confidence=float(ai_corrected.get("confidence") or 0.0),
                                notes="accepted AI correction during photo recognition",
                            )
                            fused["evidence"] = list(fused.get("evidence") or []) + [
                                {"kind": "active_learning_update", **learning_result}
                            ]
                        used_engines.add("ark")
                        ai_correction_used += 1
                    else:
                        warnings.append("AI correction was requested but returned no usable result.")
                else:
                    warnings.append("AI correction skipped because ARK_IMAGE_MODEL is not configured.")
            common_name = str(fused.get("common_name") or common_name).strip()
            scientific_name = str(fused.get("scientific_name") or scientific_name).strip()
            category = normalize_category(fused.get("category") or category)
            if category not in CATEGORY_COLORS:
                category = "unknown"
            confidence = _clamp(fused.get("confidence", confidence))
            alternatives = list(fused.get("alternatives") or alternatives)[:5]
            raw["explanation"] = str(fused.get("explanation") or raw.get("explanation") or "")
            raw["evidence"] = list(raw.get("evidence") or []) + [
                _model_evidence_item(
                    fusion,
                    speciesnet_result.get("detections") if speciesnet_result else [],
                )
            ]
            if fused.get("model_source"):
                model_mode = str(fused["model_source"])
            if fusion.get("warnings"):
                warnings.extend(str(item) for item in fusion["warnings"])
            color = CATEGORY_COLORS.get(category, CATEGORY_COLORS["unknown"])

        if scientific_name and category in BIOLOGICAL_CATEGORIES:
            duplicate = next(
                (
                    item
                    for item in detections
                    if item.scientific_name == scientific_name
                    and item.category in BIOLOGICAL_CATEGORIES
                    and (
                        _bbox_iou(item.bbox or {}, bbox) >= 0.45
                        or (
                            float(item.confidence or 0.0) >= 0.80
                            and confidence <= float(item.confidence or 0.0) - 0.08
                            and bbox["width"] * bbox["height"] <= 0.30
                        )
                    )
                ),
                None,
            )
            if duplicate:
                continue

        species = _find_species(db, common_name, scientific_name)
        if scientific_name and category in BIOLOGICAL_CATEGORIES:
            enriched_species = await ensure_species_profile(
                db,
                scientific_name=scientific_name,
                category=category,
                common_hint=common_name,
            )
            if enriched_species:
                species = enriched_species
                common_name = enriched_species.common_name
                scientific_name = enriched_species.scientific_name
                category = normalize_category(enriched_species.category or category)
                color = CATEGORY_COLORS.get(category, CATEGORY_COLORS["unknown"])
                if not raw.get("explanation") or "BioCLIP" in str(raw.get("explanation")):
                    raw["explanation"] = (
                        f"本地 BioCLIP 将图像向量与 400721 个物种视觉原型检索后，"
                        f"最相近的候选为{common_name}（{scientific_name}）。"
                        "请结合置信度、Top K 候选和拍摄角度复核。"
                    )
        detection = Detection(
            job_id=job.id,
            species_id=species.id if species else None,
            track_id=index,
            category=category,
            label=species.common_name if species and confidence >= 0.55 else common_name,
            scientific_name=species.scientific_name if species else scientific_name,
            confidence=confidence,
            timestamp_ms=0,
            bbox=bbox,
            color=color,
            source=model_mode,
            review_status="confirmed",
            behavior=behavior,
            phenomenon=str(raw.get("phenomenon") or "")[:120],
            explanation=str(raw.get("explanation") or "")[:3000],
            evidence=_evidence_items(raw.get("evidence")),
            alternatives=alternatives,
        )
        db.add(detection)
        db.flush()
        detections.append(detection)
        counts[detection.category] = counts.get(detection.category, 0) + 1


        if detection.category in {"fire", "smoke"} and detection.confidence >= 0.55:
            db.add(
                RiskEvent(
                    job_id=job.id,
                    event_type=detection.category,
                    title=f"{detection.label}风险候选",
                    severity="high" if detection.confidence >= 0.8 else "medium",
                    status="pending",
                    description=detection.explanation,
                    confidence=detection.confidence,
                    evidence={"detection_id": detection.id, "bbox": detection.bbox, "image_url": image_url},
                    ai_advice="请结合现场情况和人工复核，不要仅凭单张图片下结论。",
                )
            )

    job.status = "completed"
    job.progress = 100
    job.completed_at = now_utc()
    model_mode = _final_model_mode(used_engines, model_mode)
    if model_mode not in {"heuristic", "onnx+heuristic"}:
        warnings = [
            item
            for item in warnings
            if "启发式" not in str(item) and "heuristic" not in str(item).lower()
        ]
    job.summary = {
        "scene_summary": scene_summary,
        "scene_type": scene_type,
        "objects": len(detections),
        "categories": counts,
        "model_mode": model_mode,
        "warnings": warnings,
        "ai_correction_predictions": ai_correction_used,
        "ai_correction_enabled": settings.ai_correction_enabled,
        "ai_correction_min_confidence": settings.ai_correction_min_confidence,
    }
    db.commit()
    for item in detections:
        db.refresh(item)
    return job, detections, scene_summary, scene_type, warnings, model_mode
