from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from backend.core.database import get_db
from backend.deps import require_regulator
from backend.models import AuditLog, Detection, ReviewResult, Species, User
from backend.schemas import DetectionReviewRequest
from backend.vision.learning_feedback import learn_from_detection_correction

router = APIRouter(prefix="/api/review", tags=["review"])


@router.get("/queue")
def review_queue(
    db: Session = Depends(get_db), _: User = Depends(require_regulator)
) -> list[dict]:
    items = db.scalars(
        select(Detection)
        .where(
            or_(
                Detection.review_status == "pending",
                Detection.confidence < 0.72,
                Detection.species_id.is_(None),
            )
        )
        .order_by(Detection.confidence.asc(), Detection.id.desc())
        .limit(100)
    ).all()
    return [
        {
            "id": item.id,
            "job_id": item.job_id,
            "track_id": item.track_id,
            "species_id": item.species_id,
            "label": item.label,
            "scientific_name": item.scientific_name,
            "category": item.category,
            "confidence": item.confidence,
            "timestamp_ms": item.timestamp_ms,
            "bbox": item.bbox,
            "color": item.color,
            "review_status": item.review_status,
            "review_note": item.review_note,
        }
        for item in items
    ]


@router.patch("/detections/{detection_id}")
def review_detection(
    detection_id: int,
    payload: DetectionReviewRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_regulator),
) -> dict:
    item = db.get(Detection, detection_id)
    if not item:
        raise HTTPException(status_code=404, detail="检测记录不存在")
    species = db.get(Species, payload.species_id) if payload.species_id else None
    if payload.species_id and not species:
        raise HTTPException(status_code=404, detail="物种不存在")
    original = {
        "species_id": item.species_id,
        "label": item.label,
        "scientific_name": item.scientific_name,
        "category": item.category,
        "confidence": item.confidence,
        "source": item.source,
    }
    item.species_id = species.id if species else None
    item.label = species.common_name if species else payload.label
    item.scientific_name = species.scientific_name if species else payload.scientific_name
    item.category = species.category if species else payload.category
    item.color = species.color if species else item.color
    item.review_status = payload.status
    item.review_note = payload.note
    item.reviewed_by = user.id
    corrected = {
        "species_id": item.species_id,
        "label": item.label,
        "scientific_name": item.scientific_name,
        "category": item.category,
        "confidence": item.confidence,
        "source": "human-review",
    }
    learning_result = {"stored": False, "reason": "not a trainable review status"}
    if payload.status in {"confirmed", "needs_training"} and item.scientific_name:
        learning_result = learn_from_detection_correction(
            db,
            item,
            scientific_name=item.scientific_name,
            common_name=item.label,
            category=item.category,
            label_source="human-review",
            label_confidence=1.0,
            validator=str(user.id),
            notes=payload.note,
        )
    db.add(
        ReviewResult(
            detection_id=item.id,
            reviewer_id=user.id,
            original_prediction=original,
            corrected_prediction=corrected,
            status=payload.status,
            reason=payload.note,
            enter_training=payload.status in {"confirmed", "needs_training"},
        )
    )
    db.add(
        AuditLog(
            actor_id=user.id,
            action="review_detection",
            entity_type="detection",
            entity_id=str(item.id),
            detail={
                "status": payload.status,
                "enter_training": payload.status in {"confirmed", "needs_training"},
                "active_learning": learning_result,
            },
        )
    )
    db.commit()
    return {
        "message": "复核结果已保存",
        "id": item.id,
        "review_status": item.review_status,
        "active_learning": learning_result,
    }
