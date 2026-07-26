from __future__ import annotations

import argparse
import csv
import json
import os
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

import cv2

from backend.vision.object_detector import LocalObjectDetector


def json_request(url: str, payload: dict, token: str = "") -> dict:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(
        url, data=json.dumps(payload).encode(), headers=headers, method="POST"
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)


def upload(url: str, path: Path, token: str) -> dict:
    boundary = "----WildLensAcceptance" + uuid.uuid4().hex
    parts: list[bytes] = []
    for name, value in {"hint": "独立验收样本", "address": ""}.items():
        parts.extend(
            [
                f"--{boundary}\r\n".encode(),
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(),
                value.encode("utf-8"),
                b"\r\n",
            ]
        )
    parts.extend(
        [
            f"--{boundary}\r\n".encode(),
            f'Content-Disposition: form-data; name="file"; filename="{path.name}"\r\n'.encode(),
            b"Content-Type: image/jpeg\r\n\r\n",
            path.read_bytes(),
            b"\r\n",
            f"--{boundary}--\r\n".encode(),
        ]
    )
    request = urllib.request.Request(
        url,
        data=b"".join(parts),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=240) as response:
        return json.load(response)


def obtain_token(base: str, username: str, password: str) -> str:
    try:
        return json_request(
            base + "/api/auth/login", {"username": username, "password": password}
        )["access_token"]
    except urllib.error.HTTPError as exc:
        if exc.code != 401:
            raise
    return json_request(
        base + "/api/auth/register",
        {
            "username": username,
            "email": username + "@example.com",
            "password": password,
            "display_name": "YOLO26s Acceptance",
            "role": "public",
            "invite_code": "",
        },
    )["access_token"]


def passed(expected: str, categories: list[str]) -> bool:
    if expected == "negative":
        return not any(item in {"mammal", "bird"} for item in categories)
    return expected in categories


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:8010")
    args = parser.parse_args()
    project = args.project.resolve()
    root = project / "data" / "acceptance" / "real_world_v1"
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    model_path = project / "models" / "trained" / "wildlens_yolo26s_mammal_bird_v3.onnx"
    detector = LocalObjectDetector(str(model_path), confidence=0.35)
    if not detector.available:
        raise RuntimeError(f"YOLO unavailable: {detector.error}")
    username = "wildlens_acceptance_20260723"
    password = os.environ.get("WILDLENS_ACCEPTANCE_PASSWORD", "WildLens-Acceptance-2026!")
    token = obtain_token(args.base_url, username, password)
    results: list[dict] = []
    for index, sample in enumerate(manifest, 1):
        path = root / sample["local_path"]
        image = cv2.imread(str(path))
        started = time.perf_counter()
        direct = detector.detect(image)
        yolo_seconds = time.perf_counter() - started
        yolo_categories = [item.category for item in direct]
        api_started = time.perf_counter()
        error = ""
        response: dict = {}
        try:
            response = upload(args.base_url + "/api/identify/photo", path, token)
        except Exception as exc:
            error = str(exc)
        api_seconds = time.perf_counter() - api_started
        web_categories = [str(item.get("category", "")) for item in response.get("objects", [])]
        row = {
            "sample_id": sample["sample_id"],
            "expected": sample["expected"],
            "local_path": sample["local_path"],
            "page_url": sample["page_url"],
            "yolo_pass": passed(sample["expected"], yolo_categories),
            "yolo_categories": "|".join(yolo_categories),
            "yolo_confidences": "|".join(f"{item.confidence:.4f}" for item in direct),
            "yolo_boxes": json.dumps([item.bbox for item in direct]),
            "yolo_seconds": round(yolo_seconds, 4),
            "web_pass": passed(sample["expected"], web_categories) if not error else False,
            "web_categories": "|".join(web_categories),
            "web_labels": "|".join(str(item.get("label", "")) for item in response.get("objects", [])),
            "web_confidences": "|".join(
                f"{float(item.get('confidence', 0)):.4f}" for item in response.get("objects", [])
            ),
            "web_seconds": round(api_seconds, 4),
            "model_mode": response.get("model_mode", ""),
            "job_id": response.get("job_id", ""),
            "error": error,
        }
        results.append(row)
        print(
            f"[{index:02d}/{len(manifest)}] {sample['sample_id']} "
            f"YOLO={'PASS' if row['yolo_pass'] else 'FAIL'} "
            f"WEB={'PASS' if row['web_pass'] else 'FAIL'} {api_seconds:.1f}s",
            flush=True,
        )
    with (root / "results.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(results[0]))
        writer.writeheader()
        writer.writerows(results)
    summary = {
        "model": str(model_path),
        "total": len(results),
        "yolo_pass": sum(bool(row["yolo_pass"]) for row in results),
        "web_pass": sum(bool(row["web_pass"]) for row in results),
        "api_errors": sum(bool(row["error"]) for row in results),
        "by_expected": {
            expected: {
                "total": sum(row["expected"] == expected for row in results),
                "yolo_pass": sum(row["expected"] == expected and bool(row["yolo_pass"]) for row in results),
                "web_pass": sum(row["expected"] == expected and bool(row["web_pass"]) for row in results),
            }
            for expected in ("mammal", "bird", "negative")
        },
    }
    (root / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
