from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models import Detection, SpeciesGuideCache, now_utc
from backend.services.ai import _extract_json, ark_ai
from backend.services.taxon_names import (
    category_zh,
    has_cjk,
    localize_candidate,
    normalize_category,
    resolve_chinese_name,
)
from backend.services.text_clean import clean_text, is_garbled

GUIDE_KEYS = (
    "summary",
    "appearance",
    "habitat",
    "behavior",
    "similar_species",
    "observation_tips",
    "caution",
)


def _fallback_guide(label: str, scientific_name: str, category: str) -> dict[str, str]:
    category_name = category_zh(category)
    display = label or scientific_name or category_name
    return {
        "summary": f"{display}是本次识别得到的候选，分类为{category_name}。建议结合地点、季节和多角度照片复核。",
        "appearance": "重点观察体型、颜色、斑纹、喙/叶/花/果等结构，以及主体与背景的比例关系。",
        "habitat": "栖息或生长环境需要结合拍摄地点、季节和周边环境确认。",
        "behavior": "单张照片只能说明可见姿态，不能把瞬间动作直接等同于稳定行为。",
        "similar_species": "相近物种需要比较关键形态、分类关系、分布区域和多角度照片。",
        "observation_tips": "建议补拍正面、侧面、整体与细节照片；观察动物时不要靠近、投喂或惊扰。",
        "caution": "低置信度、幼体、局部照片或相似物种需要人工复核；珍稀物种不要公开精确位置。",
    }


def _clean_guide(value: dict[str, Any], label: str, scientific_name: str, category: str) -> dict[str, str]:
    fallback = _fallback_guide(label, scientific_name, category)
    output: dict[str, str] = {}
    for key in GUIDE_KEYS:
        text = clean_text(value.get(key), "")
        output[key] = text if text and not is_garbled(text) else fallback[key]
    return output


def _candidate_identity(item: dict[str, Any]) -> str:
    return str(item.get("scientific_name") or item.get("name") or item.get("common_name") or "").strip()


def _clean_localized_alternatives(
    db: Session,
    detection: Detection,
    ai_items: Any,
) -> list[dict[str, Any]]:
    source_items = [item for item in (detection.alternatives or []) if isinstance(item, dict)]
    by_id = {_candidate_identity(item): dict(item) for item in source_items if _candidate_identity(item)}
    if isinstance(ai_items, list):
        for item in ai_items:
            if not isinstance(item, dict):
                continue
            identity = _candidate_identity(item)
            if not identity:
                continue
            original = by_id.get(identity, {})
            original.update(item)
            by_id[identity] = original
    output: list[dict[str, Any]] = []
    for item in list(by_id.values())[:8]:
        localized = localize_candidate(db, item)
        zh = str(localized.get("common_name_zh") or localized.get("display_name") or "").strip()
        if zh and has_cjk(zh):
            localized["name"] = zh
            localized["display_name"] = zh
        output.append(localized)
    return output


async def guide_for_detection(db: Session, detection: Detection) -> dict[str, Any]:
    scientific_name = str(detection.scientific_name or "").strip()
    category = normalize_category(detection.category)
    label = resolve_chinese_name(db, scientific_name, detection.label, category)
    cache_key = scientific_name or f"{category}:{label}"
    cached = db.scalar(select(SpeciesGuideCache).where(SpeciesGuideCache.scientific_name == cache_key))
    if cached and cached.content and (cached.mode == "ark" or not ark_ai.enabled):
        raw_content = dict(cached.content)
        content = _clean_guide(raw_content, label, scientific_name, category)
        return {
            "detection_id": detection.id,
            "species_id": detection.species_id,
            "label": cached.common_name_zh or label,
            "scientific_name": scientific_name,
            "category": category,
            "category_zh": category_zh(category),
            "confidence": detection.confidence,
            "mode": cached.mode,
            "common_name_zh": cached.common_name_zh or label,
            "localized_alternatives": _clean_localized_alternatives(
                db, detection, raw_content.get("localized_alternatives")
            ),
            **content,
        }

    system = (
        "你是“识境”的中文自然科普编辑。只输出合法 JSON，不要 Markdown。"
        "每个字段 1-2 句中文，准确、具体，不编造保护级别。"
        "必须把英文名或拉丁学名规范成常见中文名，中文名放在 common_name_zh。"
        "若资料不确定，要说需要结合当地名录确认，不要写成确定事实。"
    )
    user = (
        "为这个识别结果生成简短中文科普。"
        "JSON 字段必须为 common_name_zh, summary, appearance, habitat, behavior, similar_species, "
        "observation_tips, caution, localized_alternatives。\n"
        "localized_alternatives 是数组，每项包含 scientific_name, common_name_zh, name, confidence；"
        "name 必须优先填中文名。\n"
        f"中文名线索：{label}\n"
        f"学名：{scientific_name or '未提供'}\n"
        f"类别：{category_zh(category)}\n"
        f"置信度：{detection.confidence:.1%}\n"
        f"模型解释：{(detection.explanation or '无')[:500]}\n"
        f"候选：{json.dumps(detection.alternatives or [], ensure_ascii=False)[:500]}"
    )
    answer = await ark_ai.chat(system, user, temperature=0.15, max_tokens=700, timeout_seconds=60.0)
    parsed = _extract_json(answer or "") if answer else None
    if answer and not parsed:
        parsed = {"summary": answer.strip()[:1200]}
    if isinstance(parsed, dict):
        parsed_label = clean_text(parsed.get("common_name_zh"), "")
        if parsed_label and has_cjk(parsed_label) and not is_garbled(parsed_label):
            label = parsed_label
    mode = "ark" if answer else "local"
    content = _clean_guide(parsed or {}, label, scientific_name, category)
    localized_alternatives = _clean_localized_alternatives(
        db, detection, (parsed or {}).get("localized_alternatives") if isinstance(parsed, dict) else None
    )
    content_for_cache: dict[str, Any] = dict(content)
    content_for_cache["localized_alternatives"] = localized_alternatives

    if cached:
        cached.common_name_zh = label
        cached.category = category
        cached.content = content_for_cache
        cached.mode = mode
        cached.updated_at = now_utc()
    else:
        cached = SpeciesGuideCache(
            scientific_name=cache_key,
            common_name_zh=label,
            category=category,
            content=content_for_cache,
            mode=mode,
            updated_at=now_utc(),
        )
        db.add(cached)
    db.commit()
    return {
        "detection_id": detection.id,
        "species_id": detection.species_id,
        "label": label,
        "scientific_name": scientific_name,
        "category": category,
        "category_zh": category_zh(category),
        "confidence": detection.confidence,
        "mode": mode,
        "common_name_zh": label,
        "localized_alternatives": localized_alternatives,
        **content,
    }
