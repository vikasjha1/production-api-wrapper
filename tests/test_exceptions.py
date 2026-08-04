from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.exceptions import NotFoundError, register_exception_handlers


def make_test_app() -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/boom-known")
    def boom_known() -> None:
        raise NotFoundError("thing missing")

    @app.get("/boom-unknown")
    def boom_unknown() -> None:
        raise ValueError("totally unexpected")

    return app


def test_known_error_returns_clean_json() -> None:
    client = TestClient(make_test_app())

    response = client.get("/boom-known")

    assert response.status_code == 404
    assert response.json() == {
        "error": {"code": "not_found", "message": "thing missing"}
    }


def test_unknown_error_returns_generic_500_without_leaking_details() -> None:
    client = TestClient(make_test_app(), raise_server_exceptions=False)

    response = client.get("/boom-unknown")

    assert response.status_code == 500
    body = response.json()
    assert body["error"]["code"] == "internal_error"
    assert "totally unexpected" not in body["error"]["message"]
