from __future__ import annotations

import json
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models import Detection, Species
from backend.services.ai import _extract_json, ark_ai

LATIN_RE = re.compile(r"^[A-Z][a-z-]+(?:\s+[a-z][a-z-]+){1,3}$")

CATEGORY_COLORS = {
    "mammal": "#F5A623",
    "bird": "#55B8FF",
    "reptile": "#D6C64C",
    "amphibian": "#2FD5C4",
    "fish": "#45B6FF",
    "insect": "#A87CFF",
    "arachnid": "#A87CFF",
    "mollusk": "#7DD3FC",
    "crustacean": "#7DD3FC",
    "invertebrate": "#A87CFF",
    "plant": "#35E58C",
    "angiosperm": "#35E58C",
    "gymnosperm": "#35E58C",
    "fern": "#35E58C",
    "moss": "#35E58C",
    "algae": "#35E58C",
    "fungus": "#E0B55A",
    "lichen": "#B4D66C",
    "unknown": "#8CA9A0",
}

KNOWN_PROFILES: dict[str, dict[str, Any]] = {
    "Passer montanus": {
        "common_name_zh": "树麻雀",
        "english_name": "Eurasian tree sparrow",
        "category": "bird",
    },
    "Passer montanus kansuensis": {
        "common_name_zh": "树麻雀甘肃亚种",
        "english_name": "Eurasian tree sparrow",
        "category": "bird",
    },
    "Nycticorax nycticorax": {
        "common_name_zh": "夜鹭",
        "english_name": "Black-crowned night heron",
        "category": "bird",
    },
    "Nycticorax nycticorax nycticorax": {
        "common_name_zh": "夜鹭指名亚种",
        "english_name": "Black-crowned night heron",
        "category": "bird",
    },
    "Larus armenicus": {
        "common_name_zh": "亚美尼亚鸥",
        "english_name": "Armenian gull",
        "category": "bird",
    },
}

SUBSPECIES_HINTS = {
    "kansuensis": "甘肃亚种",
    "nycticorax": "指名亚种",
    "altaica": "东北亚种",
    "tigris": "指名亚种",
}


def looks_latin(value: str) -> bool:
    return bool(LATIN_RE.match((value or "").strip()))


def is_specific_species_name(value: str) -> bool:
    cleaned = (value or "").strip()
    if not cleaned:
        return False
    vague = {"待确认目标", "待确认植物", "疑似雾或低能见度", "疑似火焰色区域", "未知物种"}
    return cleaned not in vague and not cleaned.startswith("疑似") and not cleaned.startswith("待确认")


def _safe_text(value: Any, default: str = "") -> str:
    return str(value or default).strip()


def _profile_from_known(scientific_name: str, category: str = "unknown") -> dict[str, Any]:
    name = scientific_name.strip()
    if name in KNOWN_PROFILES:
        base = dict(KNOWN_PROFILES[name])
    else:
        parts = name.split()
        base_name = " ".join(parts[:2])
        base = dict(KNOWN_PROFILES.get(base_name, {}))
        if base and len(parts) >= 3:
            suffix = SUBSPECIES_HINTS.get(parts[2].lower(), f"{parts[2]}亚种")
            common = str(base.get("common_name_zh") or base_name)
            if suffix not in common:
                common = f"{common}{suffix}"
            base["common_name_zh"] = common
    if not base:
        parts = name.split()
        base = {
            "common_name_zh": name if not parts else f"{parts[0]}属物种",
            "english_name": "",
            "category": category or "unknown",
        }
    base.setdefault("scientific_name", name)
    base.setdefault("category", category or "unknown")
    return base


def _fallback_profile(scientific_name: str, category: str = "unknown", common_hint: str = "") -> dict[str, Any]:
    profile = _profile_from_known(scientific_name, category)
    common = _safe_text(profile.get("common_name_zh")) or common_hint or scientific_name
    category_label = {
        "bird": "鸟类",
        "mammal": "哺乳动物",
        "plant": "植物",
        "insect": "昆虫",
        "reptile": "爬行动物",
        "amphibian": "两栖动物",
        "fish": "鱼类",
    }.get(category or profile.get("category") or "unknown", "生物")
    return {
        "common_name_zh": common,
        "scientific_name": scientific_name,
        "english_name": _safe_text(profile.get("english_name")),
        "category": _safe_text(profile.get("category"), category or "unknown"),
        "protection_level": "未列入本地保护名录",
        "rarity": 2,
        "habitat": f"{common}的具体栖息环境需要结合当地记录确认，通常可先按{category_label}的生境线索继续观察。",
        "distribution": "分布信息需要结合权威名录和本地观察记录进一步确认。",
        "traits": f"{common}（{scientific_name}）是本次识别到的具体分类单元。建议结合头部、体色、翅/叶/花果等关键特征复核。",
        "diet": "食性或营养方式需要结合该类群资料确认。",
        "activity": "活动规律需要结合季节、昼夜和栖息地继续观察。",
        "ecology_value": "该记录可作为本地自然观察数据的一部分，用于积累物种出现与生境信息。",
        "threats": "主要威胁需结合当地栖息地变化、人为干扰和种群状态判断。",
        "conservation": "拍摄和记录时请减少干扰，避免透露珍稀物种精确位置。",
        "facts": [f"学名：{scientific_name}", "识别结果应结合更多角度和地点信息复核。"],
    }


