from fastapi import FastAPI

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import configure_logging
from app.middleware.request_logging import RequestLoggingMiddleware


def create_app() -> FastAPI:
    configure_logging()
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        debug=settings.debug,
    )

    register_exception_handlers(app)
    app.add_middleware(RequestLoggingMiddleware)
    app.include_router(api_router, prefix="/v1")

    @app.get("/")
    def root() -> dict[str, str]:
        return {"message": f"{settings.app_name} is running"}

    return app


app = create_app()
