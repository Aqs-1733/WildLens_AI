from __future__ import annotations

import asyncio
import logging
import time

from sqlalchemy import select

from backend.core.config import get_settings
from backend.core.database import Base, SessionLocal, engine
from backend.models import AnalysisJob
from backend.seed import seed_database
from backend.vision.pipeline import process_job

settings = get_settings()
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | worker | %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(settings.logs_dir / "worker.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("wildlens.worker")


def bootstrap() -> None:
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        seed_database(db)


def next_queued_job() -> int | None:
    with SessionLocal() as db:
        job = db.scalar(
            select(AnalysisJob)
            .where(AnalysisJob.status == "queued", AnalysisJob.media.has(media_type="video"))
            .order_by(AnalysisJob.id)
        )
        return job.id if job else None


async def run_forever(interval_seconds: float = 2.0) -> None:
    bootstrap()
    logger.info("worker_started interval_seconds=%s", interval_seconds)
    while True:
        job_id = next_queued_job()
        if job_id is None:
            await asyncio.sleep(interval_seconds)
            continue
        started = time.perf_counter()
        logger.info("job_started job_id=%s", job_id)
        await process_job(job_id)
        logger.info("job_finished job_id=%s duration=%.2f", job_id, time.perf_counter() - started)


if __name__ == "__main__":
    asyncio.run(run_forever())
