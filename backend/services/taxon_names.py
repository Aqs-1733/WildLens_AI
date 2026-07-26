from __future__ import annotations

import csv
import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.core.config import PROJECT_ROOT
from backend.models import Species, Taxon

_CJK_RE = re.compile(r"[\u4e00-\u9fff]")

_SCIENTIFIC_ZH: dict[str, str] = {
    "Passer montanus": "树麻雀",
    "Passer montanus kansuensis": "树麻雀甘肃亚种",
    "Passer domesticus": "家麻雀",
    "Nycticorax nycticorax": "夜鹭",
    "Nycticorax nycticorax nycticorax": "夜鹭指名亚种",
    "Ardea cinerea": "苍鹭",
    "Ardea alba": "大白鹭",
    "Egretta garzetta": "小白鹭",
    "Bubulcus ibis": "牛背鹭",
    "Butorides striata": "绿鹭",
    "Butorides virescens": "绿鹭",
    "Anas platyrhynchos": "绿头鸭",
    "Branta canadensis": "加拿大雁",
    "Sturnus vulgaris": "紫翅椋鸟",
    "Turdus merula": "乌鸫",
    "Parus major": "大山雀",
    "Hirundo rustica": "家燕",
    "Cardinalis cardinalis": "北美红雀",
    "Sciurus carolinensis": "东部灰松鼠",
    "Odocoileus virginianus": "白尾鹿",
    "Coccinella septempunctata": "七星瓢虫",
    "Apis mellifera": "西方蜜蜂",
    "Harmonia axyridis": "异色瓢虫",
    "Ginkgo biloba": "银杏",
    "Panthera tigris": "虎",
    "Panthera tigris tigris": "孟加拉虎",
    "Panthera pardus": "豹",
    "Elephas maximus": "亚洲象",
}

_SUBSPECIES_ZH: dict[str, str] = {
    "kansuensis": "甘肃亚种",
    "nycticorax": "指名亚种",
    "tigris": "指名亚种",
    "sinensis": "中华亚种",
    "japonicus": "日本亚种",
    "coreanus": "朝鲜亚种",
    "mandarinus": "华东亚种",
    "formosanus": "台湾亚种",
    "hainanus": "海南亚种",
}

_CATEGORY_ZH: dict[str, str] = {
    "mammal": "哺乳动物",
    "bird": "鸟类",
    "reptile": "爬行动物",
    "amphibian": "两栖动物",
    "fish": "鱼类",
    "insect": "昆虫",
    "arachnid": "蛛形动物",
    "mollusk": "软体动物",
    "crustacean": "甲壳动物",
    "invertebrate": "无脊椎动物",
    "plant": "植物",
    "angiosperm": "被子植物",
    "gymnosperm": "裸子植物",
    "fern": "蕨类",
    "moss": "苔藓",
    "algae": "藻类",
    "fungus": "真菌",
    "lichen": "地衣",
    "phenomenon": "自然现象",
    "weather": "天气现象",
    "fire": "火情候选",
    "smoke": "烟雾候选",
    "unknown": "待确认目标",
}


def has_cjk(value: str | None) -> bool:
    return bool(value and _CJK_RE.search(value))


def category_zh(category: str | None) -> str:
    return _CATEGORY_ZH.get(str(category or "unknown").lower(), str(category or "待确认"))


@lru_cache(maxsize=1)
def _target_species_names() -> dict[str, str]:
    names: dict[str, str] = {}
    json_path = PROJECT_ROOT / "data" / "taxonomy" / "target_species.json"
    if json_path.exists():
        try:
            items = json.loads(json_path.read_text(encoding="utf-8"))
            for item in items if isinstance(items, list) else []:
                scientific = str(item.get("scientific_name") or "").strip()
                common = str(item.get("common_name") or "").strip()
                if scientific and has_cjk(common):
                    names[scientific.lower()] = common
        except (OSError, json.JSONDecodeError):
            pass
    csv_path = PROJECT_ROOT / "data" / "taxonomy" / "target_species.csv"
    if csv_path.exists():
        try:
            with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
                for row in csv.DictReader(handle):
                    scientific = str(row.get("scientific_name") or "").strip()
                    common = str(row.get("common_name") or "").strip()
                    if scientific and has_cjk(common):
                        names[scientific.lower()] = common
        except OSError:
            pass
    return names


