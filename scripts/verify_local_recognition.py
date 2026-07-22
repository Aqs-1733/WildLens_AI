from __future__ import annotations

import argparse
import io
import json
import os
from pathlib import Path

from fastapi.testclient import TestClient


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify local CPU recognition through the 识境 API.")
    parser.add_argument("image", type=Path)
    parser.add_argument("--expect-scientific", default="")
    parser.add_argument("--min-confidence", type=float, default=0.25)
    args = parser.parse_args()
    if not args.image.exists():
        raise SystemExit(f"Image not found: {args.image}")

    os.environ.setdefault("SPECIESNET_ENABLED", "true")
    os.environ.setdefault("SPECIESNET_API_URL", "http://127.0.0.1:8101")
    os.environ.setdefault("ARK_API_KEY", "")

    try:
        import onnxruntime as ort
    except ImportError:
        ort = None

    from backend.core.config import get_settings
    from backend.main import app

    settings = get_settings()
    species_model = Path(settings.custom_wildlife_model_path)
    if not species_model.is_absolute():
        species_model = Path(__file__).resolve().parents[1] / species_model
    classes = species_model.with_suffix(".classes.json")
    onnx_available = species_model.exists() and classes.exists()

    with TestClient(app) as client:
        login = client.post("/api/auth/login", json={"username": "explorer", "password": "Wild1234!"})
        login.raise_for_status()
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
        image_bytes = args.image.read_bytes()
        response = client.post(
            "/api/identify/photo",
            headers=headers,
            files={"file": (args.image.name, io.BytesIO(image_bytes), "image/jpeg")},
            data={"hint": "local cpu verification"},
        )
        response.raise_for_status()
        body = response.json()

    objects = body.get("objects") or []
    if not objects:
        raise SystemExit(f"No objects returned: {json.dumps(body, ensure_ascii=False)[:1000]}")
    best = max(objects, key=lambda item: float(item.get("confidence") or 0.0))
    if float(best.get("confidence") or 0.0) < args.min_confidence:
        raise SystemExit(f"Best confidence below threshold: {best}")
    if args.expect_scientific:
        expected = args.expect_scientific.lower()
        matches = [
            item
            for item in objects
            if str(item.get("scientific_name") or "").lower() == expected
            or str((item.get("speciesnet_evidence") or {}).get("scientific_name") or "").lower()
            == expected
        ]
        if not matches:
            raise SystemExit(
                f"Expected {args.expect_scientific}, got "
                f"{[item.get('scientific_name') for item in objects]}: {best}"
            )
        best = max(matches, key=lambda item: float(item.get("confidence") or 0.0))
    print(
        json.dumps(
            {
                "onnxruntime_providers": ort.get_available_providers() if ort else [],
                "speciesnet_enabled": settings.speciesnet_enabled,
                "speciesnet_api_url": settings.speciesnet_api_url,
                "model": str(species_model),
                "classes": str(classes),
                "onnx_available": onnx_available,
                "model_mode": body.get("model_mode"),
                "warnings": body.get("warnings") or [],
                "best": best,
                "objects": len(objects),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
