from __future__ import annotations

import mimetypes
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Body, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from backend.core.config import get_settings
from backend.core.database import get_db
from backend.deps import get_current_user, require_regulator
from backend.models import (
    AnalysisJob,
    Detection,
    Favorite,
    MediaFile,
    Report,
    RiskEvent,
    Species,
    User,
)
from backend.routers.identify import history, identify_photo
from backend.routers.qa import ask as ask_question
from backend.routers.review import review_detection, review_queue
from backend.routers.system import dataset_registry, model_registry
from backend.routers.videos import get_job as get_video_job
from backend.routers.videos import list_jobs as list_video_jobs
from backend.routers.videos import upload_video
from backend.schemas import DetectionReviewRequest, QARequest
from backend.services.reports import create_job_report
from backend.vision.pipeline import process_job

settings = get_settings()
router = APIRouter(tags=["compatibility"])

IMAGE_TYPES = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}
VIDEO_SUFFIXES = {".mp4", ".webm", ".mov", ".avi", ".mkv"}


def _media_url(path: str) -> str:
    file_path = Path(path)
    if not file_path.name:
        return ""
    if file_path.parent == settings.report_dir:
        return f"/media/reports/{file_path.name}"
    if file_path.parent == settings.result_dir:
        return f"/media/results/{file_path.name}"
    return f"/media/uploads/{file_path.name}"


def _media_dict(item: MediaFile) -> dict[str, Any]:
    return {
        "id": item.id,
        "filename": item.filename,
        "media_type": item.media_type,
        "url": _media_url(item.stored_path),
        "duration_seconds": item.duration_seconds,
        "size_bytes": item.size_bytes,
        "created_at": item.created_at,
    }


def _risk_level(detection: Detection) -> str:
    if detection.category in {"fire", "smoke"}:
        return "high" if detection.confidence >= 0.7 else "medium"
    if detection.category in {"person", "vehicle"}:
        return "medium"
    if detection.confidence < 0.55:
        return "review"
    return "low"


def _model_metadata(evidence: list) -> dict:
    for entry in evidence or []:
        if isinstance(entry, dict) and entry.get("kind") == "model_evidence":
            return entry
    return {}


def _detection_dict(item: Detection, created_at: Any = None) -> dict[str, Any]:
    taxonomy = item.species.taxonomy if item.species else {}
    family = taxonomy.get("family", "") if isinstance(taxonomy, dict) else ""
    genus = taxonomy.get("genus", "") if isinstance(taxonomy, dict) else ""
    metadata = _model_metadata(item.evidence or [])
    return {
        "detection_id": item.id,
        "id": item.id,
        "job_id": item.job_id,
        "track_id": item.track_id,
        "category": item.category,
        "scientific_name": item.scientific_name,
        "common_name": item.label,
        "taxon_id": item.species_id,
        "family": family,
        "genus": genus,
        "confidence": item.confidence,
        "prototype_similarity": None,
        "model_source": item.source,
        "candidate_scope": "species" if item.species_id else "open-set",
        "bounding_box": item.bbox,
        "bbox": item.bbox,
        "risk_level": _risk_level(item),
        "is_uncertain": item.confidence < 0.72 or item.species_id is None,
        "needs_review": item.review_status == "pending" or item.confidence < 0.72 or item.species_id is None,
        "evidence": item.evidence or [],
        "speciesnet_evidence": metadata.get("speciesnet_evidence"),
        "bioclip_evidence": metadata.get("bioclip_evidence"),
        "local_prototype_evidence": metadata.get("local_prototype_evidence"),
        "fusion_decision": metadata.get("fusion_decision"),
        "fusion_status": metadata.get("fusion_status"),
        "fusion_reason": metadata.get("fusion_reason"),
        "bioclip_top_k": metadata.get("bioclip_top_k") or [],
        "bioclip_similarity": metadata.get("bioclip_similarity"),
        "bioclip_top1_margin": metadata.get("bioclip_top1_margin"),
        "prototype_image_count": metadata.get("prototype_image_count"),
        "model_warnings": metadata.get("model_warnings") or [],
        "detections": metadata.get("detections") or [],
        "created_at": created_at,
    }


