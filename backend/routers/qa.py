from __future__ import annotations

import mimetypes
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.core.database import get_db
from backend.core.config import get_settings
from backend.deps import get_current_user
from backend.models import QAConversation, QAMessage, Species, User, UserCollection, now_utc
from backend.schemas import QAConversationOut, QAMessageOut, QARequest, QAResponse
from backend.services.qa import answer_question

router = APIRouter(prefix="/api/qa", tags=["qa"])
settings = get_settings()
ALLOWED_IMAGE_TYPES = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}


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
                "title": item.title,
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
    conversation = db.get(QAConversation, payload.conversation_id) if payload.conversation_id else None
    if not conversation:
        conversation = QAConversation(
            user_id=user.id,
            species_id=payload.species_id,
            job_id=payload.job_id,
            detection_id=payload.detection_id,
            title=payload.question[:80],
        )
        db.add(conversation)
        db.flush()
    elif conversation.user_id != user.id:
        raise HTTPException(status_code=404, detail="聊天记录不存在")
    if conversation.title in {"新的自然问答", "自然智能问答"} or len(conversation.title) < 6:
        conversation.title = payload.question[:40]
    if payload.species_id and (species := db.get(Species, payload.species_id)):
        collection = db.scalar(
            select(UserCollection).where(
                UserCollection.user_id == user.id,
                UserCollection.species_id == species.id,
            )
        )
        if collection:
            collection.knowledge_progress = min(100, max(collection.knowledge_progress, 35))
            collection.last_discovered_at = now_utc()
        else:
            db.add(
                UserCollection(
                    user_id=user.id,
                    species_id=species.id,
                    discovered_count=0,
                    knowledge_progress=35,
                    stars_earned=max(1, min(5, species.rarity)),
                )
            )
    user_content = f"{payload.question}\n\n[图片附件] {payload.image_url}" if payload.image_url else payload.question
    db.add(QAMessage(conversation_id=conversation.id, role="user", content=user_content))
    answer, sources, mode, fallback_reason, suggestions = await answer_question(
        db, payload.question, payload.species_id, payload.job_id, payload.detection_id
    )
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
