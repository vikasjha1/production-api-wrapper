from collections.abc import Generator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings
from app.main import app


@pytest.fixture
def client_with_test_key() -> Generator[TestClient, None, None]:
    def override_settings() -> Settings:
        return Settings(api_keys={"test-key-abc": "test-client"})

    app.dependency_overrides[get_settings] = override_settings
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.pop(get_settings, None)


def test_missing_api_key_is_rejected(client_with_test_key: TestClient) -> None:
    response = client_with_test_key.get("/v1/me")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


def test_wrong_api_key_is_rejected(client_with_test_key: TestClient) -> None:
    response = client_with_test_key.get("/v1/me", headers={"X-API-Key": "wrong-key"})

    assert response.status_code == 401


def test_correct_api_key_is_accepted(client_with_test_key: TestClient) -> None:
    response = client_with_test_key.get("/v1/me", headers={"X-API-Key": "test-key-abc"})

    assert response.status_code == 200
    assert response.json() == {"client_id": "test-client"}


@pytest.fixture
def client_with_expiring_key() -> Generator[TestClient, None, None]:
    def override_settings() -> Settings:
        return Settings(
            api_keys={"expired-key": "test-client", "future-key": "test-client"},
            api_key_expires_at={
                "expired-key": datetime.now(UTC) - timedelta(hours=1),
                "future-key": datetime.now(UTC) + timedelta(hours=1),
            },
        )

    app.dependency_overrides[get_settings] = override_settings
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.pop(get_settings, None)


def test_expired_api_key_is_rejected(client_with_expiring_key: TestClient) -> None:
    response = client_with_expiring_key.get("/v1/me", headers={"X-API-Key": "expired-key"})

    assert response.status_code == 401
    assert "expired" in response.json()["error"]["message"].lower()


def test_not_yet_expired_api_key_is_accepted(client_with_expiring_key: TestClient) -> None:
    response = client_with_expiring_key.get("/v1/me", headers={"X-API-Key": "future-key"})

    assert response.status_code == 200
