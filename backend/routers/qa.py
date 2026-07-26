from __future__ import annotations

import mimetypes
import re
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from backend.core.database import get_db
from backend.core.config import get_settings
from backend.deps import get_current_user
from backend.models import (
    DiscoveryRecord,
    ObservationLocation,
    QAConversation,
    QAMessage,
    Species,
    User,
    UserCollection,
    now_utc,
)
from backend.schemas import QAConversationOut, QAMessageOut, QARequest, QAResponse
from backend.services.qa import answer_question
from backend.services.species_profile import ensure_species_from_user_text
from backend.services.text_clean import clean_title
from backend.services.user_memory import remember_interaction

router = APIRouter(prefix="/api/qa", tags=["qa"])
settings = get_settings()
ALLOWED_IMAGE_TYPES = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}
CITY_COORDINATES: dict[str, tuple[float, float]] = {
    "北京": (39.9042, 116.4074),
    "天津": (39.3434, 117.3616),
    "上海": (31.2304, 121.4737),
    "重庆": (29.5630, 106.5516),
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
}

KNOWN_NAME_RE = re.compile(r"[\u4e00-\u9fffA-Za-z][\u4e00-\u9fffA-Za-z\s.-]{1,80}")
LOCATION_PATTERNS = (
    re.compile(r"(?:地点|位置|地址)\s*(?:是|在|为|:|：)?\s*([\u4e00-\u9fffA-Za-z0-9·.\-\s]{2,80})"),
    re.compile(r"(?:在|位于)\s*([\u4e00-\u9fffA-Za-z0-9·.\-\s]{2,80}?)(?:发现|看到|拍到|观察到|加入|记录|$)"),
)


@router.post("/attachments")
async def upload_attachment(
    file: UploadFile = File(...),
    _: User = Depends(get_current_user),
) -> dict:
    content_type = (file.content_type or mimetypes.guess_type(file.filename or "")[0] or "").lower()
    if content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(status_code=400, detail="仅支持 JPG、PNG、WebP 图片")
    payload = await file.read(8 * 1024 * 1024 + 1)
    if len(payload) > 8 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="图片不能超过 8MB")
    filename = f"qa_{uuid.uuid4().hex}{ALLOWED_IMAGE_TYPES[content_type]}"
    path = settings.upload_dir / filename
    path.write_bytes(payload)
    return {"image_url": f"/media/uploads/{path.name}"}


