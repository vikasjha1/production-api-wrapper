import time

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response


def _templated_path(request: Request) -> str:
    path_params = request.scope.get("path_params")
    if path_params is None:
        return "unmatched"

    path = request.url.path
    for name, value in path_params.items():
        path = path.replace(str(value), f"{{{name}}}")
    return path


class MetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        start_time = time.perf_counter()

        response = await call_next(request)

        duration = time.perf_counter() - start_time

        path_label = _templated_path(request)

        metrics = request.app.state.metrics
        metrics.request_count.labels(
            method=request.method, path=path_label, status_code=response.status_code
        ).inc()
        metrics.request_latency.labels(method=request.method, path=path_label).observe(duration)

        return response
