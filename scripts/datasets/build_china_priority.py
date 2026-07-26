from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from sqlalchemy import select

from backend.core.database import SessionLocal
from backend.models import Taxon


def point_in_ring(x: float, y: float, ring: list[list[float]]) -> bool:
    inside = False
    j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i][:2]
        xj, yj = ring[j][:2]
        intersects = (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-12) + xi
        if intersects:
            inside = not inside
        j = i
    return inside


def in_geometry(lon: float, lat: float, geometry: dict[str, Any]) -> bool:
    coordinates = geometry.get("coordinates") or []
    polygons = coordinates if geometry.get("type") == "MultiPolygon" else [coordinates]
    for polygon in polygons:
        if not polygon:
            continue
        if point_in_ring(lon, lat, polygon[0]) and not any(point_in_ring(lon, lat, hole) for hole in polygon[1:]):
            return True
    return False


def coordinates(image: dict[str, Any]) -> tuple[float, float] | None:
    values = (image.get("longitude"), image.get("latitude"))
    if all(value is not None for value in values):
        try:
            return float(values[0]), float(values[1])
        except (TypeError, ValueError):
            return None
    location = image.get("location")
    if isinstance(location, str) and "," in location:
        try:
            lat, lon = (float(value.strip()) for value in location.split(",", 1))
            return lon, lat
        except ValueError:
            return None
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a China-priority species list from geotagged iNaturalist annotations")
    parser.add_argument("annotations", type=Path, nargs="+")
    parser.add_argument("--china-geojson", type=Path, default=Path("frontend/public/maps/china_adm0.geojson"))
    parser.add_argument("--output", type=Path, default=Path("data/taxonomy/china_priority_species.csv"))
    parser.add_argument("--limit", type=int, default=10000)
    parser.add_argument("--update-database", action="store_true")
    args = parser.parse_args()

    geo = json.loads(args.china_geojson.read_text(encoding="utf-8"))
    geometry = geo["features"][0]["geometry"]
    counts: Counter[int] = Counter()
    months: dict[int, Counter[int]] = defaultdict(Counter)
    categories: dict[int, dict] = {}

    for annotation_path in args.annotations:
        data = json.loads(annotation_path.read_text(encoding="utf-8"))
        categories.update({int(item["id"]): item for item in data.get("categories") or []})
        category_by_image = {int(item["image_id"]): int(item["category_id"]) for item in data.get("annotations") or []}
        for image in data.get("images") or []:
            location = coordinates(image)
            if not location or not in_geometry(location[0], location[1], geometry):
                continue
            category_id = category_by_image.get(int(image["id"]))
            if category_id is None:
                continue
            counts[category_id] += 1
            date = str(image.get("date") or image.get("date_captured") or "")
            if len(date) >= 7 and date[5:7].isdigit():
                months[category_id][int(date[5:7])] += 1

    rows = []
    for category_id, count in counts.most_common(args.limit):
        raw = categories.get(category_id, {})
        rows.append({
            "category_id": category_id,
            "scientific_name": str(raw.get("name") or raw.get("scientific_name") or ""),
            "common_name_en": str(raw.get("common_name") or ""),
            "kingdom": str(raw.get("kingdom") or ""),
            "family": str(raw.get("family") or ""),
            "china_geotagged_observations": count,
            "months": json.dumps(dict(months[category_id]), ensure_ascii=False),
        })
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0].keys()) if rows else ["category_id", "scientific_name"])
        writer.writeheader()
        writer.writerows(rows)

    if args.update_database:
        with SessionLocal() as db:
            for row in rows:
                taxon = db.scalar(select(Taxon).where(Taxon.taxon_id == f"inat2021:{row['category_id']}"))
                if not taxon:
                    continue
                taxon.is_china_priority = True
                taxon.distribution = {
                    **(taxon.distribution or {}),
                    "china_geotagged_observations": row["china_geotagged_observations"],
                    "months": json.loads(row["months"]),
                    "method": "iNaturalist 2021 geotagged images inside Natural Earth China outline",
                }
            db.commit()

    print(f"中国范围内有地理记录的类别：{len(rows)}；输出：{args.output}")
    if len(rows) < args.limit:
        print("注意：iNaturalist 2021中有中国地理记录的类别少于目标数量；全一万类模型仍保留，其余类别不加中国先验。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