async def _ai_profile(scientific_name: str, category: str, common_hint: str = "") -> dict[str, Any] | None:
    if not ark_ai.enabled:
        return None
    prompt = (
        "你是中文物种命名和自然科普助手。请根据给定学名生成中文物种档案。"
        "内容应基于常见公开资料、权威名录和稳定自然史知识；不确定的信息要写明需以当地权威资料核对。"
        "必须输出严格 JSON，不要 Markdown，不要解释 JSON 之外的文字。"
        "中文名必须是具体名字，不能写“待确认”“某种鸟”“疑似”。"
        "如果是亚种或变种，中文名应体现亚种/变种，例如“树麻雀甘肃亚种”。"
        "字段：common_name_zh, scientific_name, english_name, category, protection_level, rarity,"
        "habitat, distribution, traits, diet, activity, ecology_value, threats, conservation, facts。"
        "facts 是 2-4 条中文短句。rarity 为 1-5。"
        f"\n学名：{scientific_name}\n当前类别：{category or 'unknown'}\n已有名称线索：{common_hint or '无'}"
    )
    answer = await ark_ai.chat("只输出 JSON。", prompt, temperature=0.05, max_tokens=760, timeout_seconds=18.0)
    if not answer:
        return None
    data = _extract_json(answer)
    return data if isinstance(data, dict) else None


def _unique_common_name(db: Session, common_name: str, scientific_name: str) -> str:
    common_name = common_name.strip()[:90] or scientific_name[:90]
    existing = db.scalar(select(Species).where(Species.common_name == common_name))
    if not existing or existing.scientific_name == scientific_name:
        return common_name
    suffix = scientific_name[: max(1, 96 - len(common_name))]
    return f"{common_name}（{suffix}）"[:100]


def species_needs_profile_refresh(species: Species) -> bool:
    notes = " ".join(str(item) for item in (species.source_notes or []))
    if "识境 ARK 中文科普生成" in notes:
        return False
    if "识境本地临时物种档案" in notes:
        return True
    if species.scientific_name:
        return True
    fields = " ".join(
        str(getattr(species, field, "") or "")
        for field in ("traits", "habitat", "distribution", "diet", "activity", "ecology_value", "threats", "conservation")
    )
    markers = ("待", "首次打开科普", "生成并缓存", "由真实识别记录", "逐步完善")
    return any(marker in fields for marker in markers)


def _apply_profile_to_species(species: Species, profile: dict[str, Any]) -> None:
    species.common_name = _safe_text(profile.get("common_name_zh"), species.common_name)[:100]
    species.english_name = _safe_text(profile.get("english_name"), species.english_name)[:150]
    species.category = _safe_text(profile.get("category"), species.category)[:40]
    species.kingdom = "Plantae" if species.category in {"plant", "angiosperm", "gymnosperm", "fern", "moss", "algae"} else "Animalia"
    protection = _safe_text(profile.get("protection_level"), species.protection_level)
    if "待" in protection or "未知" in protection:
        protection = "未列入本地保护名录"
    species.protection_level = protection[:80]
    try:
        species.rarity = max(1, min(5, int(profile.get("rarity") or species.rarity or 2)))
    except (TypeError, ValueError):
        species.rarity = species.rarity or 2
    species.color = CATEGORY_COLORS.get(species.category, CATEGORY_COLORS["unknown"])
    for field in ("habitat", "distribution", "traits", "diet", "activity", "ecology_value", "threats", "conservation"):
        value = _safe_text(profile.get(field))
        if value and not any(marker in value for marker in ("待补充", "待查询", "待核验", "未知")):
            setattr(species, field, value)
    facts = profile.get("facts")
    if isinstance(facts, list):
        species.facts = [str(item).strip() for item in facts if str(item).strip()][:6]
    species.taxonomy = {"scientific_name": species.scientific_name}
    if profile.get("_profile_mode") == "ark":
        species.source_notes = ["识境 ARK 中文科普生成；请以权威名录和实地复核为准。"]
    else:
        species.source_notes = ["识境本地临时物种档案；下次打开会继续尝试生成完整科普。"]


