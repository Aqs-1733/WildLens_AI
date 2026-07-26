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
DATA = PROJECT / "data" / "yolo_datasets" / "wildlens_v4" / "data.yaml"
RUNS = PROJECT / "models" / "trained" / "runs" / "detect"


def main() -> None:
    model = YOLO(str(MODEL))
    model.train(
        data=str(DATA),
        epochs=60,
        patience=12,
        batch=8,
        imgsz=640,
        device=0,
        workers=4,
        project=str(RUNS),
        name="wildlens_wcs_mammal_bird_v4_final",
        exist_ok=False,
        pretrained=True,
        optimizer="auto",
        seed=20260723,
        deterministic=True,
        amp=True,
        cache=False,
        close_mosaic=10,
        val=True,
        plots=True,
    )


if __name__ == "__main__":
    main()
