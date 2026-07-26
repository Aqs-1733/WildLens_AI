from __future__ import annotations

import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models import DiscoveryRecord, Species, SystemSetting, User, UserCollection, UserPreference, now_utc


def _memory_row(db: Session, user_id: int) -> SystemSetting:
    key = f"user_memory:{user_id}"
    row = db.scalar(select(SystemSetting).where(SystemSetting.key == key))
    if not row:
        row = SystemSetting(
            key=key,
            value={"interests": [], "species": [], "questions": [], "locations": []},
            description="Per-user natural science interests and QA memory.",
        )
        db.add(row)
        db.flush()
    return row


def _append_unique(values: list[str], new_values: list[str], limit: int = 24) -> list[str]:
    output: list[str] = []
    for item in [*values, *new_values]:
        cleaned = str(item or "").strip()
        if cleaned and cleaned not in output:
            output.append(cleaned)
    return output[-limit:]


def _keywords(text: str) -> list[str]:
    candidates = re.findall(r"[\u4e00-\u9fff]{2,8}|[A-Z][a-z]+(?:\s+[a-z]+){1,2}", text or "")
    stop = {"什么", "怎么", "为什么", "可以", "这个", "那个", "请问", "自然", "科普", "识别"}
    return [item for item in candidates if item not in stop][:12]


def memory_context(db: Session, user: User) -> str:
    row = _memory_row(db, user.id)
    value = row.value or {}
    pref = db.scalar(select(UserPreference).where(UserPreference.user_id == user.id))
    recent_records = db.scalars(
        select(DiscoveryRecord)
        .where(DiscoveryRecord.user_id == user.id)
        .order_by(DiscoveryRecord.created_at.desc())
        .limit(8)
    ).all()
    collection = db.scalars(
        select(UserCollection)
        .where(UserCollection.user_id == user.id)
        .order_by(UserCollection.last_discovered_at.desc())
        .limit(8)
    ).all()
    species_names = [
        item.species.common_name or item.species.scientific_name
        for item in collection
        if item.species
    ]
    record_names = [item.title or item.scientific_name for item in recent_records]
    locations = []
    if pref:
        locations.extend([pref.home_location, *(pref.frequent_locations or [])])
    locations.extend(value.get("locations") or [])
    return (
        f"用户昵称：{user.display_name}；简介：{user.bio or '未填写'}。\n"
        f"常去地点：{'、'.join([item for item in locations if item]) or '未填写'}。\n"
        f"长期兴趣：{'、'.join(value.get('interests') or []) or '暂无'}。\n"
        f"最近问过：{'、'.join(value.get('questions') or []) or '暂无'}。\n"
        f"图鉴物种：{'、'.join(_append_unique(value.get('species') or [], species_names + record_names, 18)) or '暂无'}。"
    )


def remember_interaction(
    db: Session,
    user: User,
    *,
    question: str,
    answer: str = "",
    species: Species | None = None,
    location: str = "",
) -> None:
    row = _memory_row(db, user.id)
    value: dict[str, Any] = dict(row.value or {})
    value["questions"] = _append_unique(value.get("questions") or [], [question[:60]], 20)
    value["interests"] = _append_unique(value.get("interests") or [], _keywords(f"{question} {answer}"), 30)
    if species:
        value["species"] = _append_unique(
            value.get("species") or [],
            [species.common_name, species.scientific_name],
            30,
        )
    if location:
        value["locations"] = _append_unique(value.get("locations") or [], [location], 20)
    row.value = value
    row.updated_at = now_utc()
