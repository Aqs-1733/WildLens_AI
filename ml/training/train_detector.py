"""Train a YOLO detector from a standard Ultralytics data YAML."""
from __future__ import annotations
import argparse
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("data", type=Path)
    parser.add_argument("--base", default="yolo11n.pt")
    parser.add_argument("--epochs", type=int, default=60)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--batch", type=int, default=16)
    parser.add_argument("--project", default="models/trained/runs")
    parser.add_argument("--name", default="wildlife_detector")
    args = parser.parse_args()
    try:
        from ultralytics import YOLO
    except ImportError as exc:
        raise SystemExit("请先安装：uv sync --extra vision") from exc
    model = YOLO(args.base)
    result = model.train(
        data=str(args.data), epochs=args.epochs, imgsz=args.imgsz, batch=args.batch,
        project=args.project, name=args.name, patience=12, cache=False, pretrained=True,
    )
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
