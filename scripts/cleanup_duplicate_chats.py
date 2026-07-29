from __future__ import annotations

from collections import defaultdict

from sqlalchemy import select

from backend.core.database import SessionLocal
from backend.models import ChatMessage, ChatThread


def member_key(thread: ChatThread) -> tuple[int, ...]:
    return tuple(sorted(int(item) for item in (thread.member_ids or [])))


def main() -> None:
    removed = 0
    moved_messages = 0
    with SessionLocal() as db:
        groups: dict[tuple[int, ...], list[ChatThread]] = defaultdict(list)
        threads = db.scalars(select(ChatThread).where(ChatThread.thread_type == "direct")).all()
        for thread in threads:
            key = member_key(thread)
            if len(key) >= 2:
                groups[key].append(thread)

        for items in groups.values():
            if len(items) <= 1:
                continue
            items.sort(key=lambda item: (item.updated_at, item.id), reverse=True)
            keep = items[0]
            for duplicate in items[1:]:
                messages = db.scalars(select(ChatMessage).where(ChatMessage.thread_id == duplicate.id)).all()
                for message in messages:
                    message.thread_id = keep.id
                    moved_messages += 1
                db.delete(duplicate)
                removed += 1
            keep.member_ids = list(member_key(keep))
        db.commit()

    print({"duplicate_threads_removed": removed, "messages_moved": moved_messages})


if __name__ == "__main__":
    main()
