from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.core.database import get_db
from backend.deps import get_current_user
from backend.models import AnalysisJob, Detection, RiskEvent, Species, User, UserCollection

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("")
def dashboard(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    jobs = db.scalar(select(func.count(AnalysisJob.id))) or 0
    detections = db.scalar(select(func.count(Detection.id))) or 0
    species_total = db.scalar(select(func.count(Species.id))) or 0
    alerts = db.scalar(select(func.count(RiskEvent.id)).where(RiskEvent.status == "pending")) or 0
    collection = db.scalar(
        select(func.count(UserCollection.id)).where(UserCollection.user_id == user.id)
    ) or 0
    latest_jobs = db.scalars(select(AnalysisJob).order_by(AnalysisJob.id.desc()).limit(5)).all()
    latest_events = db.scalars(select(RiskEvent).order_by(RiskEvent.id.desc()).limit(5)).all()
    category_rows = db.execute(
        select(Detection.category, func.count(Detection.id)).group_by(Detection.category)
    ).all()
    return {
        "stats": {
            "analysis_jobs": jobs,
            "detections": detections,
            "species_total": species_total,
            "pending_alerts": alerts,
            "collection_count": collection,
            "points": user.points,
            "stars": user.stars,
            "level": user.level,
        },
        "category_distribution": [{"name": row[0], "value": row[1]} for row in category_rows],
        "latest_jobs": [
            {
                "id": item.id,
                "filename": item.media.filename,
                "status": item.status,
                "progress": item.progress,
                "summary": item.summary,
                "created_at": item.created_at,
            }
            for item in latest_jobs
        ],
        "latest_events": [
            {
                "id": item.id,
                "title": item.title,
                "severity": item.severity,
                "status": item.status,
                "created_at": item.created_at,
            }
            for item in latest_events
        ],
    }
