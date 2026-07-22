from __future__ import annotations

from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfgen import canvas
from sqlalchemy.orm import Session

from backend.core.config import get_settings
from backend.models import AnalysisJob, Detection, RiskEvent

settings = get_settings()


def create_job_report(db: Session, job_id: int) -> Path:
    job = db.get(AnalysisJob, job_id)
    if not job:
        raise ValueError("任务不存在")
    detections = db.query(Detection).filter(Detection.job_id == job_id).all()
    events = db.query(RiskEvent).filter(RiskEvent.job_id == job_id).all()
    output = settings.report_dir / f"analysis-job-{job_id}.pdf"
    try:
        pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
        body_font = "STSong-Light"
    except Exception:
        body_font = "Helvetica"
    pdf = canvas.Canvas(str(output), pagesize=A4)
    width, height = A4
    y = height - 55
    pdf.setTitle(f"识境分析报告 #{job.id}")
    pdf.setFont(body_font, 18)
    pdf.drawString(48, y, "识境视频分析报告")
    y -= 32
    pdf.setFont(body_font, 10)
    lines = [
        f"任务编号：{job.id}",
        f"媒体文件：{job.media.filename}",
        f"状态：{job.status}",
        f"检测记录：{len(detections)}",
        f"风险事件：{len(events)}",
        f"摘要：{str(job.summary)[:420]}",
    ]
    for line in lines:
        pdf.drawString(48, y, line)
        y -= 18
    y -= 10
    pdf.setFont(body_font, 12)
    pdf.drawString(48, y, "主要观察")
    y -= 20
    pdf.setFont(body_font, 9)
    for item in detections[:25]:
        label = f"{item.timestamp_ms/1000:.1f}秒  {item.label} / {item.scientific_name}  {item.confidence:.0%}"
        pdf.drawString(55, y, label[:95])
        y -= 15
        if y < 70:
            pdf.showPage()
            pdf.setFont(body_font, 9)
            y = height - 55
    if events:
        y -= 8
        pdf.setFont(body_font, 12)
        pdf.drawString(48, y, "风险与复核")
        y -= 18
        pdf.setFont(body_font, 9)
        for event in events[:15]:
            pdf.drawString(55, y, f"{event.severity}｜{event.title}｜{event.status}"[:95])
            y -= 15
    pdf.save()
    return output
