from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

BEIJING_TZ = timezone(timedelta(hours=8), "Asia/Shanghai")


def as_beijing_time(value: datetime) -> datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(BEIJING_TZ)


def beijing_isoformat(value: datetime) -> str:
    return as_beijing_time(value).isoformat()
