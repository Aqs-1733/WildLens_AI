from __future__ import annotations

from backend.core.database import Base, SessionLocal, engine
from backend.seed import seed_database


def main() -> None:
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        seed_database(db)
    print("Database schema is compatible and seed data is ready.")


if __name__ == "__main__":
    main()
