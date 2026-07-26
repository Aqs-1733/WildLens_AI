from __future__ import annotations

import argparse
import cgi
import importlib.metadata
import json
import os
import tempfile
import threading
import time
from hashlib import sha256
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CACHE = PROJECT_ROOT / "models" / "speciesnet_offline"
os.environ.setdefault("KAGGLEHUB_CACHE", str(DEFAULT_CACHE))
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "-1")

from backend.vision.species_fusion import normalize_speciesnet_response  # noqa: E402

MODEL_NAME = os.getenv("SPECIESNET_MODEL_NAME", "kaggle:google/speciesnet/pyTorch/v4.0.3a/1")
MODEL_VERSION = os.getenv("SPECIESNET_MODEL_VERSION", "4.0.3a")
MAX_IMAGE_MB = int(os.getenv("SPECIESNET_MAX_IMAGE_MB", "25"))
CACHE_ENABLED = os.getenv("SPECIESNET_CACHE_ENABLED", "true").lower() in {"1", "true", "yes", "on"}
CACHE_DIR = Path(os.getenv("SPECIESNET_CACHE_DIR", PROJECT_ROOT / "storage" / "speciesnet_cache")).resolve()
ALLOWED_MIME_TYPES = {"image/jpeg", "image/png", "image/webp", "application/octet-stream"}
SUFFIX_BY_MIME = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}

_model: Any | None = None
_model_error: str | None = None
_model_lock = threading.Lock()
_predict_lock = threading.Lock()


def _json_atomic_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def _cache_path(image_bytes: bytes, country: str, top_k: int) -> Path:
    digest = sha256()
    digest.update(image_bytes)
    digest.update(country.upper().encode("utf-8"))
    digest.update(str(top_k).encode("ascii"))
    return CACHE_DIR / f"{digest.hexdigest()}.json"


def _suffix_for(filename: str, content_type: str) -> str:
    suffix = Path(filename or "").suffix.lower()
    if suffix in {".jpg", ".jpeg", ".png", ".webp"}:
        return ".jpg" if suffix == ".jpeg" else suffix
    return SUFFIX_BY_MIME.get(content_type, ".jpg")


def _load_model() -> Any:
    global _model, _model_error
    if _model is not None:
        return _model
    with _model_lock:
        if _model is not None:
            return _model
        try:
            from speciesnet import SpeciesNet  # type: ignore

            _model = SpeciesNet(MODEL_NAME, components="all", geofence=True, multiprocessing=False)
            _model_error = None
            return _model
        except Exception as exc:  # noqa: BLE001
            _model_error = str(exc)
            raise


def _runtime_status() -> dict[str, Any]:
    try:
        import speciesnet  # type: ignore
    except Exception:
        speciesnet_version = ""
    else:
        speciesnet_version = str(getattr(speciesnet, "__version__", ""))
    if not speciesnet_version:
        try:
            speciesnet_version = importlib.metadata.version("speciesnet")
        except importlib.metadata.PackageNotFoundError:
            speciesnet_version = ""
    try:
        import torch  # type: ignore

        cuda_available = bool(torch.cuda.is_available())
        torch_version = str(torch.__version__)
        gpu = torch.cuda.get_device_name(0) if cuda_available else ""
    except Exception as exc:  # noqa: BLE001
        cuda_available = False
        torch_version = ""
        gpu = ""
        torch_error = str(exc)
    else:
        torch_error = ""
    return {
        "speciesnet_version": speciesnet_version,
        "torch_version": torch_version,
        "cuda_available": cuda_available,
        "gpu": gpu,
        "torch_error": torch_error,
    }


def health_payload() -> dict[str, Any]:
    runtime = _runtime_status()
    return {
        "status": "ready" if _model is not None and _model_error is None else "error",
        "model_loaded": _model is not None,
        "model_version": MODEL_VERSION,
        "model_name": MODEL_NAME,
        "cache_enabled": CACHE_ENABLED,
        "cache_dir": str(CACHE_DIR),
        "kagglehub_cache": os.getenv("KAGGLEHUB_CACHE", ""),
        "cuda_visible_devices": os.getenv("CUDA_VISIBLE_DEVICES", ""),
        "error": _model_error,
        **runtime,
    }


