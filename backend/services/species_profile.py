from __future__ import annotations

import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models import Detection, Species
from backend.services.ai import _extract_json, ark_ai
from backend.services.taxon_names import has_cjk, resolve_chinese_name
from backend.services.text_clean import clean_text, is_garbled

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
    "Panthera tigris altaica": {
        "common_name_zh": "东北虎",
        "english_name": "Amur tiger",
        "category": "mammal",
        "rarity": 5,
        "protection_level": "国家一级保护动物",
        "traits": "体型巨大，冬季毛色较浅，黑色横纹稀疏，头圆耳短，四肢粗壮有力。",
        "habitat": "主要栖息在针阔混交林、山地森林和河谷林地，依赖连续森林和充足猎物。",
        "distribution": "中国东北、俄罗斯远东及朝鲜半岛北部有分布，中国野外种群主要在东北虎豹国家公园一带。",
        "diet": "以鹿、野猪等中大型有蹄类为主，也会捕食小型哺乳动物。",
        "activity": "多在晨昏和夜间活动，单独生活，领域范围很大。",
        "ecology_value": "作为顶级捕食者调节有蹄类数量，维持森林食物网稳定。",
        "threats": "栖息地破碎化、猎物减少和人兽冲突是主要威胁。",
        "conservation": "保护连续森林廊道，减少盗猎和干扰，野外观察不要公开精确位置。",
        "facts": ["虎纹如同指纹，可辅助个体识别。", "冬季毛发更厚，能适应严寒环境。"],
    },
    "Panthera tigris tigris": {
        "common_name_zh": "孟加拉虎",
        "english_name": "Bengal tiger",
        "category": "mammal",
        "rarity": 5,
        "protection_level": "濒危大型猫科动物",
        "traits": "体型大，橙黄色被毛上有清晰黑色条纹，面部白斑明显，雄性通常更粗壮。",
        "habitat": "栖息在热带和亚热带森林、草原、红树林和湿地边缘。",
        "distribution": "主要分布于印度、孟加拉国、尼泊尔和不丹等南亚地区。",
        "diet": "以鹿类、野猪、水牛等中大型猎物为主，偶尔捕食较小动物。",
        "activity": "多为独居，晨昏和夜间活动较多，善于利用植被掩护接近猎物。",
        "ecology_value": "维持大型草食动物种群结构，是南亚森林和湿地生态系统的重要旗舰物种。",
        "threats": "栖息地缩小、猎物减少、盗猎和人虎冲突影响种群恢复。",
        "conservation": "保护栖息地和迁移廊道，减少人虎冲突；不要追逐、投喂或公开精确位置。",
        "facts": ["孙德尔本斯红树林中也有孟加拉虎活动。", "条纹帮助它在草丛和林下阴影中隐蔽。"],
    },
    "Panthera tigris": {"common_name_zh": "虎", "english_name": "Tiger", "category": "mammal", "rarity": 5, "protection_level": "国家一级保护动物"},
    "Panthera pardus": {"common_name_zh": "金钱豹", "english_name": "Leopard", "category": "mammal", "rarity": 5, "protection_level": "国家一级保护动物"},
    "Elephas maximus": {"common_name_zh": "亚洲象", "english_name": "Asian elephant", "category": "mammal", "rarity": 5, "protection_level": "国家一级保护动物"},
    "Passer montanus": {"common_name_zh": "树麻雀", "english_name": "Eurasian tree sparrow", "category": "bird", "rarity": 1, "protection_level": "常见鸟类"},
    "Passer montanus kansuensis": {"common_name_zh": "树麻雀甘肃亚种", "english_name": "Eurasian tree sparrow", "category": "bird", "rarity": 2, "protection_level": "常见鸟类"},
    "Nycticorax nycticorax": {
        "common_name_zh": "夜鹭",
        "english_name": "Black-crowned night heron",
        "category": "bird",
        "rarity": 2,
        "protection_level": "未列入本地重点保护名录",
        "traits": "成鸟头顶和背部黑色，身体灰白，眼睛红色，繁殖期头后有细长白色饰羽；幼鸟褐色并有浅色斑纹。",
        "habitat": "常见于湖泊、河流、湿地、公园水域和鱼塘附近，喜欢有树木或芦苇遮蔽的水边环境。",
        "distribution": "广泛分布于中国多地以及欧亚、非洲和美洲部分地区，在许多城市湿地也能见到。",
        "diet": "以鱼、蛙、昆虫、甲壳类和小型水生动物为食。",
        "activity": "傍晚和夜间活动更频繁，白天常在树上或岸边休息。",
        "ecology_value": "是湿地食物网中的中小型捕食者，可反映水域生境质量。",
        "threats": "湿地退化、水体污染和繁殖地干扰会影响其栖息。",
        "conservation": "观察时保持距离，不惊扰集群栖息点和繁殖地。",
        "facts": ["夜鹭的英文名来自其偏夜行的习性。", "幼鸟外观与成鸟差异很大，容易被误认。"],
    },
    "Nycticorax nycticorax nycticorax": {"common_name_zh": "夜鹭指名亚种", "english_name": "Black-crowned night heron", "category": "bird", "rarity": 2, "protection_level": "未列入本地重点保护名录"},
    "Ginkgo biloba": {"common_name_zh": "银杏", "english_name": "Ginkgo", "category": "plant", "rarity": 4, "protection_level": "国家一级重点保护野生植物"},
}


