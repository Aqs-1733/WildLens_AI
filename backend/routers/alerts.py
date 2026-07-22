from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.core.database import get_db
from backend.deps import require_regulator
from backend.models import RiskEvent, User
from backend.schemas import ReviewEventRequest

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


@router.get("")
def list_alerts(
    db: Session = Depends(get_db), _: User = Depends(require_regulator)
) -> list[dict]:
    items = db.scalars(select(RiskEvent).order_by(RiskEvent.created_at.desc())).all()
    return [
        {
            "id": item.id,
            "job_id": item.job_id,
            "event_type": item.event_type,
            "title": item.title,
            "severity": item.severity,
            "status": item.status,
            "description": item.description,
            "timestamp_ms": item.timestamp_ms,
            "confidence": item.confidence,
            "evidence": item.evidence,
            "ai_advice": item.ai_advice,
            "created_at": item.created_at,
        }
        for item in items
    ]


@router.patch("/{event_id}")
def review_alert(
    event_id: int,
    payload: ReviewEventRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_regulator),
) -> dict:
    item = db.get(RiskEvent, event_id)
    if not item:
        raise HTTPException(status_code=404, detail="事件不存在")
    item.status = payload.status
    if payload.note:
        item.description = f"{item.description}\n复核备注：{payload.note}"
    db.commit()
    return {"message": "事件状态已更新", "status": item.status}
