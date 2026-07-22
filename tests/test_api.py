from __future__ import annotations

import io
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient
from PIL import Image

from backend.services.ai import ark_ai


def test_health_and_auth(client: TestClient):
    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"

    registration = client.post(
        "/api/auth/register",
        json={
            "username": "newobserver",
            "email": "newobserver@example.com",
            "password": "Observer123!",
            "display_name": "新观察员",
            "role": "public",
        },
    )
    assert registration.status_code == 200, registration.text
    assert registration.json()["access_token"]

    denied = client.post(
        "/api/auth/register",
        json={
            "username": "badregulator",
            "email": "badregulator@example.com",
            "password": "Observer123!",
            "display_name": "无邀请码监管员",
            "role": "regulator",
            "invite_code": "wrong",
        },
    )
    assert denied.status_code == 403


def test_public_dashboard_species_and_collection(
    client: TestClient, public_headers: dict[str, str]
):
    dashboard = client.get("/api/dashboard", headers=public_headers)
    assert dashboard.status_code == 200
    assert dashboard.json()["stats"]["species_total"] >= 15

    species = client.get("/api/species", headers=public_headers)
    assert species.status_code == 200
    rows = species.json()
    assert any(item["scientific_name"] == "Cervus nippon" for item in rows)
    assert any(item["kingdom"] == "Plantae" for item in rows)

    collection = client.get("/api/species/collection", headers=public_headers)
    assert collection.status_code == 200
    assert collection.json() == []


def test_video_overlay_data_and_events(client: TestClient, public_headers: dict[str, str]):
    jobs = client.get("/api/videos/jobs", headers=public_headers)
    assert jobs.status_code == 200
    completed = next(item for item in jobs.json() if item["status"] == "completed")
    assert completed["media"]["playback_url"].endswith(".mp4")

    detections = client.get(
        f"/api/videos/jobs/{completed['id']}/detections", headers=public_headers
    )
    assert detections.status_code == 200
    body = detections.json()
    assert len(body) >= 9
    assert all("bbox" in item and "scientific_name" in item for item in body)
    assert any(item["label"] == "梅花鹿" for item in body)

    tracks = client.get(f"/api/videos/jobs/{completed['id']}/tracks", headers=public_headers)
    assert tracks.status_code == 200
    assert tracks.json()
    assert all(item["keyframes"] for item in tracks.json())

    events = client.get(f"/api/videos/jobs/{completed['id']}/events", headers=public_headers)
    assert events.status_code == 200
    assert events.json()[0]["severity"] == "low"

    frame = client.get(
        f"/api/videos/jobs/{completed['id']}/frame?timestamp_ms=3200", headers=public_headers
    )
    assert frame.status_code == 200, frame.text
    assert frame.json()["url"].endswith(".jpg")


def test_species_context_qa(client: TestClient, public_headers: dict[str, str], monkeypatch):
    species = client.get("/api/species?q=梅花鹿", headers=public_headers).json()[0]
    job_id = client.get("/api/videos/jobs", headers=public_headers).json()[0]["id"]
    monkeypatch.setattr(
        ark_ai,
        "chat",
        AsyncMock(
            return_value="视频事实与物种知识需要分开判断：梅花鹿可能处于警戒状态，但仍需结合连续帧确认。"
        ),
    )
    response = client.post(
        "/api/qa/ask",
        headers=public_headers,
        json={
            "question": "视频里的梅花鹿为什么可能停在原地？",
            "species_id": species["id"],
            "job_id": job_id,
        },
    )
    assert response.status_code == 200, response.text
    answer = response.json()
    assert "梅花鹿" in answer["answer"]
    assert answer["mode"] == "ark"
    assert answer["fallback_reason"] is None

    follow_up = client.post(
        "/api/qa/ask",
        headers=public_headers,
        json={
            "question": "那它和周围环境有什么关系？",
            "species_id": species["id"],
            "job_id": job_id,
            "conversation_id": answer["conversation_id"],
        },
    )
    assert follow_up.status_code == 200, follow_up.text
    assert follow_up.json()["conversation_id"] == answer["conversation_id"]

    conversations = client.get("/api/qa/conversations", headers=public_headers)
    assert conversations.status_code == 200
    assert any(item["id"] == answer["conversation_id"] for item in conversations.json())

    messages = client.get(
        f"/api/qa/conversations/{answer['conversation_id']}/messages",
        headers=public_headers,
    )
    assert messages.status_code == 200
    rows = messages.json()
    assert [item["role"] for item in rows] == ["user", "assistant", "user", "assistant"]
    assert rows[0]["content"] == "视频里的梅花鹿为什么可能停在原地？"
    assert rows[2]["content"] == "那它和周围环境有什么关系？"


