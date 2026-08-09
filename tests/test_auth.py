from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings
from app.main import app


@pytest.fixture
def client_with_test_key() -> Generator[TestClient, None, None]:
    def override_settings() -> Settings:
        return Settings(api_keys={"test-key-abc": "test-client"})

    app.dependency_overrides[get_settings] = override_settings
    yield TestClient(app)
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
