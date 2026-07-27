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
from backend.services.text_clean import clean_text, is_garbled

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
    "Hirundo dimidiata": "珍珠胸燕",
    "Hirundo dimidiata marwitzi": "珍珠胸燕马氏亚种",
    "Riparia riparia": "崖沙燕",
    "Tachycineta albilinea": "红树林燕",
    "Tachycineta bicolor": "树燕",
    "Progne subis": "紫崖燕",
    "Cecropis rufula": "赤腰燕",
    "Cardinalis cardinalis": "北美红雀",
    "Haliaeetus leucocephalus": "白头海雕",
    "Haliaeetus leucocephalus washingtoniensis": "白头海雕北方亚种",
    "Sciurus carolinensis": "东部灰松鼠",
    "Odocoileus virginianus": "白尾鹿",
    "Coccinella septempunctata": "七星瓢虫",
    "Apis mellifera": "西方蜜蜂",
    "Harmonia axyridis": "异色瓢虫",
    "Ginkgo biloba": "银杏",
    "Panthera tigris": "虎",
    "Panthera tigris tigris": "孟加拉虎",
    "Panthera tigris altaica": "东北虎",
    "Panthera pardus": "金钱豹",
    "Panthera leo": "狮",
    "Ailuropoda melanoleuca": "大熊猫",
    "Elephas maximus": "亚洲象",
    "Elephas maximus indicus": "印度象",
    "Giraffa camelopardalis": "长颈鹿",
    "Giraffa camelopardalis camelopardalis": "努比亚长颈鹿",
    "Vulpes vulpes": "赤狐",
}

_ENGLISH_ZH: dict[str, str] = {
    "mangrove swallow": "红树林燕",
    "bank swallow": "崖沙燕",
    "tree swallow": "树燕",
    "purple martin": "紫崖燕",
    "european red-rumped swallow": "赤腰燕",
    "barn swallow": "家燕",
    "pearl-breasted swallow": "珍珠胸燕",
    "asian elephant": "亚洲象",
    "indian elephant": "印度象",
    "bald eagle": "白头海雕",
    "giant panda": "大熊猫",
    "giraffe": "长颈鹿",
    "red fox": "赤狐",
    "ginkgo": "银杏",
    "ginkgo biloba": "银杏",
}

_SUBSPECIES_ZH: dict[str, str] = {
    "kansuensis": "甘肃亚种",
    "nycticorax": "指名亚种",
    "tigris": "指名亚种",
    "altaica": "东北亚种",
    "indicus": "印度亚种",
    "camelopardalis": "指名亚种",
    "washingtoniensis": "北方亚种",
    "sinensis": "中华亚种",
    "japonicus": "日本亚种",
    "coreanus": "朝鲜亚种",
    "mandarinus": "华东亚种",
    "formosanus": "台湾亚种",
    "hainanus": "海南亚种",
}

CANONICAL_CATEGORIES = {
    "mammal",
    "bird",
    "reptile",
    "amphibian",
    "fish",
    "insect",
    "arachnid",
    "mollusk",
    "crustacean",
    "invertebrate",
    "plant",
    "angiosperm",
    "gymnosperm",
    "fern",
    "moss",
    "algae",
    "fungus",
    "lichen",
    "person",
    "vehicle",
    "phenomenon",
    "weather",
    "fire",
    "smoke",
    "unknown",
}

_CATEGORY_ALIASES: dict[str, str] = {
    "animal": "mammal",
    "animals": "mammal",
    "mammalia": "mammal",
    "mammal species": "mammal",
    "aves": "bird",
    "bird species": "bird",
    "plant species": "plant",
    "plantae": "plant",
    "tracheophyta": "plant",
    "自然": "phenomenon",
    "自然现象": "phenomenon",
    "天气": "weather",
    "天气现象": "weather",
    "火": "fire",
    "火焰": "fire",
    "烟": "smoke",
    "烟雾": "smoke",
    "动物": "mammal",
    "哺乳动物": "mammal",
    "哺乳纲": "mammal",
    "鸟": "bird",
    "鸟类": "bird",
    "鸟纲": "bird",
    "爬行动物": "reptile",
    "两栖动物": "amphibian",
    "鱼": "fish",
    "鱼类": "fish",
    "昆虫": "insect",
    "蛛形动物": "arachnid",
    "软体动物": "mollusk",
    "甲壳动物": "crustacean",
    "无脊椎动物": "invertebrate",
    "植物": "plant",
    "被子植物": "angiosperm",
    "裸子植物": "gymnosperm",
    "蕨类": "fern",
    "苔藓": "moss",
    "藻类": "algae",
    "真菌": "fungus",
    "地衣": "lichen",
    "人": "person",
    "人物": "person",
    "车辆": "vehicle",
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
    "fern": "蕨类植物",
    "moss": "苔藓植物",
    "algae": "藻类",
    "fungus": "真菌",
    "lichen": "地衣",
    "person": "人物",
    "vehicle": "车辆",
    "phenomenon": "自然现象",
    "weather": "天气现象",
    "fire": "火情候选",
    "smoke": "烟雾候选",
    "unknown": "低置信度候选",
}