def looks_latin(value: str) -> bool:
    return bool(LATIN_RE.match((value or "").strip()))


def is_specific_species_name(value: str) -> bool:
    cleaned = (value or "").strip()
    vague = {"待确认目标", "待确认植物", "疑似雾或低能见度", "疑似火焰色区域", "未知物种", "自然现象"}
    return bool(cleaned and cleaned not in vague and not cleaned.startswith(("疑似", "待确认")))


def _known_seed(scientific_name: str, category: str, common_hint: str = "") -> dict[str, Any]:
    base = dict(KNOWN_PROFILES.get(scientific_name, {}))
    if not base:
        base_name = " ".join(scientific_name.split()[:2])
        base = dict(KNOWN_PROFILES.get(base_name, {}))
    resolved = resolve_chinese_name(None, scientific_name, common_hint, category)
    common = (
        base.get("common_name_zh")
        or (resolved if has_cjk(resolved) else "")
        or clean_text(common_hint)
        or scientific_name
    )
    return {
        "common_name_zh": common,
        "scientific_name": scientific_name,
        "english_name": base.get("english_name", ""),
        "category": base.get("category", category or "unknown"),
        "protection_level": base.get("protection_level", "未列入本地重点保护名录"),
        "rarity": int(base.get("rarity", 2)),
        "traits": "",
        "habitat": "",
        "distribution": "",
        "diet": "",
        "activity": "",
        "ecology_value": "",
        "threats": "",
        "conservation": "",
        "facts": [],
    }


async def _ai_profile(scientific_name: str, category: str, common_hint: str = "") -> dict[str, Any] | None:
    if not ark_ai.enabled:
        return None
    prompt = (
        "请根据公开自然史资料、常见权威名录和稳定物种知识，生成中文物种档案。"
        "必须输出严格 JSON，不要 Markdown，不要 JSON 之外文字。"
        "中文名必须具体，不要写“某种鸟”“待确认”“疑似”。"
        "如果是亚种或变种，中文名要体现亚种/变种。"
        "不要编造保护级别；不确定时写“未列入本地重点保护名录”或说明需以当地名录为准。"
        "字段：common_name_zh, scientific_name, english_name, category, protection_level, rarity,"
        "traits, habitat, distribution, diet, activity, ecology_value, threats, conservation, facts。"
        "rarity 为 1-5；facts 为 2-4 条中文短句。"
        f"\n学名：{scientific_name}\n当前类别：{category or 'unknown'}\n名称线索：{common_hint or '无'}"
    )
    answer = await ark_ai.chat("你是中文物种百科编辑，只输出 JSON。", prompt, temperature=0.05, max_tokens=900, timeout_seconds=60.0)
    if not answer:
        return None
    data = _extract_json(answer)
    return data if isinstance(data, dict) else None


def _unique_common_name(db: Session, common_name: str, scientific_name: str) -> str:
    common_name = clean_text(common_name, scientific_name)[:90] or scientific_name[:90]
    existing = db.scalar(select(Species).where(Species.common_name == common_name))
    if not existing or existing.scientific_name == scientific_name:
        return common_name
    suffix = scientific_name[: max(1, 96 - len(common_name))]
    return f"{common_name}（{suffix}）"[:100]


def species_needs_profile_refresh(species: Species) -> bool:
    notes = " ".join(str(item) for item in (species.source_notes or []))
    if "ARK 物种百科已生成" in notes and not any(is_garbled(getattr(species, field, "")) for field in _PROFILE_FIELDS):
        return False
    fields = " ".join(str(getattr(species, field, "") or "") for field in _PROFILE_FIELDS)
    markers = (
        "本地 BioCLIP", "具体分类单元", "建议结合", "需要结合", "待补充", "首次打开",
        "逐步完善", "分布信息需要", "食性或营养方式需要", "当前本地", "暂无",
    )
    if any(marker in fields for marker in markers):
        return True
    if any(is_garbled(getattr(species, field, "")) for field in ("common_name", "protection_level", *_PROFILE_FIELDS)):
        return True
    required = [species.traits, species.habitat, species.distribution, species.diet, species.activity, species.ecology_value]
    return any(not str(item or "").strip() for item in required)


