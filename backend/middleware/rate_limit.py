from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from services.cache import RateLimiter

_EXEMPT = ("/health", "/metrics", "/docs", "/openapi.json")


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Per-user (JWT sub) or per-IP fixed-window limit. Sits before auth, so it
    reads the JWT subject without verifying — verification happens downstream;
    a forged sub only carves out its own bucket."""

    def __init__(self, app, limiter: RateLimiter) -> None:  # type: ignore[no-untyped-def]
        super().__init__(app)
        self._limiter = limiter

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.url.path.startswith(_EXEMPT):
            return await call_next(request)
        subject = request.client.host if request.client else "unknown"
        auth = request.headers.get("authorization", "")
        if auth.startswith("Bearer "):
            import jwt as pyjwt

            try:
                claims = pyjwt.decode(auth[7:], options={"verify_signature": False})
                subject = claims.get("sub", subject)
            except pyjwt.PyJWTError:
                pass
        if not await self._limiter.allow(subject):
            return JSONResponse(
                status_code=429,
                content={"error": {"code": "rate_limited", "message": "Too many requests"}},
            )
        return await call_next(request)