@router.post("/api/media/upload")
async def upload_media(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    content_type = (file.content_type or mimetypes.guess_type(file.filename or "")[0] or "").lower()
    suffix = Path(file.filename or "").suffix.lower()
    if content_type in IMAGE_TYPES:
        suffix = IMAGE_TYPES[content_type]
        media_type = "image"
    elif suffix in VIDEO_SUFFIXES or content_type.startswith("video/"):
        media_type = "video"
        suffix = suffix or ".mp4"
    else:
        raise HTTPException(status_code=400, detail="仅支持 JPG、PNG、WebP、MP4、MOV、AVI、MKV")
    filename = f"media_{user.id}_{uuid.uuid4().hex}{suffix}"
    destination = settings.upload_dir / filename
    size = 0
    with destination.open("wb") as target:
        while chunk := await file.read(1024 * 1024):
            size += len(chunk)
            target.write(chunk)
    item = MediaFile(
        owner_id=user.id,
        filename=file.filename or filename,
        stored_path=str(destination),
        media_type=media_type,
        size_bytes=size,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return _media_dict(item)


@router.get("/api/media")
def list_media(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> list[dict[str, Any]]:
    stmt = select(MediaFile).order_by(MediaFile.id.desc())
    if user.role == "public":
        stmt = stmt.where(MediaFile.owner_id == user.id)
    return [_media_dict(item) for item in db.scalars(stmt).all()]


@router.get("/api/media/{media_id}")
def get_media(
    media_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    item = db.get(MediaFile, media_id)
    if not item or (user.role == "public" and item.owner_id != user.id):
        raise HTTPException(status_code=404, detail="媒体不存在")
    return _media_dict(item)


@router.post("/api/analysis/image")
async def analyze_image(
    file: UploadFile = File(...),
    hint: str = Form(default=""),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return await identify_photo(file=file, hint=hint, db=db, user=user)


@router.post("/api/analysis/video")
async def analyze_video(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    mode: str = Form("standard"),
    targets: str = Form("animals,plants,people,fire"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    return await upload_video(background_tasks, file=file, mode=mode, targets=targets, db=db, user=user)


@router.get("/api/jobs")
def list_jobs(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return list_video_jobs(db=db, user=user)


@router.get("/api/jobs/{job_id}")
def get_job(job_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return get_video_job(job_id=job_id, db=db, user=user)


@router.post("/api/jobs/{job_id}/cancel")
def cancel_job(
    job_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    item = db.get(AnalysisJob, job_id)
    if not item or (user.role == "public" and item.owner_id != user.id):
        raise HTTPException(status_code=404, detail="任务不存在")
    if item.status != "completed":
        item.status = "cancelled"
        item.error_message = "用户取消任务"
        db.commit()
    return {"id": item.id, "status": item.status}


@router.post("/api/jobs/{job_id}/retry")
def retry_job(
    job_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    item = db.get(AnalysisJob, job_id)
    if not item or (user.role == "public" and item.owner_id != user.id):
        raise HTTPException(status_code=404, detail="任务不存在")
    if item.status not in {"failed", "cancelled"}:
        raise HTTPException(status_code=409, detail="只有失败或取消的任务可以重试")
    retry = AnalysisJob(
        owner_id=item.owner_id,
        media_id=item.media_id,
        status="queued",
        progress=0,
        mode=item.mode,
        enabled_targets=item.enabled_targets,
        summary={"retry_of": item.id},
    )
    db.add(retry)
    db.commit()
    db.refresh(retry)
    background_tasks.add_task(process_job, retry.id)
    return {"job_id": retry.id, "status": retry.status, "retry_of": item.id}


@router.get("/api/detections")
def list_detections(
    job_id: int | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[dict[str, Any]]:
    stmt = select(Detection).join(AnalysisJob, AnalysisJob.id == Detection.job_id)
    if job_id:
        stmt = stmt.where(Detection.job_id == job_id)
    if user.role == "public":
        stmt = stmt.where(AnalysisJob.owner_id == user.id)
    items = db.scalars(stmt.order_by(Detection.id.desc()).limit(300)).all()
    job_ids = {item.job_id for item in items}
    jobs = {
        item.id: item
        for item in db.scalars(select(AnalysisJob).where(AnalysisJob.id.in_(job_ids))).all()
    } if job_ids else {}
    return [_detection_dict(item, jobs.get(item.job_id).created_at if jobs.get(item.job_id) else None) for item in items]


@router.post("/api/reviews")
def create_review(
    payload: dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_regulator),
):
    detection_id = int(payload.get("detection_id") or payload.get("id") or 0)
    request = DetectionReviewRequest(
        species_id=payload.get("species_id"),
        label=str(payload.get("label") or "待确认目标"),
        scientific_name=str(payload.get("scientific_name") or ""),
        category=str(payload.get("category") or "unknown"),
        status=str(payload.get("status") or "confirmed"),
        note=str(payload.get("note") or payload.get("reason") or ""),
    )
    return review_detection(detection_id=detection_id, payload=request, db=db, user=user)


@router.get("/api/reviews")
def list_reviews(db: Session = Depends(get_db), user: User = Depends(require_regulator)):
    return review_queue(db=db, _=user)


@router.get("/api/risks")
def list_risks(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> list[dict[str, Any]]:
    stmt = select(RiskEvent).outerjoin(AnalysisJob, AnalysisJob.id == RiskEvent.job_id)
    if user.role == "public":
        stmt = stmt.where(or_(RiskEvent.job_id.is_(None), AnalysisJob.owner_id == user.id))
    items = db.scalars(stmt.order_by(RiskEvent.created_at.desc()).limit(200)).all()
    output: list[dict[str, Any]] = []
    jobs = {
        item.id: item
        for item in db.scalars(
            select(AnalysisJob).where(AnalysisJob.id.in_({event.job_id for event in items if event.job_id}))
        ).all()
    } if items else {}
    for item in items:
        job = jobs.get(item.job_id) if item.job_id else None
        output.append({
            "risk_id": item.id,
            "id": item.id,
            "risk_type": item.event_type,
            "severity": item.severity,
            "source_media": job.media.filename if job else "",
            "start_time": item.timestamp_ms,
            "end_time": item.timestamp_ms,
            "location": "",
            "evidence": item.evidence,
            "status": item.status,
            "assigned_to": "",
            "resolution": item.description,
            "created_at": item.created_at,
            "title": item.title,
            "confidence": item.confidence,
        })
    return output


@router.patch("/api/risks/{risk_id}")
def update_risk(
    risk_id: int,
    payload: dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    _: User = Depends(require_regulator),
) -> dict[str, Any]:
    item = db.get(RiskEvent, risk_id)
    if not item:
        raise HTTPException(status_code=404, detail="风险事件不存在")
    if payload.get("status"):
        item.status = str(payload["status"])
    if payload.get("resolution"):
        item.description = f"{item.description}\n处置记录：{payload['resolution']}"
    db.commit()
    return {"risk_id": item.id, "status": item.status, "resolution": item.description}


@router.post("/api/qa")
async def qa(payload: QARequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return await ask_question(payload=payload, db=db, user=user)


@router.get("/api/records")
def records(
    record_type: str = "",
    limit: int = 80,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return history(record_type=record_type, limit=limit, db=db, user=user)


@router.post("/api/favorites")
def create_favorite(
    payload: dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    species_id = int(payload.get("species_id") or 0)
    species = db.get(Species, species_id)
    if not species:
        raise HTTPException(status_code=404, detail="物种不存在")
    item = db.scalar(select(Favorite).where(Favorite.user_id == user.id, Favorite.species_id == species_id))
    if not item:
        item = Favorite(user_id=user.id, species_id=species_id)
        db.add(item)
        db.commit()
        db.refresh(item)
    return {"id": item.id, "species_id": species_id, "created_at": item.created_at}


@router.delete("/api/favorites/{favorite_id}")
def delete_favorite(
    favorite_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    item = db.get(Favorite, favorite_id)
    if not item:
        item = db.scalar(select(Favorite).where(Favorite.user_id == user.id, Favorite.species_id == favorite_id))
    if not item or item.user_id != user.id:
        raise HTTPException(status_code=404, detail="收藏不存在")
    db.delete(item)
    db.commit()
    return {"deleted": True, "id": favorite_id}


@router.post("/api/reports")
def create_report(
    payload: dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    job_id = int(payload.get("job_id") or 0)
    job = db.get(AnalysisJob, job_id)
    if not job or (user.role == "public" and job.owner_id != user.id):
        raise HTTPException(status_code=404, detail="任务不存在")
    path = create_job_report(db, job_id)
    report = Report(
        job_id=job_id,
        owner_id=user.id,
        title=str(payload.get("title") or f"识境分析报告 #{job_id}"),
        stored_path=str(path),
        summary=job.summary or {},
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    return {"id": report.id, "job_id": job_id, "url": f"/api/reports/{report.id}"}


@router.get("/api/reports/{report_id}")
def get_report(
    report_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    item = db.get(Report, report_id)
    if not item or (user.role == "public" and item.owner_id != user.id):
        raise HTTPException(status_code=404, detail="报告不存在")
    return {
        "id": item.id,
        "job_id": item.job_id,
        "title": item.title,
        "report_type": item.report_type,
        "url": _media_url(item.stored_path),
        "summary": item.summary,
        "created_at": item.created_at,
    }


@router.get("/api/models")
def list_models_alias(user: User = Depends(require_regulator)):
    return model_registry(_=user)


@router.get("/api/datasets")
def list_datasets_alias(user: User = Depends(require_regulator)):
    return dataset_registry(_=user)
