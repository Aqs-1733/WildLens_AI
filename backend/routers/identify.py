from __future__ import annotations

import mimetypes
import re
import uuid
from pathlib import Path

import cv2
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.core.config import get_settings
from backend.core.database import get_db
from backend.core.pagination import add_pagination_headers, page_window, paginate_scalars
from backend.deps import get_current_user
from backend.models import (
    AnalysisJob,
    Detection,
    DiscoveryRecord,
    MediaFile,
    MediaVariant,
    ObservationLocation,
    RecognitionFeedback,
    Species,
    Taxon,
    User,
    UserCollection,
    now_utc,
)
from backend.schemas import (
    DiscoveryOut,
    ManualObservationRequest,
    PhotoIdentifyResponse,
    PhotoObjectOut,
    RecognitionFeedbackRequest,
    ReidentifyRequest,
    SaveDiscoveryRequest,
    SpeciesGuideOut,
)
from backend.services.species_guides import guide_for_detection
from backend.services.species_profile import localize_detection
from backend.services.taxon_names import localize_candidate, normalize_category, resolve_chinese_name
from backend.vision.learning_feedback import learn_from_detection_correction
from backend.vision.photo_pipeline import analyze_photo

router = APIRouter(prefix="/api/identify", tags=["identify"])
settings = get_settings()

