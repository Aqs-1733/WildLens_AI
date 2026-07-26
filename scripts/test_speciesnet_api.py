from __future__ import annotations

import argparse
import sys
from pathlib import Path

import httpx


def main() -> int:
    parser = argparse.ArgumentParser(description="Check the local SpeciesNet API with a real image.")
    parser.add_argument("--url", default="http://127.0.0.1:8101")
    parser.add_argument("--image", default="/root/autodl-tmp/test_images/tiger.jpg")
    parser.add_argument("--expect", default="panthera tigris")
    parser.add_argument("--top-k", type=int, default=5)
    args = parser.parse_args()

    image = Path(args.image)
    if not image.exists():
        print(f"Image not found: {image}", file=sys.stderr)
        return 2

    with httpx.Client(timeout=httpx.Timeout(180.0, connect=10.0)) as client:
        health = client.get(f"{args.url.rstrip('/')}/health")
        health.raise_for_status()
        health_json = health.json()
        print("health:", health_json)
        if not health_json.get("model_loaded"):
            print("SpeciesNet model is not loaded", file=sys.stderr)
            return 3

        with image.open("rb") as handle:
            response = client.post(
                f"{args.url.rstrip('/')}/predict/upload",
                files={"file": (image.name, handle, "image/jpeg")},
                data={"top_k": str(args.top_k)},
            )
        response.raise_for_status()
        payload = response.json()
        print("prediction:", payload.get("result"))
        scientific_name = str((payload.get("result") or {}).get("scientific_name") or "").lower()
        if scientific_name != args.expect.lower():
            print(
                f"Expected {args.expect!r}, got {scientific_name!r}",
                file=sys.stderr,
            )
            return 4
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

