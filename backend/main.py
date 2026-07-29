from __future__ import annotations

import sys
from pathlib import Path

# Allow `python backend/main.py` from the project root as documented.
PROJECT_DIR = Path(__file__).resolve().parents[1]
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

import json
import logging
import re
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime

import uvicorn
from fastapi import FastAPI, Request
from fastapi.encoders import ENCODERS_BY_TYPE
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles

from backend.core.config import get_settings
from backend.core.database import Base, SessionLocal, engine
from backend.core.time_utils import beijing_isoformat
from backend.routers import alerts, auth, compat, dashboard, identify, qa, reports, review, social, species, system, videos
from backend.seed import seed_database
from backend.vision.bioclip_classifier import bioclip_classifier

settings = get_settings()
ENCODERS_BY_TYPE[datetime] = beijing_isoformat
ISO_NAIVE_DATETIME = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?$")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(settings.logs_dir / "backend.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("wildlens.api")


def _normalize_datetime_strings(value):
    if isinstance(value, str) and ISO_NAIVE_DATETIME.match(value):
        return beijing_isoformat(datetime.fromisoformat(value))
    if isinstance(value, list):
        return [_normalize_datetime_strings(item) for item in value]
    if isinstance(value, dict):
        return {key: _normalize_datetime_strings(item) for key, item in value.items()}
    return value


async def _with_beijing_json_datetimes(response: Response) -> Response:
    if response.status_code in {204, 304}:
        return response
    content_type = response.headers.get("content-type", "")
    if not content_type.startswith("application/json"):
        return response
    body = b"".join([chunk async for chunk in response.body_iterator])
    if not body:
        return response
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return Response(
            content=body,
            status_code=response.status_code,
            headers=dict(response.headers),
            media_type=response.media_type,
            background=response.background,
        )
    headers = dict(response.headers)
    headers.pop("content-length", None)
    return Response(
        content=json.dumps(
            _normalize_datetime_strings(payload),
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8"),
        status_code=response.status_code,
        headers=headers,
        media_type="application/json",
        background=response.background,
    )


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        seed_database(db)
    if settings.bioclip_preload_model:
        bioclip_classifier.preload_model(background=True)
    if settings.bioclip_preload_index:
        bioclip_classifier.preload_index(background=True)
    yield


app = FastAPI(
    title="识境 API",
    description="识境：本地优先的自然观察识别、风险预警与智能科普平台",
    version="2.0.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        logger.exception(
            "request_failed request_id=%s method=%s path=%s",
            request_id,
            request.method,
            request.url.path,
        )
        raise
    response = await _with_beijing_json_datetimes(response)
    duration_ms = round((time.perf_counter() - started) * 1000, 2)
    response.headers["X-Request-ID"] = request_id
    logger.info(
        "request_completed request_id=%s method=%s path=%s status=%s duration_ms=%s",
        request_id,
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
    )
    return response


app.mount("/media/uploads", StaticFiles(directory=settings.upload_dir), name="uploads")
app.mount("/media/results", StaticFiles(directory=settings.result_dir), name="results")
app.mount("/media/reports", StaticFiles(directory=settings.report_dir), name="reports")
app.mount("/media/annotated", StaticFiles(directory=settings.annotated_dir), name="annotated")
app.mount("/media/playback", StaticFiles(directory=settings.playback_dir), name="playback")
app.mount("/media/samples", StaticFiles(directory=settings.sample_video_dir), name="samples")

for router in (
    auth.router,
    dashboard.router,
    species.router,
    identify.router,
    social.router,
    videos.router,
    alerts.router,
    qa.router,
    reports.router,
    review.router,
    system.router,
    compat.router,
):
    app.include_router(router)


@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "app": settings.app_name,
        "environment": settings.app_env,
        "vision_mode": settings.vision_mode,
        "ark_enabled": bool(settings.ark_api_key),
    }


if __name__ == "__main__":
    uvicorn.run("backend.main:app", host=settings.app_host, port=settings.app_port, reload=False)
