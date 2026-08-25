from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


@pytest.fixture
def client_with_allowed_origin() -> Generator[TestClient, None, None]:
    app = create_app(Settings(cors_allowed_origins=["https://dashboard.example.com"]))
    with TestClient(app) as client:
        yield client


@pytest.fixture
def client_with_no_cors_configured() -> Generator[TestClient, None, None]:
    app = create_app(Settings())
    with TestClient(app) as client:
        yield client


def test_allowed_origin_gets_cors_header(client_with_allowed_origin: TestClient) -> None:
    response = client_with_allowed_origin.get(
        "/", headers={"Origin": "https://dashboard.example.com"}
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://dashboard.example.com"


def test_disallowed_origin_gets_no_cors_header(client_with_allowed_origin: TestClient) -> None:
    response = client_with_allowed_origin.get("/", headers={"Origin": "https://evil.example.com"})

    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers


def test_preflight_request_for_allowed_origin_is_approved(
    client_with_allowed_origin: TestClient,
) -> None:
    response = client_with_allowed_origin.options(
        "/v1/me",
        headers={
            "Origin": "https://dashboard.example.com",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "X-API-Key",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://dashboard.example.com"


def test_no_origins_configured_means_no_cors_header_even_for_any_origin(
    client_with_no_cors_configured: TestClient,
) -> None:
    response = client_with_no_cors_configured.get(
        "/", headers={"Origin": "https://dashboard.example.com"}
    )

    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers
