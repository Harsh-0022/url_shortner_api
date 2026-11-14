from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from valkey import Valkey

from url_shortener import repository
from url_shortener.service import BASE62_ALPHABET, generate_base62_code


def test_health_check(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "healthy",
        "database": "connected",
        "valkey": "connected",
    }


def test_generate_short_code_properties() -> None:
    code = generate_base62_code(8)
    assert len(code) == 8
    assert all(ch in BASE62_ALPHABET for ch in code)


def test_create_redirect_and_stats_flow(client: TestClient) -> None:
    create_resp = client.post(
        "/api/v1/links",
        json={"target_url": "https://www.python.org/downloads/"},
    )
    assert create_resp.status_code == 201
    data = create_resp.json()
    short_code = data["short_code"]
    assert len(short_code) == 6
    assert data["target_url"] == "https://www.python.org/downloads/"

    stats_before = client.get(f"/api/v1/links/{short_code}/stats")
    assert stats_before.status_code == 200
    assert stats_before.json()["clicks"] == 0
    assert stats_before.json()["is_expired"] is False

    for _ in range(2):
        redirect_resp = client.get(f"/{short_code}", follow_redirects=False)
        assert redirect_resp.status_code == 307
        assert redirect_resp.headers["location"] == "https://www.python.org/downloads/"

    stats_after = client.get(f"/api/v1/links/{short_code}/stats")
    assert stats_after.status_code == 200
    assert stats_after.json()["clicks"] == 2


def test_custom_alias_and_duplicate_conflict(client: TestClient) -> None:
    payload = {"target_url": "https://docs.python.org/3/", "custom_alias": "py-docs"}
    first = client.post("/api/v1/links", json=payload)
    assert first.status_code == 201
    assert first.json()["short_code"] == "py-docs"

    duplicate = client.post("/api/v1/links", json=payload)
    assert duplicate.status_code == 409


def test_reserved_alias_rejected(client: TestClient) -> None:
    response = client.post(
        "/api/v1/links",
        json={"target_url": "https://example.com", "custom_alias": "health"},
    )
    assert response.status_code == 422


def test_invalid_url_rejected(client: TestClient) -> None:
    response = client.post(
        "/api/v1/links",
        json={"target_url": "not-a-valid-url"},
    )
    assert response.status_code == 422


def test_redirect_loop_rejected(client: TestClient) -> None:
    response = client.post(
        "/api/v1/links",
        json={"target_url": "http://localhost:8000/some-path"},
    )
    assert response.status_code == 400


def test_missing_link_returns_404(client: TestClient) -> None:
    assert client.get("/nonexistent", follow_redirects=False).status_code == 404
    assert client.get("/api/v1/links/nonexistent/stats").status_code == 404


def test_expired_link_returns_410(client: TestClient, db_session: Session) -> None:
    past_time = datetime.now(timezone.utc) - timedelta(minutes=5)
    repository.create_link(
        db_session,
        short_code="expired1",
        target_url="https://example.com",
        expires_at=past_time,
    )

    redirect_resp = client.get("/expired1", follow_redirects=False)
    assert redirect_resp.status_code == 410

    stats_resp = client.get("/api/v1/links/expired1/stats")
    assert stats_resp.status_code == 200
    assert stats_resp.json()["is_expired"] is True


def test_redirect_populates_valkey_cache(client: TestClient, valkey_client: Valkey) -> None:
    create_resp = client.post(
        "/api/v1/links",
        json={"target_url": "https://example.org/", "custom_alias": "cached1"},
    )
    assert create_resp.status_code == 201
    assert valkey_client.get("link:target:cached1") == "https://example.org/"

    # Evict key manually, then trigger redirect to verify read-through repopulation
    valkey_client.delete("link:target:cached1")
    assert valkey_client.get("link:target:cached1") is None

    redirect_resp = client.get("/cached1", follow_redirects=False)
    assert redirect_resp.status_code == 307
    assert valkey_client.get("link:target:cached1") == "https://example.org/"


def test_rate_limit_enforced_on_create(client: TestClient) -> None:
    for idx in range(20):
        resp = client.post(
            "/api/v1/links",
            json={"target_url": f"https://example.com/{idx}"},
        )
        assert resp.status_code == 201

    blocked = client.post(
        "/api/v1/links",
        json={"target_url": "https://example.com/overflow"},
    )
    assert blocked.status_code == 429