async def ensure_species_profile(
    db: Session,
    *,
    scientific_name: str,
    category: str = "unknown",
    common_hint: str = "",
    force: bool = False,
) -> Species | None:
    scientific_name = scientific_name.strip()
    if not scientific_name:
        return None
    species = db.scalar(select(Species).where(Species.scientific_name == scientific_name))
    if species and species.common_name and not looks_latin(species.common_name) and not force and not species_needs_profile_refresh(species):
        return species

    profile = await _ai_profile(scientific_name, category, common_hint)
    if profile:
        profile["_profile_mode"] = "ark"
    if not profile:
        profile = _fallback_profile(scientific_name, category, common_hint)
        profile["_profile_mode"] = "local"
    common_name = _safe_text(profile.get("common_name_zh")) or common_hint or scientific_name
    if looks_latin(common_name):
        common_name = _fallback_profile(scientific_name, category, common_hint)["common_name_zh"]
    profile["common_name_zh"] = _unique_common_name(db, common_name, scientific_name)
    profile["scientific_name"] = scientific_name
    profile["category"] = _safe_text(profile.get("category"), category or "unknown")

    if not species:
        species = Species(
            common_name=profile["common_name_zh"],
            scientific_name=scientific_name,
            english_name=_safe_text(profile.get("english_name")),
            category=profile["category"],
            color=CATEGORY_COLORS.get(profile["category"], CATEGORY_COLORS["unknown"]),
        )
        db.add(species)
        db.flush()
    _apply_profile_to_species(species, profile)
    db.flush()
    return species


async def localize_detection(db: Session, detection: Detection) -> Species | None:
    scientific = (detection.scientific_name or "").strip()
    if not scientific and looks_latin(detection.label):
        scientific = detection.label.strip()
        detection.scientific_name = scientific
    if not scientific:
        return None
    species = await ensure_species_profile(
        db,
        scientific_name=scientific,
        category=detection.category or "unknown",
        common_hint=detection.label,
    )
    if species:
        detection.species_id = species.id
        detection.label = species.common_name
        if detection.category == "unknown" or not detection.category:
            detection.category = species.category
        detection.color = species.color
        if not detection.explanation or "BioCLIP matched" in detection.explanation:
            detection.explanation = f"识别为{species.common_name}（{species.scientific_name}）。请结合图像细节、地点和季节继续复核。"
    return species


async def ensure_species_from_user_text(
    db: Session,
    *,
    species_name: str,
    scientific_name: str = "",
    category: str = "unknown",
) -> Species | None:
    species_name = species_name.strip()
    scientific_name = scientific_name.strip()
    if scientific_name:
        return await ensure_species_profile(
            db,
            scientific_name=scientific_name,
            category=category,
            common_hint=species_name,
        )
    if species_name:
        found = db.scalar(
            select(Species).where(
                (Species.common_name == species_name)
                | (Species.scientific_name == species_name)
                | (Species.english_name == species_name)
            )
        )
        if found:
            return found
    if ark_ai.enabled and species_name:
        prompt = (
            "根据用户输入的中文或英文物种名，解析成一个最可能的具体物种。"
            "输出严格 JSON：common_name_zh, scientific_name, english_name, category。"
            "如果无法确定到物种，也要给最常用的具体分类名，不要输出“未知”。"
            f"\n用户输入：{species_name}"
        )
        answer = await ark_ai.chat("只输出 JSON。", prompt, temperature=0.05)
        data = _extract_json(answer or "") if answer else None
        if isinstance(data, dict):
            scientific_name = _safe_text(data.get("scientific_name"))
            category = _safe_text(data.get("category"), category)
            species_name = _safe_text(data.get("common_name_zh"), species_name)
    if scientific_name:
        return await ensure_species_profile(
            db,
            scientific_name=scientific_name,
            category=category,
            common_hint=species_name,
        )
    if species_name:
        common = _unique_common_name(db, species_name, species_name)
        species = Species(
            common_name=common,
            scientific_name="",
            english_name="",
            category=category or "unknown",
            protection_level="未列入本地保护名录",
            traits=f"{common}来自用户手动记录，建议补充照片或学名以便进一步校验。",
            habitat="请在观察记录中补充地点和生境。",
            distribution="由用户观察记录逐步积累。",
            color=CATEGORY_COLORS.get(category, CATEGORY_COLORS["unknown"]),
            facts=["手动添加的观察物种。"],
        )
        db.add(species)
        db.flush()
        return species
    return None


def species_knowledge_payload(species: Species) -> dict[str, Any]:
    return {
        "species_id": species.id,
        "common_name": species.common_name,
        "scientific_name": species.scientific_name,
        "english_name": species.english_name,
        "category": species.category,
        "protection_level": species.protection_level,
        "rarity": species.rarity,
        "color": species.color,
        "habitat": species.habitat,
        "distribution": species.distribution,
        "traits": species.traits,
        "diet": species.diet,
        "activity": species.activity,
        "ecology_value": species.ecology_value,
        "threats": species.threats,
        "conservation": species.conservation,
        "facts": species.facts or [],
        "source_notes": species.source_notes or [],
    }