def has_cjk(value: str | None) -> bool:
    return bool(value and _CJK_RE.search(value))


def normalize_category(value: Any, default: str = "unknown") -> str:
    raw = clean_text(value, "").strip().lower()
    if not raw:
        return default
    raw = raw.replace("_", " ").replace("-", " ")
    compact = raw.replace(" ", "")
    if raw in CANONICAL_CATEGORIES:
        return raw
    if compact in CANONICAL_CATEGORIES:
        return compact
    if raw in _CATEGORY_ALIASES:
        return _CATEGORY_ALIASES[raw]
    if compact in _CATEGORY_ALIASES:
        return _CATEGORY_ALIASES[compact]
    if "哺乳" in raw:
        return "mammal"
    if "鸟" in raw or "avian" in raw:
        return "bird"
    if "爬行" in raw:
        return "reptile"
    if "两栖" in raw:
        return "amphibian"
    if "昆虫" in raw:
        return "insect"
    if "植物" in raw or "plant" in raw:
        return "plant"
    if "真菌" in raw or "fung" in raw:
        return "fungus"
    if "现象" in raw or "weather" in raw:
        return "phenomenon"
    return default


def category_zh(category: str | None) -> str:
    normalized = normalize_category(category)
    return _CATEGORY_ZH.get(normalized, "低置信度候选")


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
                if scientific and has_cjk(common) and not is_garbled(common):
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
                    if scientific and has_cjk(common) and not is_garbled(common):
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
    suffix = _SUBSPECIES_ZH.get(parts[2].lower())
    return f"{base_zh}{suffix}" if suffix else f"{base_zh}亚种"


def resolve_chinese_name(
    db: Session | None,
    scientific_name: str | None,
    current_name: str | None = "",
    category: str | None = "",
) -> str:
    current = clean_text(current_name, "").strip()
    scientific = _clean_scientific(scientific_name)
    if has_cjk(current) and current != "??" and not is_garbled(current):
        return current
    english_name = current.lower()
    if english_name in _ENGLISH_ZH:
        return _ENGLISH_ZH[english_name]
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
        if species and has_cjk(species.common_name) and not is_garbled(species.common_name):
            return species.common_name
        taxon = db.scalar(
            select(Taxon).where(func.lower(Taxon.scientific_name) == scientific.lower())
        )
        if taxon and has_cjk(taxon.common_name_zh) and not is_garbled(taxon.common_name_zh):
            return taxon.common_name_zh
        base = _base_species(scientific)
        if base and base != scientific:
            species = db.scalar(
                select(Species).where(func.lower(Species.scientific_name) == base.lower())
            )
            if species and has_cjk(species.common_name) and not is_garbled(species.common_name):
                return species.common_name
            taxon = db.scalar(
                select(Taxon).where(func.lower(Taxon.scientific_name) == base.lower())
            )
            if taxon and has_cjk(taxon.common_name_zh) and not is_garbled(taxon.common_name_zh):
                return taxon.common_name_zh
    if scientific:
        return scientific
    if current and not is_garbled(current):
        return current
    return category_zh(category)


def localize_candidate(db: Session | None, candidate: dict[str, Any]) -> dict[str, Any]:
    output = dict(candidate)
    category = normalize_category(output.get("category"), str(output.get("category") or "unknown"))
    scientific = str(output.get("scientific_name") or output.get("name") or "").strip()
    current = str(output.get("common_name") or output.get("name") or "").strip()
    scientific_zh = resolve_chinese_name(db, scientific, "", category)
    zh = scientific_zh if has_cjk(scientific_zh) else resolve_chinese_name(db, scientific, current, category)
    if zh:
        output["common_name_zh"] = zh
        output["display_name"] = zh
        output["name"] = zh
    if scientific:
        output["scientific_name"] = scientific
    output["category"] = category
    output["category_zh"] = category_zh(category)
    return output


def localize_prediction(db: Session | None, result: dict[str, Any]) -> dict[str, Any]:
    output = dict(result)
    category = normalize_category(output.get("category"))
    scientific = str(output.get("scientific_name") or "").strip()
    zh = resolve_chinese_name(
        db,
        scientific,
        str(output.get("common_name") or output.get("label") or ""),
        category,
    )
    if zh:
        output["common_name"] = zh
        output["label"] = zh
    output["category"] = category
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
