from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import cv2

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.core.config import get_settings
from backend.vision.active_learning_memory import active_learning_memory
from backend.vision.learning_feedback import learn_labeled_image
from scripts.seed_showcase_records import ANIMALS, PLANTS


def _already_seeded(source_url: str) -> bool:
    db_path = Path(get_settings().active_learning_embedding_db_path)
    if not db_path.exists():
        return False
    with sqlite3.connect(db_path) as connection:
        try:
            row = connection.execute(
                "SELECT 1 FROM streamed_embeddings WHERE source_url = ? LIMIT 1",
                (source_url,),
            ).fetchone()
        except sqlite3.OperationalError:
            return False
    return bool(row)


def _variants(image):
    height, width = image.shape[:2]
    side = int(min(height, width) * 0.82)
    x1 = max(0, (width - side) // 2)
    y1 = max(0, (height - side) // 2)
    center = image[y1 : y1 + side, x1 : x1 + side]
    return {
        "full": image,
        "flip": cv2.flip(image, 1),
        "center": center if center is not None and center.size else image,
    }


def _seed_item(prefix: str, index: int, item: dict) -> int:
    image_path = PROJECT_ROOT / "storage" / "results" / f"showcase_{prefix}_{index:02d}.jpg"
    if not image_path.exists():
        print(f"skip missing image: {image_path}")
        return 0
    image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
    if image is None or image.size == 0:
        print(f"skip unreadable image: {image_path}")
        return 0
    stored = 0
    for variant_name, variant in _variants(image).items():
        source_url = f"/media/results/{image_path.name}#{variant_name}"
        if _already_seeded(source_url):
            continue
        result = learn_labeled_image(
            variant,
            scientific_name=item["scientific_name"],
            common_name=item["common_name"],
            category=item["category"],
            label_source="showcase-reference",
            label_confidence=1.0,
            validator="seed_showcase_active_learning",
            notes="trusted real reference image imported for local active-learning correction",
        )
        if result.get("stored"):
            row_id = result.get("row_id")
            with active_learning_memory._connect() as connection:  # noqa: SLF001
                active_learning_memory.ensure_schema(connection)
                connection.execute(
                    "UPDATE streamed_embeddings SET source_url = ? WHERE id = ?",
                    (source_url, row_id),
                )
                connection.commit()
            stored += 1
    return stored


def main() -> int:
    active_learning_memory.ensure_schema()
    total = 0
    for index, item in enumerate(ANIMALS, start=1):
        total += _seed_item("animal", index, item)
    for index, item in enumerate(PLANTS, start=1):
        total += _seed_item("plant", index, item)
    print(f"showcase active-learning vectors stored: {total}")
    print(active_learning_memory.status())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
