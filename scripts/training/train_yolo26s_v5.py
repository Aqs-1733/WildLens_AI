from __future__ import annotations

from pathlib import Path

from ultralytics import YOLO


PROJECT = Path(r"C:\Users\xin20\Desktop\WildLens_AI\Shijing_handoff_full_20260722_144737")
MODEL = (
    PROJECT
    / "models"
    / "trained"
    / "runs"
    / "detect"
    / "wildlens_wcs_mammal_bird_v3"
    / "weights"
    / "best.pt"
)
DATA = PROJECT / "data" / "yolo_datasets" / "wildlens_v5" / "data.yaml"
RUNS = PROJECT / "models" / "trained" / "runs" / "detect"


def main() -> None:
    model = YOLO(str(MODEL))
    model.train(
        data=str(DATA),
        epochs=30,
        patience=8,
        batch=8,
        imgsz=640,
        device=0,
        workers=4,
        project=str(RUNS),
        name="wildlens_wcs_mammal_bird_v5",
        exist_ok=False,
        optimizer="AdamW",
        lr0=0.0001,
        lrf=0.1,
        cos_lr=True,
        weight_decay=0.0005,
        warmup_epochs=1.0,
        seed=20260724,
        deterministic=True,
        amp=True,
        cache=False,
        mosaic=0.5,
        close_mosaic=5,
        val=True,
        plots=True,
    )


if __name__ == "__main__":
    main()
