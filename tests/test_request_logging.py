from fastapi.testclient import TestClient

from app.main import app


def test_response_includes_generated_request_id() -> None:
    client = TestClient(app)

    response = client.get("/v1/health")

    assert "X-Request-ID" in response.headers
    assert len(response.headers["X-Request-ID"]) > 0


def test_incoming_request_id_is_echoed_back() -> None:
    client = TestClient(app)

    response = client.get("/v1/health", headers={"X-Request-ID": "my-custom-id-123"})

    assert response.headers["X-Request-ID"] == "my-custom-id-123"