def _clean_scientific(scientific_name: str | None) -> str:
    return " ".join(str(scientific_name or "").replace("_", " ").split())


def _base_species(scientific_name: str) -> str:
    parts = scientific_name.split()
    return " ".join(parts[:2]) if len(parts) >= 2 else scientific_name


def _subspecies_name(scientific_name: str) -> str:
    parts = scientific_name.split()
    if len(parts) < 3:
        return ""
    base = _base_species(scientific_name)
    base_zh = _SCIENTIFIC_ZH.get(base) or _target_species_names().get(base.lower())
    if not base_zh:
        return ""
    epithet = parts[2].lower()
    suffix = _SUBSPECIES_ZH.get(epithet)
    return f"{base_zh}{suffix}" if suffix else f"{base_zh}亚种"


def resolve_chinese_name(
    db: Session | None,
    scientific_name: str | None,
    current_name: str | None = "",
    category: str | None = "",
) -> str:
    current = str(current_name or "").strip()
    scientific = _clean_scientific(scientific_name)
    if has_cjk(current) and current != "??":
        return current
    if scientific in _SCIENTIFIC_ZH:
        return _SCIENTIFIC_ZH[scientific]
    target_name = _target_species_names().get(scientific.lower())
    if target_name:
        return target_name
    subspecies = _subspecies_name(scientific)
    if subspecies:
        return subspecies
    if db and scientific:
        species = db.scalar(
            select(Species).where(func.lower(Species.scientific_name) == scientific.lower())
        )
        if species and has_cjk(species.common_name):
            return species.common_name
        taxon = db.scalar(
            select(Taxon).where(func.lower(Taxon.scientific_name) == scientific.lower())
        )
        if taxon and has_cjk(taxon.common_name_zh):
            return taxon.common_name_zh
        base = _base_species(scientific)
        if base and base != scientific:
            species = db.scalar(
                select(Species).where(func.lower(Species.scientific_name) == base.lower())
            )
            if species and has_cjk(species.common_name):
                return species.common_name
            taxon = db.scalar(
                select(Taxon).where(func.lower(Taxon.scientific_name) == base.lower())
            )
            if taxon and has_cjk(taxon.common_name_zh):
                return taxon.common_name_zh
    if scientific:
        return scientific
    if current:
        return current
    return category_zh(category)


def localize_candidate(db: Session | None, candidate: dict[str, Any]) -> dict[str, Any]:
    output = dict(candidate)
    scientific = str(output.get("scientific_name") or output.get("name") or "").strip()
    current = str(output.get("common_name") or output.get("name") or "").strip()
    zh = resolve_chinese_name(db, scientific, current, str(output.get("category") or ""))
    if zh:
        output["common_name_zh"] = zh
        output["display_name"] = zh
        output["name"] = zh
    if scientific:
        output["scientific_name"] = scientific
    return output


def localize_prediction(db: Session | None, result: dict[str, Any]) -> dict[str, Any]:
    output = dict(result)
    scientific = str(output.get("scientific_name") or "").strip()
    zh = resolve_chinese_name(
        db,
        scientific,
        str(output.get("common_name") or output.get("label") or ""),
        str(output.get("category") or ""),
    )
    if zh:
        output["common_name"] = zh
        output["label"] = zh
    category = str(output.get("category") or "unknown").lower()
    if "bioclip" in str(output.get("model_source") or output.get("source") or "").lower():
        output["explanation"] = (
            f"本地 BioCLIP 将图像向量与 400721 个物种视觉原型检索后，"
            f"最相近的候选为{zh or scientific}。请结合置信度、Top K 候选和拍摄角度复核。"
        )
    output["alternatives"] = [
        localize_candidate(db, item) if isinstance(item, dict) else item
        for item in list(output.get("alternatives") or [])
    ]
    output["bioclip_top_k"] = [
        localize_candidate(db, item) if isinstance(item, dict) else item
        for item in list(output.get("bioclip_top_k") or [])
    ]
    output["category_zh"] = category_zh(category)
    return output
