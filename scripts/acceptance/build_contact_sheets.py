from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    for group in ("mammal", "bird", "negative"):
        paths = sorted((args.root / group).glob(f"{group}_*"))
        width, cell_w, cell_h = 1200, 240, 180
        rows = (len(paths) + 4) // 5
        canvas = Image.new("RGB", (width, rows * cell_h), "white")
        draw = ImageDraw.Draw(canvas)
        for index, path in enumerate(paths):
            with Image.open(path) as source:
                image = ImageOps.exif_transpose(source).convert("RGB")
                image.thumbnail((cell_w - 8, cell_h - 28))
                x = (index % 5) * cell_w + (cell_w - image.width) // 2
                y = (index // 5) * cell_h + 20
                canvas.paste(image, (x, y))
            draw.text(((index % 5) * cell_w + 5, (index // 5) * cell_h + 3), path.stem, fill="black")
        canvas.save(args.root / f"contact_sheet_{group}.jpg", quality=90)


if __name__ == "__main__":
    main()
