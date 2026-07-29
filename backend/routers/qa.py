from __future__ import annotations

import mimetypes
import re
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from backend.core.database import get_db
from backend.core.config import get_settings
from backend.core.pagination import paginate_scalars
from backend.deps import get_current_user
from backend.models import (
    Detection,
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
    re.compile(r"(?:地点|位置|地址)\s*(?:改为|修改为|更改为|更新为|设为|放到|是|在|为|:|：)\s*([\u4e00-\u9fffA-Za-z0-9·.\-\s]{2,80})"),
    re.compile(r"(?:登记在|记录在|加入到)\s*([\u4e00-\u9fffA-Za-z0-9·.\-\s]{2,80})"),
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
    response: Response,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[dict]:
    rows = paginate_scalars(
        db,
        select(QAConversation)
        .where(QAConversation.user_id == user.id)
        .order_by(QAConversation.created_at.desc()),
        response=response,
        page=page,
        limit=limit,
    )
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
    response: Response,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=100, ge=1, le=300),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[QAMessage]:
    conversation = db.get(QAConversation, conversation_id)
    if not conversation or conversation.user_id != user.id:
        raise HTTPException(status_code=404, detail="聊天记录不存在")
    return list(
        paginate_scalars(
            db,
            select(QAMessage)
            .where(QAMessage.conversation_id == conversation.id)
            .order_by(QAMessage.created_at),
            response=response,
            page=page,
            limit=limit,
            max_limit=300,
        )
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
    if not species and conversation.species_id:
        species = db.get(Species, conversation.species_id)
    effective_job_id = payload.job_id or conversation.job_id
    effective_detection_id = payload.detection_id or conversation.detection_id
    if payload.job_id:
        conversation.job_id = payload.job_id
    if payload.detection_id:
        conversation.detection_id = payload.detection_id
    if conversation.title in {"新的自然问答", "自然智能问答"} or len(conversation.title) < 6:
        conversation.title = clean_title(payload.question, fallback="新的自然问答")
    mutation_intent = _record_mutation_intent(payload.question)
    if species:
        conversation.species_id = species.id
        if not mutation_intent:
            _touch_collection(db, user, species)
            _maybe_create_footprint(db, user, species, location_text, payload.question, payload.image_url)
    user_content = f"{payload.question}\n\n[图片附件] {payload.image_url}" if payload.image_url else payload.question
    db.add(QAMessage(conversation_id=conversation.id, role="user", content=user_content))
    mutation_sources: list[dict] = []
    mutation = await _handle_record_mutation(db, user, payload, species, location_text)
    if mutation:
        _, mutation_sources = mutation
    answer, sources, mode, fallback_reason, suggestions = await answer_question(
        db,
        payload.question,
        species.id if species else payload.species_id,
        effective_job_id,
        effective_detection_id,
        user=user,
        image_url=payload.image_url,
    )
    if mutation_sources:
        sources = [*mutation_sources, *sources]
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


def _record_mutation_intent(text: str) -> bool:
    return _wants_location_update(text) or _wants_note_update(text) or any(
        word in text for word in ("登记", "加入观察", "加入生态图谱", "加入图鉴", "记一条", "记录在")
    )


def _wants_location_update(text: str) -> bool:
    return any(word in text for word in ("位置", "地点", "地址")) and any(
        word in text for word in ("改为", "修改", "更改", "更新", "设为", "放到")
    )


def _wants_note_update(text: str) -> bool:
    return any(word in text for word in ("备注", "说明", "笔记")) and any(
        word in text for word in ("改为", "修改", "更改", "更新", "设为")
    )


async def _handle_record_mutation(
    db: Session,
    user: User,
    payload: QARequest,
    species: Species | None,
    location_text: str,
) -> tuple[str, list[dict]] | None:
    text = (payload.question or "").strip()
    if not text:
        return None
    wants_location_update = _wants_location_update(text)
    wants_note_update = _wants_note_update(text)
    wants_register = any(word in text for word in ("登记", "加入观察", "加入生态图谱", "加入图鉴", "记一条", "记录在"))
    if not (wants_location_update or wants_note_update or wants_register):
        return None

    if wants_register and not any(word in text for word in ("修改", "改为", "更改", "更新")):
        target_species = species or await _resolve_species_from_question(db, text)
        if not target_species:
            return (
                "我需要先确定要登记的物种。请把物种中文名或学名说清楚，例如“将今天看到的银杏登记在天津水上公园”。",
                [{"kind": "record_mutation", "status": "need_species"}],
            )
        location = location_text or _extract_location(text)
        if not location:
            return (
                f"已定位到物种“{target_species.common_name}”，但没有识别到地点。请补充地点后我再写入观察记录。",
                [{"kind": "record_mutation", "status": "need_location", "species_id": target_species.id}],
            )
        record = DiscoveryRecord(
            user_id=user.id,
            species_id=target_species.id,
            record_type="species",
            title=target_species.common_name,
            scientific_name=target_species.scientific_name,
            category=target_species.category,
            image_url=payload.image_url,
            confidence=1.0,
            note=f"来自自然问答登记：{text[:160]}",
            stars_earned=max(1, min(5, target_species.rarity)),
        )
        db.add(record)
        db.flush()
        _set_record_location(db, record, location, target_species)
        _touch_collection(db, user, target_species)
        return (
            f"已新增观察记录 #{record.id}：{target_species.common_name}（{target_species.scientific_name}），地点：{location}。这条记录已进入观察记录、自然图鉴和地图统计。",
            [{"kind": "record_mutation", "action": "create_observation", "record_id": record.id, "location": location}],
        )

    record_resolution = _resolve_record_for_mutation(db, user, payload, species, text)
    if isinstance(record_resolution, tuple):
        records = record_resolution[1]
        choices = "\n".join(
            f"{index + 1}. #{record.id} {record.title}，{record.scientific_name or '无学名'}，{record.created_at.strftime('%Y-%m-%d %H:%M')}"
            for index, record in enumerate(records)
        )
        return (
            f"我找到多条可能要修改的记录，请你明确第几条或记录编号：\n{choices}",
            [{"kind": "record_mutation", "status": "ambiguous", "record_ids": [record.id for record in records]}],
        )
    record = record_resolution
    if not record:
        return (
            "没有找到可修改的观察记录。请说明记录编号、最近一次记录，或先完成一次识别保存。",
            [{"kind": "record_mutation", "status": "not_found"}],
        )

    before = _record_snapshot(db, record)
    changed: list[str] = []
    location = location_text or _extract_location(text)
    if wants_location_update and location:
        _set_record_location(db, record, location, record.species)
        changed.append(f"地点改为：{location}")
    note = _extract_note_update(text)
    if wants_note_update and note:
        record.note = note
        changed.append(f"备注改为：{note}")
    if not changed:
        return (
            f"已定位到记录 #{record.id}（{record.title}），但没有识别到新的地点或备注内容，请再说清楚要改成什么。",
            [{"kind": "record_mutation", "status": "need_new_value", "record_id": record.id}],
        )
    record.created_at = now_utc()
    after = _record_snapshot(db, record)
    return (
        f"已修改观察记录 #{record.id}。\n修改前：{before}\n修改后：{after}",
        [{"kind": "record_mutation", "action": "update_record", "record_id": record.id, "changes": changed}],
    )


def _resolve_record_for_mutation(
    db: Session,
    user: User,
    payload: QARequest,
    species: Species | None,
    text: str,
) -> DiscoveryRecord | tuple[str, list[DiscoveryRecord]] | None:
    if payload.detection_id:
        record = db.scalar(
            select(DiscoveryRecord).where(
                DiscoveryRecord.user_id == user.id,
                DiscoveryRecord.detection_id == payload.detection_id,
            )
        )
        if record:
            return record
    id_match = re.search(r"(?:#|编号|记录)\s*(\d+)", text)
    if id_match:
        record = db.get(DiscoveryRecord, int(id_match.group(1)))
        if record and record.user_id == user.id:
            return record
    ordinal_match = re.search(r"第\s*(\d+)\s*条", text)
    rows = list(
        db.scalars(
            select(DiscoveryRecord)
            .where(DiscoveryRecord.user_id == user.id)
            .order_by(DiscoveryRecord.created_at.desc())
            .limit(8)
        ).all()
    )
    if ordinal_match:
        index = int(ordinal_match.group(1)) - 1
        return rows[index] if 0 <= index < len(rows) else None
    if species:
        species_rows = [
            record
            for record in rows
            if record.species_id == species.id or record.scientific_name == species.scientific_name
        ]
        if len(species_rows) == 1:
            return species_rows[0]
        if len(species_rows) > 1:
            return ("ambiguous", species_rows[:5])
    return rows[0] if len(rows) == 1 or "最近" in text or "这条" in text else ("ambiguous", rows[:5]) if rows else None


def _set_record_location(db: Session, record: DiscoveryRecord, location: str, species: Species | None) -> None:
    latitude, longitude, city = _coords_for_location(location)
    privacy = "obscured" if species and species.rarity >= 4 else "precise"
    row = db.scalar(select(ObservationLocation).where(ObservationLocation.discovery_id == record.id))
    if not row:
        row = ObservationLocation(discovery_id=record.id)
        db.add(row)
    row.latitude = latitude
    row.longitude = longitude
    row.city = city
    row.district = location[:80]
    row.location_source = "manual"
    row.privacy_level = privacy
    row.observed_at = now_utc()


def _extract_note_update(text: str) -> str:
    match = re.search(r"(?:备注|说明|笔记)\s*(?:改为|修改为|更改为|更新为|设为|:|：)\s*(.+)", text)
    return match.group(1).strip(" ，。；;")[:1000] if match else ""


def _record_snapshot(db: Session, record: DiscoveryRecord) -> str:
    location = db.scalar(select(ObservationLocation).where(ObservationLocation.discovery_id == record.id))
    place = ""
    if location:
        place = " / ".join(part for part in (location.province, location.city, location.district) if part)
    return (
        f"{record.title}；学名：{record.scientific_name or '无'}；地点：{place or '未填写'}；"
        f"备注：{record.note or '无'}"
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
