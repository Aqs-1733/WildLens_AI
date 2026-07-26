from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from backend.core.database import get_db
from backend.deps import get_current_user
from backend.models import AnalysisJob, Report, User
from backend.services.reports import create_job_report

router = APIRouter(prefix="/api/reports", tags=["reports"])


@router.get("/jobs/{job_id}")
def download_job_report(
    job_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    job = db.get(AnalysisJob, job_id)
    if not job or (user.role == "public" and job.owner_id != user.id):
        raise HTTPException(status_code=404, detail="任务不存在")
    path = create_job_report(db, job_id)
    existing = db.query(Report).filter(Report.job_id == job_id, Report.owner_id == user.id).first()
    if existing:
        existing.stored_path = str(path)
        existing.summary = job.summary or {}
    else:
        db.add(
            Report(
                job_id=job_id,
                owner_id=user.id,
                title=f"识境分析报告 #{job_id}",
                stored_path=str(path),
                summary=job.summary or {},
            )
        )
    db.commit()
    return FileResponse(path, filename=f"shijing-report-{job_id}.pdf")
