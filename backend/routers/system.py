from __future__ import annotations

import json
import shutil
import sqlite3
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.core.config import PROJECT_ROOT, get_settings
from backend.core.database import get_db
from backend.deps import get_current_user, require_regulator
from backend.models import AnalysisJob, Detection, MediaFile, ReviewResult, RiskEvent, Species, User
from backend.vision.active_learning_memory import active_learning_memory
from backend.vision.bioclip_classifier import bioclip_classifier

router = APIRouter(prefix="/api/system", tags=["system"])
settings = get_settings()


def _load_json(path: Path, fallback):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return fallback


def _path_state(path: Path) -> dict[str, Any]:
    return {
        "path": str(path),
        "exists": path.exists(),
        "is_file": path.is_file(),
        "is_dir": path.is_dir(),
    }


def _dir_size(path: Path, max_files: int = 8000) -> dict[str, Any]:
    if not path.exists():
        return {"path": str(path), "exists": False, "files": 0, "bytes": 0, "truncated": False}
    total = 0
    files = 0
    truncated = False
    for item in path.rglob("*"):
        if item.is_file():
            files += 1
            total += item.stat().st_size
            if files >= max_files:
                truncated = True
                break
    return {"path": str(path), "exists": True, "files": files, "bytes": total, "truncated": truncated}


def _sqlite_readonly_status(path: Path) -> dict[str, Any]:
    state: dict[str, Any] = {"path": str(path), "exists": path.exists(), "tables": [], "counts": {}, "error": None}
    if not path.exists():
        return state
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=2)
        conn.execute("PRAGMA query_only=ON")
        tables = [
            row[0]
            for row in conn.execute(
                "select name from sqlite_master where type='table' and name not like 'sqlite_%' order by name"
            ).fetchall()
        ]
        state["tables"] = tables
        for table in tables[:30]:
            try:
                state["counts"][table] = conn.execute(f'select count(*) from "{table}"').fetchone()[0]
            except sqlite3.Error as exc:
                state["counts"][table] = f"unavailable: {exc}"
        conn.close()
    except sqlite3.Error as exc:
        state["error"] = str(exc)
    return state


def _cuda_status() -> dict[str, Any]:
    try:
        import torch  # type: ignore

        return {
            "available": bool(torch.cuda.is_available()),
            "device_count": int(torch.cuda.device_count()) if torch.cuda.is_available() else 0,
        }
    except Exception as exc:  # noqa: BLE001
        return {"available": False, "device_count": 0, "error": f"torch unavailable: {exc}"}


def _process_status() -> list[dict[str, Any]]:
    names = ("download_global_species_images.py", "learn_species_prototypes_continuously.py")
    try:
        import psutil  # type: ignore
    except Exception:
        return []
    processes: list[dict[str, Any]] = []
    for process in psutil.process_iter(["pid", "name", "cmdline", "create_time", "status"]):
        try:
            command = " ".join(process.info.get("cmdline") or [])
        except (psutil.Error, TypeError):
            continue
        if any(name in command for name in names):
            processes.append(
                {
                    "pid": process.info.get("pid"),
                    "name": process.info.get("name"),
                    "status": process.info.get("status"),
                    "command": command,
                    "create_time": process.info.get("create_time"),
                }
            )
    return processes