def predict_image_bytes(
    image_bytes: bytes,
    *,
    filename: str = "image.jpg",
    content_type: str = "image/jpeg",
    country: str = "",
    top_k: int = 5,
) -> dict[str, Any]:
    if not image_bytes:
        raise ValueError("Empty image")
    if len(image_bytes) > MAX_IMAGE_MB * 1024 * 1024:
        raise ValueError(f"Image exceeds {MAX_IMAGE_MB} MB")
    if content_type not in ALLOWED_MIME_TYPES:
        raise ValueError("Only JPEG, PNG and WebP images are supported")

    safe_top_k = max(1, min(int(top_k or 5), 20))
    country_code = country.strip().upper()
    cache_path = _cache_path(image_bytes, country_code, safe_top_k)
    if CACHE_ENABLED and cache_path.exists():
        cached = json.loads(cache_path.read_text(encoding="utf-8"))
        cached["cached"] = True
        return cached

    model = _load_model()
    started = time.perf_counter()
    temp_path = ""
    try:
        with tempfile.NamedTemporaryFile(
            prefix="speciesnet_",
            suffix=_suffix_for(filename, content_type),
            delete=False,
        ) as temp:
            temp.write(image_bytes)
            temp_path = temp.name
        with _predict_lock:
            raw = model.predict(
                filepaths=[temp_path],
                country=country_code or None,
                run_mode="single_thread",
                batch_size=1,
                progress_bars=False,
            )
    finally:
        if temp_path:
            Path(temp_path).unlink(missing_ok=True)

    if not isinstance(raw, dict):
        raise RuntimeError("SpeciesNet returned an invalid response")
    result = normalize_speciesnet_response(raw, top_k=safe_top_k)
    if not result:
        raise RuntimeError("SpeciesNet returned no predictions")

    sanitized_raw = dict(raw)
    predictions = []
    for item in list(raw.get("predictions") or []):
        if isinstance(item, dict):
            clone = dict(item)
            clone.pop("filepath", None)
            predictions.append(clone)
    sanitized_raw["predictions"] = predictions
    response = {
        "ok": True,
        "cached": False,
        "latency_ms": round((time.perf_counter() - started) * 1000, 3),
        "result": result,
        "raw": sanitized_raw,
    }
    if CACHE_ENABLED:
        _json_atomic_write(cache_path, response)
    return response


class SpeciesNetHandler(BaseHTTPRequestHandler):
    server_version = "WildLensSpeciesNetCPU/1.0"

    def _write_json(self, status: int, payload: dict[str, Any]) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path == "/health":
            self._write_json(200, health_payload())
            return
        self._write_json(404, {"ok": False, "detail": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path != "/predict/upload":
            self._write_json(404, {"ok": False, "detail": "not found"})
            return
        content_length = int(self.headers.get("Content-Length") or "0")
        if content_length > MAX_IMAGE_MB * 1024 * 1024 + 1_000_000:
            self._write_json(413, {"ok": False, "detail": f"Image exceeds {MAX_IMAGE_MB} MB"})
            return
        content_type = self.headers.get("Content-Type", "")
        if not content_type.lower().startswith("multipart/form-data"):
            self._write_json(415, {"ok": False, "detail": "multipart/form-data required"})
            return
        try:
            form = cgi.FieldStorage(
                fp=self.rfile,
                headers=self.headers,
                environ={
                    "REQUEST_METHOD": "POST",
                    "CONTENT_TYPE": content_type,
                    "CONTENT_LENGTH": str(content_length),
                },
            )
            file_item = form["file"] if "file" in form else None
            if file_item is None or not getattr(file_item, "file", None):
                self._write_json(400, {"ok": False, "detail": "file field is required"})
                return
            image_bytes = file_item.file.read(MAX_IMAGE_MB * 1024 * 1024 + 1)
            payload = predict_image_bytes(
                image_bytes,
                filename=str(getattr(file_item, "filename", "") or "image.jpg"),
                content_type=str(getattr(file_item, "type", "") or "application/octet-stream"),
                country=str(form.getvalue("country") or ""),
                top_k=int(form.getvalue("top_k") or 5),
            )
        except Exception as exc:  # noqa: BLE001
            self._write_json(500, {"ok": False, "detail": str(exc), "health": health_payload()})
            return
        self._write_json(200, payload)

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        print(f"{timestamp} | {self.address_string()} | {format % args}", flush=True)


def run_server(host: str, port: int) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        _load_model()
    except Exception as exc:  # noqa: BLE001
        print(f"SpeciesNet model failed to load: {exc}", flush=True)
    server = ThreadingHTTPServer((host, port), SpeciesNetHandler)
    print(
        f"WildLens SpeciesNet CPU service listening on http://{host}:{port} "
        f"status={health_payload()['status']}",
        flush=True,
    )
    server.serve_forever()


try:
    from fastapi import FastAPI, File, Form, HTTPException, UploadFile
except ImportError:
    app = None
else:
    app = FastAPI(title="WildLens SpeciesNet CPU API", version=MODEL_VERSION)

    @app.on_event("startup")
    def warmup() -> None:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        try:
            _load_model()
        except Exception:
            return

    @app.get("/health")
    def health() -> dict[str, Any]:
        return health_payload()

    @app.post("/predict/upload")
    async def predict_upload(
        file: UploadFile = File(...),
        country: str = Form(default=""),
        top_k: int = Form(default=5),
    ) -> dict[str, Any]:
        try:
            image_bytes = await file.read(MAX_IMAGE_MB * 1024 * 1024 + 1)
            return predict_image_bytes(
                image_bytes,
                filename=file.filename or "image.jpg",
                content_type=file.content_type or "application/octet-stream",
                country=country,
                top_k=top_k,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=500, detail=str(exc)) from exc


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the WildLens SpeciesNet CPU HTTP service.")
    parser.add_argument("--host", default=os.getenv("SPECIESNET_API_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("SPECIESNET_API_PORT", "8101")))
    args = parser.parse_args()
    run_server(args.host, args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
