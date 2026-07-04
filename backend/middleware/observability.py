"""Request-ID + structured access log + Prometheus metrics in one pass."""

import time
import uuid

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from core.logging import get_logger
from core.metrics import HTTP_LATENCY, HTTP_REQUESTS

log = get_logger("access")


class ObservabilityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        structlog.contextvars.bind_contextvars(request_id=request_id)
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            HTTP_REQUESTS.labels(request.method, request.url.path, "500").inc()
            log.exception("request_failed", method=request.method, path=request.url.path)
            raise
        finally:
            structlog.contextvars.unbind_contextvars("request_id")

        elapsed = time.perf_counter() - started
        route = request.scope.get("route")
        route_path = getattr(route, "path", request.url.path)
        HTTP_REQUESTS.labels(request.method, route_path, str(response.status_code)).inc()
        HTTP_LATENCY.labels(request.method, route_path).observe(elapsed)
        response.headers["x-request-id"] = request_id
        if not request.url.path.startswith(("/health", "/metrics")):
            log.info(
                "request",
                method=request.method,
                path=request.url.path,
                status=response.status_code,
                duration_ms=int(elapsed * 1000),
            )
        return response