@router.get("/conversations", response_model=list[QAConversationOut])
def conversations(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[dict]:
    rows = db.scalars(
        select(QAConversation)
        .where(QAConversation.user_id == user.id)
        .order_by(QAConversation.created_at.desc())
        .limit(100)
    ).all()
    output = []
    for item in rows:
        last_at = db.scalar(
            select(func.max(QAMessage.created_at)).where(QAMessage.conversation_id == item.id)
        )
        output.append(
            {
                "id": item.id,
                "title": clean_title(item.title, fallback="新的自然问答"),
                "species_id": item.species_id,
                "job_id": item.job_id,
                "detection_id": item.detection_id,
                "created_at": item.created_at,
                "last_message_at": last_at,
            }
        )
    return output


@router.post("/conversations", response_model=QAConversationOut)
def new_conversation(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    conversation = QAConversation(user_id=user.id, title="新的自然问答")
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    return {
        "id": conversation.id,
        "title": conversation.title,
        "species_id": conversation.species_id,
        "job_id": conversation.job_id,
        "detection_id": conversation.detection_id,
        "created_at": conversation.created_at,
        "last_message_at": None,
    }


@router.get("/conversations/{conversation_id}/messages", response_model=list[QAMessageOut])
def conversation_messages(
    conversation_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[QAMessage]:
    conversation = db.get(QAConversation, conversation_id)
    if not conversation or conversation.user_id != user.id:
        raise HTTPException(status_code=404, detail="聊天记录不存在")
    return list(
        db.scalars(
            select(QAMessage)
            .where(QAMessage.conversation_id == conversation.id)
            .order_by(QAMessage.created_at)
        ).all()
    )


@router.post("/ask", response_model=QAResponse)
async def ask(
    payload: QARequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> QAResponse:
    species = db.get(Species, payload.species_id) if payload.species_id else None
    if not species:
        species = await _resolve_species_from_question(db, payload.question)
    location_text = _extract_location(payload.question)

    conversation = db.get(QAConversation, payload.conversation_id) if payload.conversation_id else None
    if not conversation:
        conversation = QAConversation(
            user_id=user.id,
            species_id=species.id if species else payload.species_id,
            job_id=payload.job_id,
            detection_id=payload.detection_id,
            title=clean_title(payload.question, fallback="新的自然问答"),
        )
        db.add(conversation)
        db.flush()
    elif conversation.user_id != user.id:
        raise HTTPException(status_code=404, detail="聊天记录不存在")
    if conversation.title in {"新的自然问答", "自然智能问答"} or len(conversation.title) < 6:
        conversation.title = clean_title(payload.question, fallback="新的自然问答")
    if species:
        conversation.species_id = species.id
        _touch_collection(db, user, species)
        _maybe_create_footprint(db, user, species, location_text, payload.question, payload.image_url)
    user_content = f"{payload.question}\n\n[图片附件] {payload.image_url}" if payload.image_url else payload.question
    db.add(QAMessage(conversation_id=conversation.id, role="user", content=user_content))
    answer, sources, mode, fallback_reason, suggestions = await answer_question(
        db, payload.question, species.id if species else payload.species_id, payload.job_id, payload.detection_id, user=user
    )
    if species:
        remember_interaction(db, user, question=payload.question, answer=answer, species=species, location=location_text)
    db.add(
        QAMessage(
            conversation_id=conversation.id,
            role="assistant",
            content=answer,
            sources=sources,
        )
    )
    db.commit()
    return QAResponse(
        answer=answer,
        conversation_id=conversation.id,
        sources=sources,
        mode=mode,
        fallback_reason=fallback_reason,
        suggested_questions=suggestions,
    )


async def _resolve_species_from_question(db: Session, question: str) -> Species | None:
    text = (question or "").strip()
    if not text:
        return None
    known = db.scalars(
        select(Species).where(
            or_(
                Species.common_name != "",
                Species.scientific_name != "",
                Species.english_name != "",
            )
        ).limit(5000)
    ).all()
    lowered = text.lower()
    for species in known:
        names = [species.common_name, species.scientific_name, species.english_name]
        if any(name and name.lower() in lowered for name in names):
            return species

    candidates = []
    for match in KNOWN_NAME_RE.findall(text):
        value = match.strip(" ，。？！,.;:：")
        if len(value) < 2:
            continue
        value = re.sub(r"(是什么|加入生态图谱|加入图鉴|发现|观察|资料|科普|地点.*)$", "", value).strip()
        if value and value not in {"这个", "图片", "照片", "自然", "动物", "植物", "地点"}:
            candidates.append(value)
    for candidate in candidates[:3]:
        species = await ensure_species_from_user_text(db, species_name=candidate)
        if species:
            return species
    return None


def _touch_collection(db: Session, user: User, species: Species) -> None:
    item = db.scalar(
        select(UserCollection).where(
            UserCollection.user_id == user.id,
            UserCollection.species_id == species.id,
        )
    )
    if item:
        item.knowledge_progress = min(100, max(item.knowledge_progress, 45))
        item.stars_earned = max(item.stars_earned, max(1, min(5, species.rarity)))
        item.last_discovered_at = now_utc()
    else:
        db.add(
            UserCollection(
                user_id=user.id,
                species_id=species.id,
                discovered_count=0,
                knowledge_progress=45,
                stars_earned=max(1, min(5, species.rarity)),
            )
        )
        user.stars += max(1, min(5, species.rarity))
    user.points += 1
    user.level = max(1, 1 + user.points // 300)


def _extract_location(question: str) -> str:
    text = (question or "").strip()
    for pattern in LOCATION_PATTERNS:
        match = pattern.search(text)
        if match:
            value = match.group(1).strip(" ，。？！,.;:：")
            value = re.sub(r"(请|帮我|并|，.*|。.*)$", "", value).strip()
            if len(value) >= 2:
                return value[:80]
    return ""


def _coords_for_location(location: str) -> tuple[float | None, float | None, str]:
    for name, coords in CITY_COORDINATES.items():
        if name in location:
            return coords[0], coords[1], name
    return None, None, ""


def _maybe_create_footprint(
    db: Session,
    user: User,
    species: Species,
    location: str,
    question: str,
    image_url: str = "",
) -> None:
    if not location:
        return
    title = species.common_name or species.scientific_name
    record = DiscoveryRecord(
        user_id=user.id,
        species_id=species.id,
        record_type="species",
        title=title,
        scientific_name=species.scientific_name,
        category=species.category,
        image_url=image_url,
        confidence=1.0,
        note=f"来自自然问答：{question[:160]}",
        stars_earned=max(1, min(5, species.rarity)),
    )
    db.add(record)
    db.flush()
    latitude, longitude, city = _coords_for_location(location)
    privacy = "obscured" if species.rarity >= 4 else "precise"
    db.add(
        ObservationLocation(
            discovery_id=record.id,
            latitude=latitude,
            longitude=longitude,
            city=city,
            district=location,
            location_source="manual",
            privacy_level=privacy,
        )
    )