def test_learning_and_social(client: TestClient, public_headers: dict[str, str]):
    tasks = client.get("/api/species/learning/tasks", headers=public_headers)
    assert tasks.status_code == 200
    assert len(tasks.json()) >= 4

    friends = client.get("/api/social/friends", headers=public_headers)
    assert friends.status_code == 200
    assert any(item["username"] == "leaf" for item in friends.json()["friends"])

    feed = client.get("/api/social/feed", headers=public_headers)
    assert feed.status_code == 200
    assert len(feed.json()) >= 1

    post = client.post(
        "/api/social/posts",
        headers=public_headers,
        json={"content": "pytest观察记录：保护栖息地，从尊重事实开始。", "visibility": "friends"},
    )
    assert post.status_code == 200
    liked = client.post(f"/api/social/posts/{post.json()['id']}/like", headers=public_headers)
    assert liked.status_code == 200
    assert liked.json()["likes"] == 1


def test_regulator_permissions_review_and_datasets(
    client: TestClient,
    public_headers: dict[str, str],
    regulator_headers: dict[str, str],
):
    assert client.get("/api/alerts", headers=public_headers).status_code == 403

    alerts = client.get("/api/alerts", headers=regulator_headers)
    assert alerts.status_code == 200
    assert alerts.json()

    queue = client.get("/api/review/queue", headers=regulator_headers)
    assert queue.status_code == 200
    item = queue.json()[0]
    updated = client.patch(
        f"/api/review/detections/{item['id']}",
        headers=regulator_headers,
        json={
            "species_id": item.get("species_id"),
            "label": item["label"],
            "scientific_name": item["scientific_name"],
            "category": item["category"],
            "status": "confirmed",
            "note": "pytest人工复核",
        },
    )
    assert updated.status_code == 200

    models = client.get("/api/system/models", headers=regulator_headers)
    datasets = client.get("/api/system/datasets", headers=regulator_headers)
    assert models.status_code == 200
    assert datasets.status_code == 200
    assert any(item["id"] == "wcs-camera-traps" for item in datasets.json())


def test_pdf_report(client: TestClient, regulator_headers: dict[str, str]):
    jobs = client.get("/api/videos/jobs", headers=regulator_headers).json()
    response = client.get(f"/api/reports/jobs/{jobs[0]['id']}", headers=regulator_headers)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/pdf")
    assert response.content.startswith(b"%PDF")


def test_photo_identification_history_feedback_and_share(
    client: TestClient, public_headers: dict[str, str]
):
    image = Image.new("RGB", (720, 540), (44, 132, 72))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    response = client.post(
        "/api/identify/photo",
        headers=public_headers,
        files={"file": ("leaf.png", buffer.getvalue(), "image/png")},
        data={"hint": "公园植物近景"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["objects"]
    assert body["model_mode"] in {
        "heuristic",
        "ark",
        "speciesnet",
        "bioclip",
        "speciesnet+bioclip",
        "onnx+heuristic",
    }
    first = body["objects"][0]
    assert {"x", "y", "width", "height"}.issubset(first["bbox"])

    history_before = client.get("/api/identify/history", headers=public_headers)
    assert history_before.status_code == 200
    assert len(history_before.json()) == 1
    assert history_before.json()[0]["detection_id"] == first["id"]
    assert history_before.json()[0]["image_url"]

    feedback = client.post(
        f"/api/identify/detections/{first['id']}/feedback",
        headers=public_headers,
        json={
            "is_correct": False,
            "corrected_label": "测试银杏",
            "corrected_scientific_name": "Ginkgo biloba",
            "note": "pytest修正",
        },
    )
    assert feedback.status_code == 200, feedback.text

    saved = client.post(
        "/api/identify/observations",
        headers=public_headers,
        json={
            "detection_id": first["id"],
            "note": "pytest真实观察",
            "latitude": 39.9042,
            "longitude": 116.4074,
            "province": "北京市",
            "city": "北京市",
            "location_source": "gps",
            "privacy_level": "precise",
        },
    )
    assert saved.status_code == 200, saved.text

    history = client.get("/api/identify/history", headers=public_headers)
    assert history.status_code == 200
    assert len(history.json()) == 1
    record = history.json()[0]
    assert record["title"] == "测试银杏"
    assert record["scientific_name"] == "Ginkgo biloba"

    map_rows = client.get("/api/identify/observations/map?layer=plant", headers=public_headers)
    assert map_rows.status_code == 200
    assert map_rows.json()

    post = client.post(
        "/api/social/posts",
        headers=public_headers,
        json={
            "discovery_id": record["id"],
            "content": "pytest分享识别发现",
            "image_url": record["image_url"],
            "visibility": "public",
        },
    )
    assert post.status_code == 200, post.text