def _model_rows() -> list[dict]:
    active = _load_json(settings.active_model_config, {})
    bioclip_status = bioclip_classifier.status()
    configured = [
        {
            "name": "当前正式物种模型",
            "engine": active.get("active_species_model") or "未发布",
            "purpose": "本地细粒度物种识别与复核主模型",
            "status": "ready" if active.get("active_species_model") and Path(active["active_species_model"]).exists() else "not-published",
            "metric": "随模型版本登记",
            "latency": "随模型版本登记",
            "path": active.get("active_species_model") or str(settings.active_model_config),
        },
        {
            "name": "物种视觉原型库",
            "engine": "species_visual_embeddings.sqlite",
            "purpose": "正式模型缺失时进行原型相似度检索",
            "status": "ready" if settings.species_embedding_db_path.exists() else "missing",
            "metric": "只读检索",
            "latency": "SQLite只读",
            "path": str(settings.species_embedding_db_path),
        },
        {
            "name": "BioCLIP开放词表回退",
            "engine": active.get("fallback_model") or "hf-hub:imageomics/bioclip",
            "purpose": "开放词表图像向量和物种候选校正",
            "status": "configured" if active.get("fallback_model") else "not-configured",
            "metric": "外部权重加载后评估",
            "latency": "取决于本地/远端权重",
            "path": str(settings.model_registry_dir),
        },
        {
            "name": "BioCLIP 400721 local visual prototypes",
            "engine": settings.bioclip_model_id,
            "purpose": "Offline 512-d image embedding search over the compact local prototype database",
            "status": "ready" if bioclip_status.get("available") else "disabled" if not settings.bioclip_enabled else "missing",
            "metric": f"dim={settings.bioclip_embedding_dim}, prototypes={bioclip_status.get('prototype_count', 0)}",
            "latency": f"device={settings.bioclip_device}, batch={settings.bioclip_batch_size}",
            "path": str(settings.bioclip_prototype_db_path),
        },
        {
            "name": "SpeciesNet animal specialist",
            "engine": settings.speciesnet_model_name,
            "purpose": "Animal, human and vehicle detection plus common wildlife classification",
            "status": "configured" if settings.speciesnet_enabled else "disabled",
            "metric": f"min={settings.speciesnet_min_score}, strong={settings.speciesnet_strong_score}",
            "latency": f"HTTP timeout {settings.speciesnet_timeout_seconds}s",
            "path": settings.speciesnet_api_url,
        },
        {
            "name": "全球分类文本索引",
            "engine": "global_species_index",
            "purpose": "属级、科级、文本分类学回退",
            "status": "ready" if settings.global_species_index_path.exists() else "missing",
            "metric": "索引覆盖度",
            "latency": "本地文件检索",
            "path": str(settings.global_species_index_path),
        },
        {
            "name": "本地候选区域检测",
            "engine": "OpenCV MOG2 + HSV segmentation",
            "purpose": "离线演示和模型缺失时的候选框生成",
            "status": "active",
            "metric": "启发式模式",
            "latency": "设备相关",
            "path": "backend/vision/pipeline.py",
        },
        {
            "name": "ARK多模态复核",
            "engine": settings.ark_model,
            "purpose": "对有限数量关键裁剪图进行物种/目标辅助分类",
            "status": "active" if settings.ark_api_key else "not-configured",
            "metric": "人工复核优先",
            "latency": "网络相关",
            "path": "ARK Responses API",
        },
        {
            "name": "野生动物检测模型",
            "engine": "MegaDetector / YOLO ONNX",
            "purpose": "动物、人员、车辆候选框",
            "status": "ready" if Path(settings.yolo_model_path).exists() else "optional-model-missing",
            "metric": "安装模型后评估",
            "latency": "安装模型后评估",
            "path": settings.yolo_model_path,
        },
        {
            "name": "本地物种分类模型",
            "engine": "SpeciesNet / custom ONNX",
            "purpose": "目标裁剪图物种级分类",
            "status": "ready" if Path(settings.custom_wildlife_model_path).exists() else "optional-model-missing",
            "metric": "安装模型后评估",
            "latency": "安装模型后评估",
            "path": settings.custom_wildlife_model_path,
        },
        {
            "name": "动物行为模型",
            "engine": "VideoMAE / custom ONNX",
            "purpose": "行走、奔跑、进食、休息、警戒等时序行为分类",
            "status": "ready" if Path(settings.behavior_model_path).exists() else "train-required",
            "metric": "安装模型后评估Macro-F1",
            "latency": "安装模型后评估",
            "path": settings.behavior_model_path,
        },
        {
            "name": "自然现象模型",
            "engine": "EfficientNet-V2 multi-label ONNX",
            "purpose": "雨雪雾、彩虹、闪电、日晕、极光、烟火等场景分类",
            "status": "ready" if Path(settings.phenomena_model_path).exists() else "train-required",
            "metric": "安装模型后评估Macro-F1与风险类Recall",
            "latency": "安装模型后评估",
            "path": settings.phenomena_model_path,
        },
    ]
    return configured


