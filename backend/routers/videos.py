from __future__ import annotations

import uuid
from pathlib import Path

import cv2
from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.core.config import get_settings
from backend.core.database import get_db
from backend.deps import get_current_user
from backend.models import (
    AnalysisJob,
    Detection,
    MediaFile,
    MediaVariant,
    RiskEvent,
    TrackKeyframe,
    User,
    VideoTrack,
)
from backend.services.video_transcode import VideoTranscodeError, probe_video, transcode_browser_video
from backend.services.taxon_names import localize_candidate, resolve_chinese_name
from backend.vision.pipeline import process_job

settings = get_settings()
router = APIRouter(prefix="/api/videos", tags=["videos"])
ALLOWED_VIDEO_TYPES = {
    "video/mp4",
    "video/webm",
    "video/quicktime",
    "video/x-msvideo",
    "video/x-matroska",
    "application/octet-stream",
}


def _path_url(path: Path, kind: str) -> str:
    if kind == "playback":
        return f"/media/playback/{path.name}"
    if kind == "annotated":
        return f"/media/annotated/{path.name}"
    resolved = path.resolve()
    if resolved.parent == settings.sample_video_dir.resolve():
        return f"/media/samples/{resolved.name}"
    return f"/media/uploads/{resolved.name}"


def _variant(db: Session, media_id: int, kind: str) -> MediaVariant | None:
    return db.scalar(
        select(MediaVariant).where(MediaVariant.media_id == media_id, MediaVariant.kind == kind)
    )


def _model_metadata(evidence: list) -> dict:
    for item in evidence or []:
        if isinstance(item, dict) and item.get("kind") == "model_evidence":
            return item
    return {}


def _localized_label(db: Session, item: Detection | VideoTrack) -> str:
    return resolve_chinese_name(db, item.scientific_name, item.label, item.category)


def _localized_alternatives(db: Session, alternatives: list) -> list:
    return [
        localize_candidate(db, alt) if isinstance(alt, dict) else alt
        for alt in (alternatives or [])
    ]