_PROFILE_FIELDS = ("traits", "habitat", "distribution", "diet", "activity", "ecology_value", "threats", "conservation")


def _apply_profile_to_species(species: Species, profile: dict[str, Any], mode: str) -> None:
    species.common_name = clean_text(profile.get("common_name_zh"), species.common_name)[:100]
    species.english_name = clean_text(profile.get("english_name"), species.english_name)[:150]
    species.category = clean_text(profile.get("category"), species.category or "unknown")[:40]
    species.kingdom = "Plantae" if species.category in {"plant", "angiosperm", "gymnosperm", "fern", "moss", "algae"} else "Animalia"
    species.protection_level = clean_text(profile.get("protection_level"), "未列入本地重点保护名录")[:80]
    try:
        species.rarity = max(1, min(5, int(profile.get("rarity") or species.rarity or 2)))
    except (TypeError, ValueError):
        species.rarity = species.rarity or 2
    species.color = CATEGORY_COLORS.get(species.category, CATEGORY_COLORS["unknown"])
    for field in _PROFILE_FIELDS:
        value = clean_text(profile.get(field))
        if value:
            setattr(species, field, value)
    facts = profile.get("facts")
    if isinstance(facts, list):
        species.facts = [clean_text(item) for item in facts if clean_text(item)][:6]
    if not species.facts:
        species.facts = [f"学名：{species.scientific_name}", "建议结合地点、季节和多角度照片复核识别。"]
    species.taxonomy = {"scientific_name": species.scientific_name}
    species.source_notes = [
        "ARK 物种百科已生成并缓存。" if mode == "ark" else "本地物种档案已创建，等待下一次联网 AI 资料补全。"
    ]


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
    if species and not force and not species_needs_profile_refresh(species):
        return species

    profile = await _ai_profile(scientific_name, category, common_hint)
    mode = "ark" if profile else "local"
    if not profile:
        profile = _known_seed(scientific_name, category, common_hint)
        common = profile["common_name_zh"]
        profile.update(
            {
                "traits": f"{common}（{scientific_name}）已加入图鉴，详细资料将在 AI 百科生成成功后自动缓存。",
                "habitat": "资料生成中。",
                "distribution": "资料生成中。",
                "diet": "资料生成中。",
                "activity": "资料生成中。",
                "ecology_value": "资料生成中。",
                "threats": "资料生成中。",
                "conservation": "观察时请减少干扰，不公开珍稀物种精确位置。",
            }
        )

    common_name = clean_text(profile.get("common_name_zh"), common_hint or scientific_name)
    preferred_common = _known_seed(scientific_name, category, common_hint)["common_name_zh"]
    if has_cjk(preferred_common):
        common_name = preferred_common
    elif looks_latin(common_name) or is_garbled(common_name):
        common_name = preferred_common
    profile["common_name_zh"] = _unique_common_name(db, common_name, scientific_name)
    profile["scientific_name"] = scientific_name
    profile["category"] = clean_text(profile.get("category"), category or "unknown")

    if not species:
        species = Species(
            common_name=profile["common_name_zh"],
            scientific_name=scientific_name,
            english_name=clean_text(profile.get("english_name")),
            category=profile["category"],
            color=CATEGORY_COLORS.get(profile["category"], CATEGORY_COLORS["unknown"]),
        )
        db.add(species)
        db.flush()
    _apply_profile_to_species(species, profile, mode)
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
        return await ensure_species_profile(db, scientific_name=scientific_name, category=category, common_hint=species_name)
    if species_name:
        found = db.scalar(
            select(Species).where(
                (Species.common_name == species_name)
                | (Species.scientific_name == species_name)
                | (Species.english_name == species_name)
            )
        )
        if found:
            if species_needs_profile_refresh(found):
                return await ensure_species_profile(db, scientific_name=found.scientific_name, category=found.category, common_hint=found.common_name)
            return found
    if ark_ai.enabled and species_name:
        prompt = (
            "把用户输入的中文或英文自然名称解析为最可能的具体物种。"
            "只输出 JSON：common_name_zh, scientific_name, english_name, category。"
            "如果不能确定到种，也尽量给常见且具体的分类，不要输出未知。"
            f"\n用户输入：{species_name}"
        )
        answer = await ark_ai.chat("只输出 JSON。", prompt, temperature=0.05, max_tokens=300, timeout_seconds=30.0)
        data = _extract_json(answer or "") if answer else None
        if isinstance(data, dict):
            scientific_name = clean_text(data.get("scientific_name"))
            category = clean_text(data.get("category"), category)
            species_name = clean_text(data.get("common_name_zh"), species_name)
    if scientific_name:
        return await ensure_species_profile(db, scientific_name=scientific_name, category=category, common_hint=species_name)
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
