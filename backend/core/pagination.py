from __future__ import annotations

from typing import Any, Sequence, TypeVar

from fastapi import Response
from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

T = TypeVar("T")


def page_window(page: int = 1, limit: int = 30, *, max_limit: int = 100) -> tuple[int, int, int]:
    safe_page = max(1, int(page or 1))
    safe_limit = max(1, min(int(limit or 30), max_limit))
    return safe_page, safe_limit, (safe_page - 1) * safe_limit


def add_pagination_headers(response: Response, *, total: int, page: int, limit: int) -> None:
    response.headers["X-Total-Count"] = str(total)
    response.headers["X-Page"] = str(page)
    response.headers["X-Limit"] = str(limit)
    response.headers["X-Has-More"] = "true" if page * limit < total else "false"


def paginate_scalars(
    db: Session,
    stmt: Select[Any],
    *,
    response: Response,
    page: int = 1,
    limit: int = 30,
    max_limit: int = 100,
) -> Sequence[T]:
    safe_page, safe_limit, offset = page_window(page, limit, max_limit=max_limit)
    total = db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
    add_pagination_headers(response, total=int(total), page=safe_page, limit=safe_limit)
    return db.scalars(stmt.limit(safe_limit).offset(offset)).all()