ALLOWED_MIME = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}
ANIMAL_CATEGORIES = {
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
PLANT_CATEGORIES = {
    "plant",
    "angiosperm",
    "gymnosperm",
    "fern",
    "moss",
    "algae",
    "fungus",
    "lichen",
}
PHENOMENON_CATEGORIES = {"phenomenon", "fire", "smoke", "weather"}
DISPLAY_LATIN_PAREN_RE = re.compile(r"[（(]\s*[A-Z][A-Za-z.'-]*(?:\s+[a-z][A-Za-z.'-]*){1,4}\s*[）)]")
DISPLAY_CJK_RE = re.compile(r"[\u3400-\u9fff]")
DISPLAY_GARBLED_RE = re.compile(r"�|\?{3,}|Ã|å|ç|¤")
DISPLAY_UNCERTAIN_RE = re.compile(r"低置信度|待确认|疑似|候选|unknown|unidentified", re.IGNORECASE)
DISPLAY_EXCLUDED_CATEGORIES = {"person", "vehicle", "human"}

RARITY_BY_CATEGORY = {
    "mammal": 3,
    "bird": 2,
    "reptile": 3,
    "amphibian": 3,
    "fish": 2,
    "insect": 1,
    "arachnid": 1,
    "plant": 1,
    "angiosperm": 1,
    "gymnosperm": 3,
    "fern": 2,
    "fungus": 2,
    "lichen": 2,
}

CITY_COORDINATES: dict[str, tuple[float, float]] = {
    "北京": (39.9042, 116.4074),
    "北京市": (39.9042, 116.4074),
    "天津": (39.3434, 117.3616),
    "天津市": (39.3434, 117.3616),
    "上海": (31.2304, 121.4737),
    "上海市": (31.2304, 121.4737),
    "重庆": (29.5630, 106.5516),
    "重庆市": (29.5630, 106.5516),
    "广州": (23.1291, 113.2644),
    "深圳": (22.5431, 114.0579),
    "杭州": (30.2741, 120.1551),
    "南京": (32.0603, 118.7969),
    "成都": (30.5728, 104.0668),
    "武汉": (30.5928, 114.3055),
    "西安": (34.3416, 108.9398),
    "昆明": (25.0389, 102.7183),
    "哈尔滨": (45.8038, 126.5349),
    "长春": (43.8171, 125.3235),
    "沈阳": (41.8057, 123.4315),
    "济南": (36.6512, 117.1201),
    "青岛": (36.0671, 120.3826),
    "郑州": (34.7466, 113.6254),
    "长沙": (28.2282, 112.9388),
    "福州": (26.0745, 119.2965),
    "厦门": (24.4798, 118.0894),
    "南宁": (22.8170, 108.3669),
    "贵阳": (26.6470, 106.6302),
    "兰州": (36.0611, 103.8343),
    "乌鲁木齐": (43.8256, 87.6168),
    "拉萨": (29.6520, 91.1721),
    "海口": (20.0440, 110.1999),
}


def _targets_from_scopes(scopes: str) -> list[str]:
    raw = {item.strip().lower() for item in (scopes or "").split(",") if item.strip()}
    if not raw:
        return ["animals", "plants", "phenomena", "behaviors"]
    aliases = {
        "animal": "animals",
        "animals": "animals",
        "mammal": "animals",
        "bird": "animals",
        "plant": "plants",
        "plants": "plants",
        "fungus": "fungi",
        "fungi": "fungi",
        "insect": "animals",
        "phenomenon": "phenomena",
        "phenomena": "phenomena",
        "weather": "phenomena",
        "behavior": "behaviors",
        "behaviors": "behaviors",
    }
    targets = {aliases.get(item, item) for item in raw}
    if "behaviors" in targets:
        targets.add("animals")
    return [item for item in ["animals", "plants", "fungi", "phenomena", "behaviors"] if item in targets]


def _location_payload(
    *,
    latitude: float | None = None,
    longitude: float | None = None,
    location_accuracy: float | None = None,
    province: str = "",
    city: str = "",
    district: str = "",
    address: str = "",
    geohash: str = "",
    location_source: str = "manual",
    privacy_level: str = "precise",
) -> dict:
    address = (address or "").strip()
    province = (province or "").strip()
    city = (city or "").strip()
    district = (district or "").strip()
    if (latitude is None or longitude is None) and address:
        haystack = f"{province}{city}{district}{address}"
        for name, coords in CITY_COORDINATES.items():
            if name in haystack:
                latitude, longitude = coords
                if not city:
                    city = name
                location_source = "manual"
                break
    if address and not district:
        district = address[:80]
    return {
        "latitude": latitude,
        "longitude": longitude,
        "location_accuracy": location_accuracy,
        "province": province,
        "city": city,
        "district": district,
        "geohash": geohash,
        "location_source": location_source if location_source in {"gps", "exif", "manual", "unknown"} else "manual",
        "privacy_level": privacy_level if privacy_level in {"precise", "obscured", "private"} else "precise",
    }


def _model_metadata(evidence: list) -> dict:
    for item in evidence or []:
        if isinstance(item, dict) and item.get("kind") == "model_evidence":
            return item
    return {}


def _object_out(db: Session, item: Detection) -> PhotoObjectOut:
    discovery_id = db.scalar(
        select(DiscoveryRecord.id).where(DiscoveryRecord.detection_id == item.id)
    )
    metadata = _model_metadata(item.evidence or [])
    label = resolve_chinese_name(
        db, item.scientific_name, item.label, item.category
    )
    alternatives = [
        localize_candidate(db, alt) if isinstance(alt, dict) else alt
        for alt in (item.alternatives or [])
    ]
    bioclip_top_k = [
        localize_candidate(db, alt) if isinstance(alt, dict) else alt
        for alt in (metadata.get("bioclip_top_k") or [])
    ]
    return PhotoObjectOut(
        id=item.id,
        species_id=item.species_id,
        discovery_id=discovery_id,
        track_id=item.track_id,
        category=item.category,
        label=label,
        common_name_zh=label,
        scientific_name=item.scientific_name,
        confidence=item.confidence,
        bbox=item.bbox or {},
        color=item.color,
        behavior=item.behavior,
        phenomenon=item.phenomenon,
        explanation=item.explanation,
        evidence=item.evidence or [],
        alternatives=alternatives,
        speciesnet_evidence=metadata.get("speciesnet_evidence"),
        bioclip_evidence=metadata.get("bioclip_evidence"),
        active_learning_evidence=metadata.get("active_learning_evidence"),
        local_prototype_evidence=metadata.get("local_prototype_evidence"),
        fusion_decision=metadata.get("fusion_decision"),
        fusion_status=metadata.get("fusion_status"),
        fusion_reason=metadata.get("fusion_reason"),
        bioclip_top_k=bioclip_top_k,
        bioclip_similarity=metadata.get("bioclip_similarity"),
        bioclip_top1_margin=metadata.get("bioclip_top1_margin"),
        prototype_image_count=metadata.get("prototype_image_count"),
        model_warnings=metadata.get("model_warnings") or [],
        detections=metadata.get("detections") or [],
    )


def _discovery_image_url(db: Session, detection: Detection) -> str:
    job = db.get(AnalysisJob, detection.job_id)
    if not job:
        return ""
    media = job.media
    source = Path(media.stored_path)
    if media.media_type == "image":
        return f"/media/uploads/{source.name}"
    playback = db.scalar(
        select(MediaVariant).where(
            MediaVariant.media_id == media.id,
            MediaVariant.kind == "playback",
        )
    )
    video_path = Path(playback.stored_path) if playback else source
    output = settings.result_dir / f"observation_detection_{detection.id}_{detection.timestamp_ms}.jpg"
    if not output.exists() and video_path.exists():
        capture = cv2.VideoCapture(str(video_path))
        if capture.isOpened():
            capture.set(cv2.CAP_PROP_POS_MSEC, max(0, detection.timestamp_ms))
            ok, frame = capture.read()
            capture.release()
            if ok:
                cv2.imwrite(str(output), frame, [int(cv2.IMWRITE_JPEG_QUALITY), 92])
    return f"/media/results/{output.name}" if output.exists() else ""


def _is_placeholder_image_url(value: str | None) -> bool:
    text = str(value or "").strip().lower()
    return not text or ("/showcase_" in text and text.endswith(".png"))


def _touch_species_image(species: Species | None, image_url: str) -> None:
    if species and image_url and _is_placeholder_image_url(species.image_url):
        species.image_url = image_url


def _record_type(detection: Detection) -> str:
    if detection.category in PHENOMENON_CATEGORIES or detection.phenomenon:
        return "phenomenon"
    if detection.behavior:
        return "behavior"
    return "species"


def _clean_record_title(db: Session, record: DiscoveryRecord) -> str:
    title = record.phenomenon or record.behavior or resolve_chinese_name(
        db, record.scientific_name, record.title, record.category
    )
    title = DISPLAY_LATIN_PAREN_RE.sub("", str(title or "")).strip()
    return " ".join(title.split())


def _is_clean_observation(record: DiscoveryRecord, title: str) -> bool:
    category = normalize_category(record.category)
    if category in DISPLAY_EXCLUDED_CATEGORIES:
        return False
    if not title or not DISPLAY_CJK_RE.search(title):
        return False
    if DISPLAY_GARBLED_RE.search(title) or DISPLAY_UNCERTAIN_RE.search(title):
        return False
    return True


def _analytics_group(category: str) -> str | None:
    normalized = normalize_category(category)
    if normalized in ANIMAL_CATEGORIES:
        return "animal"
    if normalized in PLANT_CATEGORIES:
        return "plant"
    if normalized in PHENOMENON_CATEGORIES:
        return "nature"
    return None


def _rarity_for(category: str, scientific_name: str, title: str) -> int:
    category = normalize_category(category)
    text = f"{scientific_name} {title}"
    if any(token in text for token in ("tigris", "altaica", "豹", "虎", "象", "雕")):
        return 5
    if any(token in text for token in ("Panthera", "Elephas", "Ursus", "Ailuropoda")):
        return 5
    return RARITY_BY_CATEGORY.get(category, 2)


def _ensure_species_for_detection(db: Session, detection: Detection) -> Species | None:
    if detection.species_id:
        return db.get(Species, detection.species_id)
    detection.category = normalize_category(detection.category)
    if detection.category not in (ANIMAL_CATEGORIES | PLANT_CATEGORIES):
        return None
    scientific = str(detection.scientific_name or "").strip()
    if not scientific:
        return None
    species = db.scalar(select(Species).where(Species.scientific_name == scientific))
    if species:
        detection.species_id = species.id
        detection.label = resolve_chinese_name(db, scientific, detection.label, detection.category)
        return species
    title = resolve_chinese_name(db, scientific, detection.label, detection.category)
    duplicate = db.scalar(select(Species).where(Species.common_name == title))
    if duplicate and duplicate.scientific_name != scientific:
        title = f"{title}（{scientific}）"[:100]
    taxon = db.scalar(select(Taxon).where(Taxon.scientific_name == scientific))
    species = Species(
        common_name=title,
        scientific_name=scientific,
        english_name=taxon.common_name_en if taxon else "",
        kingdom=taxon.kingdom if taxon and taxon.kingdom else ("Plantae" if detection.category in PLANT_CATEGORIES else "Animalia"),
        category=detection.category,
        protection_level=(taxon.conservation_status if taxon and taxon.conservation_status else "未列入本地保护名录"),
        rarity=_rarity_for(detection.category, scientific, title),
        color=detection.color,
        habitat="已由真实识别记录创建；打开中文科普后会生成并缓存详细栖息环境。",
        distribution="分布信息会结合物种资料与用户观察地点逐步完善。",
        traits=detection.explanation or "由本地识别结果创建的物种条目，建议结合多角度照片复核。",
        diet="打开中文科普后会生成并缓存食性资料。",
        activity="打开中文科普后会生成并缓存活动规律。",
        ecology_value="打开中文科普后会生成并缓存生态价值。",
        threats="打开中文科普后会生成并缓存主要威胁。",
        conservation="不公开珍稀物种精确位置，避免干扰。",
        taxonomy={},
        facts=[],
        source_notes=["由识境本地识别结果自动创建"],
    )
    db.add(species)
    db.flush()
    detection.species_id = species.id
    return species


def _touch_collection(db: Session, user: User, species: Species | None, *, stars: int, increment: bool) -> None:
    if not species:
        return
    collection = db.scalar(
        select(UserCollection).where(
            UserCollection.user_id == user.id,
            UserCollection.species_id == species.id,
        )
    )
    if collection:
        if increment:
            collection.discovered_count += 1
        collection.last_discovered_at = now_utc()
        collection.stars_earned = max(collection.stars_earned, stars)
        collection.knowledge_progress = max(collection.knowledge_progress, 20)
    else:
        db.add(
            UserCollection(
                user_id=user.id,
                species_id=species.id,
                discovered_count=1 if increment else 0,
                knowledge_progress=20,
                stars_earned=stars,
            )
        )
        user.stars += stars
    user.points += 5 if increment else 1
    user.level = max(1, 1 + user.points // 300)


def _ensure_location(db: Session, record: DiscoveryRecord, location: dict, species: Species | None = None) -> None:
    has_location = any(
        value is not None and value != ""
        for value in (
            location.get("latitude"),
            location.get("longitude"),
            location.get("province"),
            location.get("city"),
            location.get("district"),
        )
    )
    if not has_location:
        return
    privacy = str(location.get("privacy_level") or "precise")
    if species and species.rarity >= 4 and privacy == "precise":
        privacy = "obscured"
    existing = db.scalar(
        select(ObservationLocation).where(ObservationLocation.discovery_id == record.id)
    )
    if not existing:
        existing = ObservationLocation(discovery_id=record.id)
        db.add(existing)
    existing.latitude = location.get("latitude")
    existing.longitude = location.get("longitude")
    existing.location_accuracy = location.get("location_accuracy")
    existing.province = str(location.get("province") or "")[:80]
    existing.city = str(location.get("city") or "")[:80]
    existing.district = str(location.get("district") or "")[:80]
    existing.geohash = str(location.get("geohash") or "")[:24]
    existing.location_source = str(location.get("location_source") or "manual")[:30]
    existing.privacy_level = privacy[:30]


def _ensure_discovery_record(
    db: Session,
    *,
    user: User,
    detection: Detection,
    note: str = "",
    location: dict | None = None,
) -> DiscoveryRecord:
    existing = db.scalar(
        select(DiscoveryRecord).where(
            DiscoveryRecord.user_id == user.id,
            DiscoveryRecord.detection_id == detection.id,
        )
    )
    species = _ensure_species_for_detection(db, detection)
    record_type = _record_type(detection)
    title = detection.phenomenon or detection.behavior or resolve_chinese_name(
        db, detection.scientific_name, detection.label, detection.category
    )
    stars = max(1, species.rarity if species else 1)
    if existing:
        existing.species_id = detection.species_id
        existing.record_type = record_type
        existing.title = title
        existing.scientific_name = detection.scientific_name
        existing.category = detection.category
        existing.confidence = detection.confidence
        existing.behavior = detection.behavior
        existing.phenomenon = detection.phenomenon
        if note:
            existing.note = note
        if not existing.image_url:
            existing.image_url = _discovery_image_url(db, detection)
        _touch_species_image(species, existing.image_url)
        if location:
            _ensure_location(db, existing, location, species)
        _touch_collection(db, user, species, stars=stars, increment=False)
        return existing
    record = DiscoveryRecord(
        user_id=user.id,
        job_id=detection.job_id,
        detection_id=detection.id,
        species_id=detection.species_id,
        record_type=record_type,
        title=title,
        scientific_name=detection.scientific_name,
        category=detection.category,
        image_url=_discovery_image_url(db, detection),
        confidence=detection.confidence,
        behavior=detection.behavior,
        phenomenon=detection.phenomenon,
        note=note or detection.explanation,
        stars_earned=stars,
    )
    db.add(record)
    db.flush()
    _touch_species_image(species, record.image_url)
    if location:
        _ensure_location(db, record, location, species)
    _touch_collection(db, user, species, stars=stars, increment=True)
    return record


@router.post("/photo", response_model=PhotoIdentifyResponse)
async def identify_photo(
    file: UploadFile = File(...),
    hint: str = Form(default=""),
    scopes: str = Form(default="animals,plants,fungi,phenomena,behaviors"),
    latitude: float | None = Form(default=None),
    longitude: float | None = Form(default=None),
    location_accuracy: float | None = Form(default=None),
    province: str = Form(default=""),
    city: str = Form(default=""),
    district: str = Form(default=""),
    address: str = Form(default=""),
    geohash: str = Form(default=""),
    location_source: str = Form(default="unknown"),
    privacy_level: str = Form(default="precise"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> PhotoIdentifyResponse:
    content_type = (
        file.content_type or mimetypes.guess_type(file.filename or "")[0] or ""
    ).lower()
    if content_type not in ALLOWED_MIME:
        raise HTTPException(status_code=400, detail="仅支持 JPG、PNG、WebP 图片")
    payload = await file.read(settings.max_photo_mb * 1024 * 1024 + 1)
    if not payload:
        raise HTTPException(status_code=400, detail="图片内容为空")
    if len(payload) > settings.max_photo_mb * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"图片大小不能超过 {settings.max_photo_mb}MB")

    suffix = ALLOWED_MIME[content_type]
    filename = f"photo_{user.id}_{uuid.uuid4().hex}{suffix}"
    destination = settings.upload_dir / filename
    destination.write_bytes(payload)
    media = MediaFile(
        owner_id=user.id,
        filename=file.filename or filename,
        stored_path=str(destination),
        media_type="image",
        size_bytes=len(payload),
    )
    db.add(media)
    db.flush()
    try:
        job, detections, summary, scene_type, warnings, mode = await analyze_photo(
            db,
            user,
            media,
            payload,
            content_type,
            hint,
            enabled_targets=_targets_from_scopes(scopes),
        )
    except ValueError as exc:
        destination.unlink(missing_ok=True)
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        destination.unlink(missing_ok=True)
        db.rollback()
        raise HTTPException(status_code=500, detail="图片识别失败，请稍后重试") from exc

    location = _location_payload(
        latitude=latitude,
        longitude=longitude,
        location_accuracy=location_accuracy,
        province=province,
        city=city,
        district=district,
        address=address,
        geohash=geohash,
        location_source=location_source,
        privacy_level=privacy_level,
    )
    for item in detections:
        _ensure_discovery_record(db, user=user, detection=item, note=hint, location=location)
    db.commit()

    return PhotoIdentifyResponse(
        job_id=job.id,
        media_id=media.id,
        image_url=f"/media/uploads/{filename}",
        summary=summary,
        scene_type=scene_type,
        objects=[_object_out(db, item) for item in detections],
        warnings=warnings,
        model_mode=mode,
        ai_correction_predictions=int((job.summary or {}).get("ai_correction_predictions") or 0),
        ai_correction_enabled=bool((job.summary or {}).get("ai_correction_enabled") or False),
        ai_correction_min_confidence=(job.summary or {}).get("ai_correction_min_confidence"),
    )


@router.post("/jobs/{job_id}/reidentify", response_model=PhotoIdentifyResponse)
async def reidentify_photo(
    job_id: int,
    payload: ReidentifyRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> PhotoIdentifyResponse:
    job = db.get(AnalysisJob, job_id)
    if not job or (user.role == "public" and job.owner_id != user.id):
        raise HTTPException(status_code=404, detail="识别任务不存在")
    media = job.media
    if media.media_type != "image":
        raise HTTPException(status_code=400, detail="当前只支持重新识别图片任务")
    source = Path(media.stored_path)
    if not source.exists():
        raise HTTPException(status_code=404, detail="原始图片不存在")
    content_type = (mimetypes.guess_type(media.filename or source.name)[0] or "image/jpeg").lower()
    if content_type not in ALLOWED_MIME:
        content_type = "image/jpeg"
    image_bytes = source.read_bytes()
    new_job, detections, summary, scene_type, warnings, mode = await analyze_photo(
        db,
        user,
        media,
        image_bytes,
        content_type,
        payload.hint,
        enabled_targets=_targets_from_scopes(payload.scopes),
    )
    location = _location_payload(address=payload.address or payload.hint)
    for item in detections:
        _ensure_discovery_record(db, user=user, detection=item, note=payload.hint, location=location)
    db.commit()
    return PhotoIdentifyResponse(
        job_id=new_job.id,
        media_id=media.id,
        image_url=f"/media/uploads/{source.name}",
        summary=summary,
        scene_type=scene_type,
        objects=[_object_out(db, item) for item in detections],
        warnings=warnings,
        model_mode=mode,
        ai_correction_predictions=int((new_job.summary or {}).get("ai_correction_predictions") or 0),
        ai_correction_enabled=bool((new_job.summary or {}).get("ai_correction_enabled") or False),
        ai_correction_min_confidence=(new_job.summary or {}).get("ai_correction_min_confidence"),
    )


@router.get("/detections/{detection_id}/guide", response_model=SpeciesGuideOut)
async def detection_guide(
    detection_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    detection = db.get(Detection, detection_id)
    if not detection:
        raise HTTPException(status_code=404, detail="识别结果不存在")
    job = db.get(AnalysisJob, detection.job_id)
    if not job or (user.role == "public" and job.owner_id != user.id):
        raise HTTPException(status_code=403, detail="无权访问该识别结果")
    detection.category = normalize_category(detection.category)
    species = await localize_detection(db, detection)
    if species:
        _touch_collection(db, user, species, stars=max(1, min(5, species.rarity)), increment=False)
        db.commit()
    guide = await guide_for_detection(db, detection)
    species = db.get(Species, detection.species_id) if detection.species_id else species
    if species:
        guide_name = str(guide.get("common_name_zh") or "").strip()
        if guide_name:
            duplicate = db.scalar(select(Species).where(Species.common_name == guide_name))
            if not duplicate or duplicate.id == species.id or duplicate.scientific_name == species.scientific_name:
                species.common_name = guide_name
        species.category = normalize_category(species.category)
        species.traits = guide.get("appearance") or species.traits
        species.habitat = guide.get("habitat") or species.habitat
        species.activity = guide.get("behavior") or species.activity
        species.ecology_value = guide.get("summary") or species.ecology_value
        species.conservation = guide.get("observation_tips") or species.conservation
        species.threats = guide.get("caution") or species.threats
        if not species.facts:
            species.facts = [
                guide.get("similar_species") or "",
                guide.get("observation_tips") or "",
            ]
        db.commit()
    return guide


@router.post("/observations", response_model=DiscoveryOut)
def save_observation(
    payload: SaveDiscoveryRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> DiscoveryRecord:
    detection = db.get(Detection, payload.detection_id)
    if not detection:
        raise HTTPException(status_code=404, detail="识别结果不存在")
    job = db.get(AnalysisJob, detection.job_id)
    if not job or (user.role == "public" and job.owner_id != user.id):
        raise HTTPException(status_code=403, detail="无权保存该识别结果")
    existing = db.scalar(
        select(DiscoveryRecord).where(
            DiscoveryRecord.user_id == user.id,
            DiscoveryRecord.detection_id == detection.id,
        )
    )
    if existing:
        species = _ensure_species_for_detection(db, detection)
        if not existing.image_url:
            existing.image_url = _discovery_image_url(db, detection)
        _ensure_location(
            db,
            existing,
            _location_payload(
                latitude=payload.latitude,
                longitude=payload.longitude,
                location_accuracy=payload.location_accuracy,
                province=payload.province,
                city=payload.city,
                district=payload.district,
                address=payload.address,
                geohash=payload.geohash,
                location_source=payload.location_source,
                privacy_level=payload.privacy_level,
            ),
            species,
        )
        _touch_species_image(species, existing.image_url)
        if payload.note:
            existing.note = payload.note
        db.commit()
        db.refresh(existing)
        return existing

    species = _ensure_species_for_detection(db, detection)
    record_type = _record_type(detection)
    title = detection.phenomenon or detection.behavior or resolve_chinese_name(
        db, detection.scientific_name, detection.label, detection.category
    )
    stars = max(1, species.rarity if species else 1)
    record = DiscoveryRecord(
        user_id=user.id,
        job_id=detection.job_id,
        detection_id=detection.id,
        species_id=detection.species_id,
        record_type=record_type,
        title=title,
        scientific_name=detection.scientific_name,
        category=detection.category,
        image_url=_discovery_image_url(db, detection),
        confidence=detection.confidence,
        behavior=detection.behavior,
        phenomenon=detection.phenomenon,
        note=payload.note or detection.explanation,
        stars_earned=stars,
    )
    db.add(record)
    db.flush()
    _touch_species_image(species, record.image_url)

    _ensure_location(
        db,
        record,
        _location_payload(
            latitude=payload.latitude,
            longitude=payload.longitude,
            location_accuracy=payload.location_accuracy,
            province=payload.province,
            city=payload.city,
            district=payload.district,
            address=payload.address,
            geohash=payload.geohash,
            location_source=payload.location_source,
            privacy_level=payload.privacy_level,
        ),
        species,
    )

    if species:
        _touch_collection(db, user, species, stars=stars, increment=True)
    else:
        user.points += 2
    db.commit()
    db.refresh(record)
    return record


@router.get("/history", response_model=list[DiscoveryOut])
def history(
    response: Response,
    record_type: str = "",
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=80, ge=1, le=200),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[DiscoveryRecord]:
    stmt = select(DiscoveryRecord).where(DiscoveryRecord.user_id == user.id)
    if record_type:
        stmt = stmt.where(DiscoveryRecord.record_type == record_type)
    records = list(
        paginate_scalars(
            db,
            stmt.order_by(DiscoveryRecord.created_at.desc()),
            response=response,
            page=page,
            limit=limit,
            max_limit=200,
        )
    )
    for record in records:
        record.title = record.phenomenon or record.behavior or resolve_chinese_name(
            db, record.scientific_name, record.title, record.category
        )
    return records


@router.get("/observations/map")
def observation_map(
    response: Response,
    layer: str = "animal",
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=300, ge=1, le=1000),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[dict]:
    category_set = ANIMAL_CATEGORIES
    if layer == "plant":
        category_set = PLANT_CATEGORIES
    elif layer == "phenomenon":
        category_set = PHENOMENON_CATEGORIES
    base = (
        select(DiscoveryRecord, ObservationLocation)
        .join(ObservationLocation, ObservationLocation.discovery_id == DiscoveryRecord.id)
        .where(
            DiscoveryRecord.user_id == user.id,
            DiscoveryRecord.category.in_(category_set),
        )
    )
    safe_page, safe_limit, offset = page_window(page, limit, max_limit=1000)
    total = db.scalar(select(func.count()).select_from(base.order_by(None).subquery())) or 0
    add_pagination_headers(response, total=int(total), page=safe_page, limit=safe_limit)
    rows = db.execute(
        base.order_by(DiscoveryRecord.created_at.desc()).limit(safe_limit).offset(offset)
    ).all()
    payload = []
    for record, location in rows:
        title = _clean_record_title(db, record)
        if not _is_clean_observation(record, title):
            continue
        payload.append(
            {
                "id": record.id,
                "title": title,
                "scientific_name": record.scientific_name,
                "category": normalize_category(record.category),
                "image_url": record.image_url,
                "confidence": record.confidence,
                "description": record.note or "",
                "behavior": record.behavior,
                "phenomenon": record.phenomenon,
                "observed_at": location.observed_at,
                "latitude": location.latitude,
                "longitude": location.longitude,
                "province": location.province,
                "city": location.city,
                "district": location.district,
                "privacy_level": location.privacy_level,
                "is_first": db.scalar(
                    select(func.count(DiscoveryRecord.id)).where(
                        DiscoveryRecord.user_id == user.id,
                        DiscoveryRecord.species_id == record.species_id,
                        DiscoveryRecord.created_at < record.created_at,
                    )
                )
                == 0,
            }
        )
    return payload


@router.get("/observations/summary")
def observation_summary(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[dict]:
    records = db.scalars(
        select(DiscoveryRecord)
        .where(DiscoveryRecord.user_id == user.id)
        .order_by(DiscoveryRecord.created_at)
    ).all()
    grouped: dict[str, dict] = {}
    for record in records:
        title = _clean_record_title(db, record)
        if not _is_clean_observation(record, title):
            continue
        key = (
            f"species:{record.species_id}"
            if record.species_id
            else f"name:{record.scientific_name or title or record.category}".lower()
        )
        item = grouped.get(key)
        if not item:
            item = {
                "species_id": record.species_id,
                "title": title,
                "scientific_name": record.scientific_name,
                "category": record.category,
                "count": 0,
                "first_discovered_at": record.created_at,
                "last_discovered_at": record.created_at,
                "latest_record_id": record.id,
                "latest_image_url": record.image_url,
            }
            grouped[key] = item
        item["count"] += 1
        if record.created_at >= item["last_discovered_at"]:
            item["title"] = title
            item["scientific_name"] = record.scientific_name
            item["category"] = record.category
            item["last_discovered_at"] = record.created_at
            item["latest_record_id"] = record.id
            item["latest_image_url"] = record.image_url or item["latest_image_url"]
        elif record.image_url and not item["latest_image_url"]:
            item["latest_image_url"] = record.image_url
    return sorted(grouped.values(), key=lambda item: item["last_discovered_at"], reverse=True)


@router.post("/detections/{detection_id}/feedback")
def submit_feedback(
    detection_id: int,
    payload: RecognitionFeedbackRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    detection = db.get(Detection, detection_id)
    if not detection:
        raise HTTPException(status_code=404, detail="识别结果不存在")
    job = db.get(AnalysisJob, detection.job_id)
    if not job or (user.role == "public" and job.owner_id != user.id):
        raise HTTPException(status_code=403, detail="无权反馈该识别结果")
    feedback = RecognitionFeedback(
        user_id=user.id,
        detection_id=detection_id,
        **payload.model_dump(),
    )
    db.add(feedback)
    detection.review_status = "confirmed" if payload.is_correct else "needs_training"
    detection.review_note = payload.note
    if not payload.is_correct:
        if payload.corrected_label:
            detection.label = payload.corrected_label
        if payload.corrected_scientific_name:
            detection.scientific_name = payload.corrected_scientific_name
    record = db.scalar(
        select(DiscoveryRecord).where(
            DiscoveryRecord.user_id == user.id,
            DiscoveryRecord.detection_id == detection.id,
        )
    )
    if record:
        record.title = detection.phenomenon or detection.behavior or resolve_chinese_name(
            db, detection.scientific_name, detection.label, detection.category
        )
        record.scientific_name = detection.scientific_name
        record.category = detection.category
        record.confidence = detection.confidence
        record.behavior = detection.behavior
        record.phenomenon = detection.phenomenon
        if payload.note:
            record.note = payload.note
    learning_result = {"stored": False, "reason": "missing scientific name"}
    if detection.scientific_name:
        learning_result = learn_from_detection_correction(
            db,
            detection,
            scientific_name=detection.scientific_name,
            common_name=detection.label,
            category=detection.category,
            label_source="user-feedback",
            label_confidence=1.0 if not payload.is_correct else max(
                float(detection.confidence or 0.0),
                float(settings.active_learning_accept_min_confidence),
            ),
            validator=str(user.id),
            notes=payload.note,
        )
    user.points += 5
    db.commit()
    return {
        "message": "感谢反馈，已加入模型改进数据",
        "points": user.points,
        "active_learning": learning_result,
    }



@router.patch("/history/{record_id}/shared")
def mark_shared(
    record_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    record = db.get(DiscoveryRecord, record_id)
    if not record or record.user_id != user.id:
        raise HTTPException(status_code=404, detail="观察记录不存在")
    record.is_shared = True
    db.commit()
    return {"message": "已标记为分享", "record_id": record.id}

@router.get("/observations/analytics")
def observation_analytics(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    records = list(
        db.scalars(
            select(DiscoveryRecord)
            .where(DiscoveryRecord.user_id == user.id)
            .order_by(DiscoveryRecord.created_at)
        ).all()
    )
    species_counts: dict[str, int] = {}
    category_counts: dict[str, int] = {}
    animal_counts: dict[str, int] = {}
    plant_counts: dict[str, int] = {}
    nature_counts: dict[str, int] = {}
    behavior_counts: dict[str, int] = {}
    phenomenon_counts: dict[str, int] = {}
    date_counts: dict[str, int] = {}
    located = 0
    first_keys: set[str] = set()
    valid_records: list[DiscoveryRecord] = []
    for record in records:
        title = _clean_record_title(db, record)
        if not _is_clean_observation(record, title):
            continue
        group = _analytics_group(record.category)
        if not group:
            continue
        valid_records.append(record)
        category = normalize_category(record.category)
        key = str(record.species_id) if record.species_id else f"{category}:{title}"
        first_keys.add(key)
        species_counts[title] = species_counts.get(title, 0) + 1
        category_counts[category] = category_counts.get(category, 0) + 1
        if group == "animal":
            animal_counts[category] = animal_counts.get(category, 0) + 1
        elif group == "plant":
            plant_counts[category] = plant_counts.get(category, 0) + 1
        else:
            nature_counts[category] = nature_counts.get(category, 0) + 1
        if record.behavior:
            behavior_counts[record.behavior] = behavior_counts.get(record.behavior, 0) + 1
        if record.phenomenon:
            phenomenon_counts[record.phenomenon] = phenomenon_counts.get(record.phenomenon, 0) + 1
        date_key = record.created_at.date().isoformat()
        date_counts[date_key] = date_counts.get(date_key, 0) + 1
        if db.scalar(
            select(func.count(ObservationLocation.id)).where(
                ObservationLocation.discovery_id == record.id,
                ObservationLocation.latitude.is_not(None),
                ObservationLocation.longitude.is_not(None),
            )
        ):
            located += 1

    def ranked(values: dict[str, int], limit: int = 12) -> list[dict]:
        return [
            {"name": name, "value": value}
            for name, value in sorted(values.items(), key=lambda item: item[1], reverse=True)[:limit]
        ]

    return {
        "summary": {
            "observations": len(valid_records),
            "unique_taxa": len(first_keys),
            "located": located,
            "repeat_observations": max(0, len(valid_records) - len(first_keys)),
        },
        "species_counts": ranked(species_counts),
        "category_counts": ranked(category_counts, 30),
        "animal_counts": ranked(animal_counts, 30),
        "plant_counts": ranked(plant_counts, 30),
        "nature_counts": ranked(nature_counts, 30),
        "behavior_counts": ranked(behavior_counts),
        "phenomenon_counts": ranked(phenomenon_counts),
        "timeline": [
            {"date": date, "value": value}
            for date, value in sorted(date_counts.items())
        ],
    }