@router.post("/upload")
async def upload_video(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    mode: str = Form("standard"),
    targets: str = Form("animals,plants,people,fire"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    suffix = Path(file.filename or "video.mp4").suffix.lower()
    if file.content_type not in ALLOWED_VIDEO_TYPES and suffix not in {".mp4", ".webm", ".mov", ".avi", ".mkv"}:
        raise HTTPException(status_code=400, detail="仅支持 MP4、WebM、MOV、AVI、MKV 视频")
    filename = f"{uuid.uuid4().hex}{suffix or '.mp4'}"
    output = settings.upload_dir / filename
    size = 0
    with output.open("wb") as target:
        while chunk := await file.read(1024 * 1024):
            size += len(chunk)
            if size > settings.max_upload_mb * 1024 * 1024:
                target.close()
                output.unlink(missing_ok=True)
                raise HTTPException(status_code=413, detail="视频超过上传大小限制")
            target.write(chunk)
    media = MediaFile(
        owner_id=user.id,
        filename=file.filename or filename,
        stored_path=str(output),
        media_type="video",
        size_bytes=size,
    )
    db.add(media)
    db.flush()
    job = AnalysisJob(
        owner_id=user.id,
        media_id=media.id,
        status="queued",
        progress=0,
        mode=mode,
        enabled_targets=[item.strip() for item in targets.split(",") if item.strip()],
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    background_tasks.add_task(process_job, job.id)
    return {"job_id": job.id, "status": job.status, "message": "分析任务已创建"}


def _job_dict(db: Session, item: AnalysisJob) -> dict:
    original_path = Path(item.media.stored_path)
    playback = _variant(db, item.media_id, "playback")
    annotated = _variant(db, item.media_id, "annotated")
    original_url = _path_url(original_path, "original")
    needs_transcode = playback is None and original_path.parent != settings.sample_video_dir
    if playback:
        try:
            playback_probe = probe_video(Path(playback.stored_path))
            needs_transcode = playback_probe.video_codec not in {"h264", "avc1"}
        except VideoTranscodeError:
            needs_transcode = True
    playback_url = _path_url(Path(playback.stored_path), "playback") if playback and not needs_transcode else original_url
    annotated_url = _path_url(Path(annotated.stored_path), "annotated") if annotated else str((item.summary or {}).get("annotated_url") or "")
    return {
        "id": item.id,
        "status": item.status,
        "progress": item.progress,
        "mode": item.mode,
        "enabled_targets": item.enabled_targets,
        "error_message": item.error_message,
        "summary": item.summary,
        "created_at": item.created_at,
        "completed_at": item.completed_at,
        "media": {
            "id": item.media.id,
            "filename": item.media.filename,
            "url": playback_url,
            "original_url": original_url,
            "playback_url": playback_url,
            "annotated_url": annotated_url,
            "needs_transcode": needs_transcode,
            "duration_seconds": item.media.duration_seconds,
            "size_bytes": item.media.size_bytes,
        },
    }


@router.get("/jobs")
def list_jobs(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> list[dict]:
    stmt = select(AnalysisJob).order_by(AnalysisJob.id.desc())
    if user.role == "public":
        stmt = stmt.where(AnalysisJob.owner_id == user.id)
    return [_job_dict(db, item) for item in db.scalars(stmt).all()]


@router.get("/jobs/{job_id}")
def get_job(job_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    item = db.get(AnalysisJob, job_id)
    if not item or (user.role == "public" and item.owner_id != user.id):
        raise HTTPException(status_code=404, detail="任务不存在")
    return _job_dict(db, item)


@router.post("/jobs/{job_id}/repair-playback")
def repair_playback(
    job_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    job = db.get(AnalysisJob, job_id)
    if not job or (user.role == "public" and job.owner_id != user.id):
        raise HTTPException(status_code=404, detail="任务不存在")
    source = Path(job.media.stored_path)
    if not source.exists():
        raise HTTPException(status_code=404, detail="原始视频不存在")
    destination = settings.playback_dir / f"media_{job.media_id}_playback.mp4"
    try:
        probe = transcode_browser_video(source, destination)
    except VideoTranscodeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    item = _variant(db, job.media_id, "playback")
    if item:
        item.stored_path = str(destination)
        item.codec = "h264"
    else:
        db.add(MediaVariant(media_id=job.media_id, kind="playback", stored_path=str(destination), codec="h264"))
    job.media.duration_seconds = probe.duration_seconds
    db.commit()
    return {"message": "播放版本已修复", "playback_url": _path_url(destination, "playback")}


@router.get("/jobs/{job_id}/frame")
def get_job_frame(
    job_id: int,
    timestamp_ms: int = 0,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    job = db.get(AnalysisJob, job_id)
    if not job or (user.role == "public" and job.owner_id != user.id):
        raise HTTPException(status_code=404, detail="任务不存在")
    playback = _variant(db, job.media_id, "playback")
    source = Path(playback.stored_path) if playback else Path(job.media.stored_path)
    if not source.exists():
        raise HTTPException(status_code=404, detail="视频不存在")
    safe_ms = max(0, int(timestamp_ms))
    output = settings.result_dir / f"job_{job_id}_frame_{safe_ms}.jpg"
    if not output.exists():
        capture = cv2.VideoCapture(str(source))
        if not capture.isOpened():
            raise HTTPException(status_code=422, detail="无法读取视频")
        capture.set(cv2.CAP_PROP_POS_MSEC, safe_ms)
        ok, frame = capture.read()
        actual_ms = int(capture.get(cv2.CAP_PROP_POS_MSEC) or safe_ms)
        capture.release()
        if not ok:
            raise HTTPException(status_code=422, detail="无法提取指定时间的关键帧")
        if not cv2.imwrite(str(output), frame, [int(cv2.IMWRITE_JPEG_QUALITY), 90]):
            raise HTTPException(status_code=500, detail="关键帧保存失败")
    else:
        actual_ms = safe_ms
    return {"url": f"/media/results/{output.name}", "timestamp_ms": actual_ms}


@router.get("/jobs/{job_id}/detections")
def get_detections(
    job_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[dict]:
    job = db.get(AnalysisJob, job_id)
    if not job or (user.role == "public" and job.owner_id != user.id):
        raise HTTPException(status_code=404, detail="任务不存在")
    items = db.scalars(select(Detection).where(Detection.job_id == job_id).order_by(Detection.timestamp_ms)).all()
    rows = []
    for item in items:
        metadata = _model_metadata(item.evidence or [])
        rows.append(
            {
            "id": item.id,
            "track_id": item.track_id,
            "species_id": item.species_id,
            "category": item.category,
            "label": _localized_label(db, item),
            "scientific_name": item.scientific_name,
            "confidence": item.confidence,
            "timestamp_ms": item.timestamp_ms,
            "bbox": item.bbox,
            "color": item.color,
            "source": item.source,
            "behavior": item.behavior,
            "phenomenon": item.phenomenon,
            "alternatives": _localized_alternatives(db, item.alternatives or []),
            "evidence": item.evidence or [],
            "speciesnet_evidence": metadata.get("speciesnet_evidence"),
            "bioclip_evidence": metadata.get("bioclip_evidence"),
            "local_prototype_evidence": metadata.get("local_prototype_evidence"),
            "fusion_decision": metadata.get("fusion_decision"),
            "fusion_status": metadata.get("fusion_status"),
            "fusion_reason": metadata.get("fusion_reason"),
            "bioclip_top_k": _localized_alternatives(db, metadata.get("bioclip_top_k") or []),
            "bioclip_similarity": metadata.get("bioclip_similarity"),
            "bioclip_top1_margin": metadata.get("bioclip_top1_margin"),
            "prototype_image_count": metadata.get("prototype_image_count"),
            "model_warnings": metadata.get("model_warnings") or [],
            "detections": metadata.get("detections") or [],
            }
        )
    return rows


@router.get("/jobs/{job_id}/tracks")
def get_tracks(
    job_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[dict]:
    job = db.get(AnalysisJob, job_id)
    if not job or (user.role == "public" and job.owner_id != user.id):
        raise HTTPException(status_code=404, detail="任务不存在")
    tracks = db.scalars(select(VideoTrack).where(VideoTrack.job_id == job_id).order_by(VideoTrack.track_id)).all()
    if not tracks:
        detections = db.scalars(
            select(Detection).where(Detection.job_id == job_id).order_by(Detection.track_id, Detection.timestamp_ms)
        ).all()
        grouped: dict[int, list[Detection]] = {}
        for detection in detections:
            grouped.setdefault(detection.track_id, []).append(detection)
        return [
            {
                "id": -track_id,
                "detection_id": max(items, key=lambda item: item.confidence).id,
                "track_id": track_id,
                "species_id": max(items, key=lambda item: item.confidence).species_id,
                "category": max(items, key=lambda item: item.confidence).category,
                "label": _localized_label(db, max(items, key=lambda item: item.confidence)),
                "scientific_name": max(items, key=lambda item: item.confidence).scientific_name,
                "confidence": max(item.confidence for item in items),
                "color": max(items, key=lambda item: item.confidence).color,
                "start_ms": items[0].timestamp_ms,
                "end_ms": items[-1].timestamp_ms,
                "source": "legacy-detections",
                "alternatives": _localized_alternatives(db, max(items, key=lambda item: item.confidence).alternatives or []),
                "behavior": max(items, key=lambda item: item.confidence).behavior,
                "phenomenon": max(items, key=lambda item: item.confidence).phenomenon,
                "explanation": max(items, key=lambda item: item.confidence).explanation,
                "evidence": max(items, key=lambda item: item.confidence).evidence or [],
                "keyframes": [
                    {"timestamp_ms": item.timestamp_ms, "bbox": item.bbox, "confidence": item.confidence}
                    for item in items
                ],
            }
            for track_id, items in grouped.items()
        ]
    result: list[dict] = []
    for track in tracks:
        keyframes = db.scalars(
            select(TrackKeyframe)
            .where(TrackKeyframe.video_track_id == track.id)
            .order_by(TrackKeyframe.timestamp_ms)
        ).all()
        best_detection = db.scalar(
            select(Detection)
            .where(Detection.job_id == job_id, Detection.track_id == track.track_id)
            .order_by(Detection.confidence.desc())
        )
        result.append(
            {
                "id": track.id,
                "detection_id": best_detection.id if best_detection else None,
                "track_id": track.track_id,
                "species_id": track.species_id,
                "category": track.category,
                "label": _localized_label(db, best_detection or track),
                "scientific_name": track.scientific_name,
                "confidence": track.confidence,
                "color": track.color,
                "start_ms": track.start_ms,
                "end_ms": track.end_ms,
                "source": track.source,
                "alternatives": _localized_alternatives(db, track.alternatives or []),
                "behavior": best_detection.behavior if best_detection else "",
                "phenomenon": best_detection.phenomenon if best_detection else "",
                "explanation": best_detection.explanation if best_detection else "",
                "evidence": best_detection.evidence if best_detection else [],
                "keyframes": [
                    {
                        "timestamp_ms": item.timestamp_ms,
                        "bbox": item.bbox,
                        "confidence": item.confidence,
                    }
                    for item in keyframes
                ],
            }
        )
    return result


@router.get("/jobs/{job_id}/events")
def get_events(
    job_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[dict]:
    job = db.get(AnalysisJob, job_id)
    if not job or (user.role == "public" and job.owner_id != user.id):
        raise HTTPException(status_code=404, detail="任务不存在")
    events = db.scalars(select(RiskEvent).where(RiskEvent.job_id == job_id).order_by(RiskEvent.timestamp_ms)).all()
    return [
        {
            "id": item.id,
            "event_type": item.event_type,
            "title": item.title,
            "severity": item.severity,
            "status": item.status,
            "description": item.description,
            "timestamp_ms": item.timestamp_ms,
            "confidence": item.confidence,
            "ai_advice": item.ai_advice,
        }
        for item in events
    ]
