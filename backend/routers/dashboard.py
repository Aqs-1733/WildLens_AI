from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.core.database import get_db
from backend.deps import get_current_user
from backend.models import AnalysisJob, Detection, DiscoveryRecord, RiskEvent, Species, User, UserCollection
from backend.services.taxon_names import has_cjk, normalize_category

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

EXCLUDED_DASHBOARD_CATEGORIES = {"unknown", "person", "vehicle", "human"}
UNCERTAIN_DASHBOARD_TOKENS = ("低置信度", "待确认", "疑似", "候选", "unknown", "unidentified")


def _dashboard_observation_title(record: DiscoveryRecord) -> str:
    return " ".join(str(record.phenomenon or record.behavior or record.title or "").split())


def _include_dashboard_observation(record: DiscoveryRecord) -> bool:
    title = _dashboard_observation_title(record)
    category = normalize_category(record.category)
    if category in EXCLUDED_DASHBOARD_CATEGORIES:
        return False
    if not has_cjk(title):
        return False
    lowered = title.lower()
    return not any(token.lower() in lowered for token in UNCERTAIN_DASHBOARD_TOKENS)


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
    category_distribution: dict[str, int] = {}
    observation_rows = db.scalars(
        select(DiscoveryRecord).where(DiscoveryRecord.user_id == user.id)
    ).all()
    for record in observation_rows:
        if not _include_dashboard_observation(record):
            continue
        category = normalize_category(record.category)
        category_distribution[category] = category_distribution.get(category, 0) + 1
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
        "category_distribution": [
            {"name": name, "value": value}
            for name, value in sorted(category_distribution.items(), key=lambda item: item[1], reverse=True)
        ],
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
