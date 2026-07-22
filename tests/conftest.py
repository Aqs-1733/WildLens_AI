from __future__ import annotations

import gc
import os
from pathlib import Path

TEST_DB = Path(__file__).resolve().parent / "wildlens_test.db"
os.environ["APP_ENV"] = "test"
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB.as_posix()}"
os.environ["ARK_API_KEY"] = ""
os.environ["BIOCLIP_ENABLED"] = "false"
os.environ["LANGCHAIN_TRACING_V2"] = "false"
os.environ["SECRET_KEY"] = "pytest-secret-key-at-least-thirty-two-bytes-long"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import close_all_sessions

from backend.core.database import Base, engine
from backend.main import app


def cleanup() -> None:
    close_all_sessions()
    engine.dispose()
    gc.collect()
    TEST_DB.unlink(missing_ok=True)


@pytest.fixture(scope="session")
def client():
    cleanup()
    Base.metadata.create_all(bind=engine)
    with TestClient(app) as test_client:
        yield test_client
    cleanup()


@pytest.fixture(scope="session")
def public_headers(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/auth/login", json={"username": "explorer", "password": "Wild1234!"}
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture(scope="session")
def regulator_headers(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/auth/login", json={"username": "ranger", "password": "Wild1234!"}
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}
