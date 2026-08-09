from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class GatewayError(Exception):
    """Base class for every error we raise on purpose, anywhere in the app."""

    status_code: int = 500
    error_code: str = "internal_error"

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class NotFoundError(GatewayError):
    status_code = 404
    error_code = "not_found"


class BadRequestError(GatewayError):
    status_code = 400
    error_code = "bad_request"


class UnauthorizedError(GatewayError):
    status_code = 401
    error_code = "unauthorized"


class ProviderError(GatewayError):
    status_code = 502
    error_code = "provider_error"


class ProviderTimeoutError(ProviderError):
    status_code = 504
    error_code = "provider_timeout"


async def gateway_error_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, GatewayError)
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.error_code, "message": exc.message}},
    )


async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "internal_error",
                "message": "Something went wrong on our end.",
            }
        },
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(GatewayError, gateway_error_handler)
    app.add_exception_handler(Exception, unhandled_error_handler)
