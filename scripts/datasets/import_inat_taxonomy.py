from __future__ import annotations

import argparse
import json
from pathlib import Path

from sqlalchemy import select

from backend.core.database import SessionLocal
from backend.models import Taxon


def category_group(raw: dict) -> str:
    kingdom = str(raw.get("kingdom") or "").lower()
    class_name = str(raw.get("class") or raw.get("class_name") or "").lower()
    phylum = str(raw.get("phylum") or "").lower()
    if kingdom == "plantae":
        return "plant"
    if kingdom == "fungi":
        return "fungus"
    if "aves" in class_name:
        return "bird"
    if "mammalia" in class_name:
        return "mammal"
    if "reptilia" in class_name:
        return "reptile"
    if "amphibia" in class_name:
        return "amphibian"
    if "actinopter" in class_name or "chondrich" in class_name:
        return "fish"
    if "insecta" in class_name:
        return "insect"
    if "arachnida" in class_name:
        return "arachnid"
    if "mollusca" in phylum:
        return "mollusk"
    if "arthropoda" in phylum:
        return "invertebrate"
    return "unknown"


def main() -> int:
    parser = argparse.ArgumentParser(description="Import iNaturalist taxonomy into the 识境 taxa table")
    parser.add_argument("annotations", type=Path)
    parser.add_argument("--output", type=Path, default=Path("models/metadata/inat2021_taxonomy.json"))
    parser.add_argument("--china-priority-file", type=Path)
    args = parser.parse_args()
    data = json.loads(args.annotations.read_text(encoding="utf-8"))
    categories = sorted(data["categories"], key=lambda item: int(item["id"]))
    priority_names: set[str] = set()
    if args.china_priority_file and args.china_priority_file.exists():
        priority_names = {
            line.strip().lower()
            for line in args.china_priority_file.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.startswith("#")
        }
    metadata = []
    with SessionLocal() as db:
        for model_index, raw in enumerate(categories):
            scientific = str(raw.get("name") or raw.get("scientific_name") or f"taxon_{raw['id']}")
            item = db.scalar(select(Taxon).where(Taxon.taxon_id == f"inat2021:{raw['id']}"))
            if not item:
                item = Taxon(taxon_id=f"inat2021:{raw['id']}", scientific_name=scientific)
                db.add(item)
            item.scientific_name = scientific
            item.common_name_en = str(raw.get("common_name") or "")
            item.kingdom = str(raw.get("kingdom") or "")
            item.phylum = str(raw.get("phylum") or "")
            item.class_name = str(raw.get("class") or raw.get("class_name") or "")
            item.order_name = str(raw.get("order") or raw.get("order_name") or "")
            item.family = str(raw.get("family") or "")
            item.genus = str(raw.get("genus") or "")
            item.species_epithet = scientific.split()[-1] if " " in scientific else ""
            item.category = category_group(raw)
            item.model_class_index = model_index
            item.source = "iNaturalist 2021"
            item.source_url = "https://github.com/visipedia/inat_comp/tree/master/2021"
            item.is_china_priority = scientific.lower() in priority_names
            metadata.append({
                "index": model_index,
                "category_id": int(raw["id"]),
                "scientific_name": scientific,
                "common_name_zh": item.common_name_zh,
                "common_name_en": item.common_name_en,
                "kingdom": item.kingdom,
                "phylum": item.phylum,
                "class": item.class_name,
                "order": item.order_name,
                "family": item.family,
                "genus": item.genus,
                "category": item.category,
                "is_china_priority": item.is_china_priority,
            })
        db.commit()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"已导入 {len(metadata)} 个分类单元；元数据：{args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