@router.get("/status")
def system_status(
    db: Session = Depends(get_db), _: User = Depends(get_current_user)
) -> dict[str, Any]:
    return {
        "app": settings.app_name,
        "environment": settings.app_env,
        "database_url": settings.effective_database_url,
        "vision_mode": settings.vision_mode,
        "ark_enabled": bool(settings.ark_api_key),
        "bioclip": bioclip_classifier.status(),
        "active_learning": active_learning_memory.status(),
        "counts": {
            "users": db.scalar(select(func.count(User.id))) or 0,
            "media_files": db.scalar(select(func.count(MediaFile.id))) or 0,
            "analysis_jobs": db.scalar(select(func.count(AnalysisJob.id))) or 0,
            "detections": db.scalar(select(func.count(Detection.id))) or 0,
            "species": db.scalar(select(func.count(Species.id))) or 0,
            "risk_events": db.scalar(select(func.count(RiskEvent.id))) or 0,
            "review_results": db.scalar(select(func.count(ReviewResult.id))) or 0,
        },
        "paths": {
            "upload_dir": _path_state(settings.upload_dir),
            "output_media_dir": _path_state(settings.output_media_dir),
            "report_output_dir": _path_state(settings.report_dir),
            "sample_media_dir": _path_state(settings.sample_video_dir),
        },
    }


@router.get("/data-status")
def data_status(_: User = Depends(require_regulator)) -> dict[str, Any]:
    queue = _sqlite_readonly_status(settings.species_queue_db_path)
    embeddings = _sqlite_readonly_status(settings.species_embedding_db_path)
    image_root = _path_state(settings.species_image_root)
    return {
        "business_database": _sqlite_readonly_status(settings.wildlens_db_path),
        "species_queue_database": queue,
        "species_embedding_database": embeddings,
        "global_species_index": _path_state(settings.global_species_index_path),
        "species_image_root": image_root,
        "inat_dwca": _path_state(settings.inat_dwca_path),
        "catalogue_of_life": _path_state(settings.catalogue_of_life_path),
        "notes": [
            "训练库通过SQLite只读连接读取，并设置短超时。",
            "图片目录不会在Web状态接口中递归扫描大型外部数据集。",
        ],
    }


@router.get("/training-status")
def training_status(_: User = Depends(require_regulator)) -> dict[str, Any]:
    return {
        "running_processes": _process_status(),
        "queue_database": _sqlite_readonly_status(settings.species_queue_db_path),
        "embedding_database": _sqlite_readonly_status(settings.species_embedding_db_path),
        "model_checkpoint_dir": _path_state(settings.model_checkpoint_dir),
        "policy": "Web应用只读展示训练状态，不启动或停止下载与持续学习任务。",
    }


@router.get("/model-status")
def model_status(_: User = Depends(require_regulator)) -> dict[str, Any]:
    active = _load_json(settings.active_model_config, {})
    return {
        "active_model_config": active,
        "active_model_config_path": str(settings.active_model_config),
        "cuda": _cuda_status(),
        "models": _model_rows(),
    }


@router.get("/storage-status")
def storage_status(_: User = Depends(require_regulator)) -> dict[str, Any]:
    usage = shutil.disk_usage(PROJECT_ROOT)
    return {
        "project_root": str(PROJECT_ROOT),
        "disk": {"total": usage.total, "used": usage.used, "free": usage.free},
        "directories": {
            "uploads": _dir_size(settings.upload_dir),
            "results": _dir_size(settings.result_dir),
            "annotated": _dir_size(settings.annotated_dir),
            "playback": _dir_size(settings.playback_dir),
            "reports": _dir_size(settings.report_dir),
            "logs": _dir_size(settings.logs_dir),
            "models_registry": _dir_size(settings.model_registry_dir),
            "checkpoints": _dir_size(settings.model_checkpoint_dir),
        },
    }


@router.get("/models")
def model_registry(_: User = Depends(require_regulator)) -> list[dict]:
    return _model_rows()


@router.get("/datasets")
def dataset_registry(_: User = Depends(require_regulator)) -> list[dict]:
    path = PROJECT_ROOT / "data" / "manifests" / "dataset_sources.json"
    return _load_json(path, [])
