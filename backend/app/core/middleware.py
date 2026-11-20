from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.core.security import TokenError, decode_token


class AccessTokenMiddleware(BaseHTTPMiddleware):
    """Authentication gate for the whole API.

    Every request under `prefix` must carry a valid `Authorization: Bearer <access token>`
    unless its path is in `public_paths`. On success the decoded claims are stashed on
    `request.state.auth_claims`; per-route authorization (roles) is done by dependencies.
    """

    def __init__(self, app, *, prefix: str, public_paths: set[str]):
        super().__init__(app)
        self.prefix = prefix
        self.public_paths = public_paths

    async def dispatch(self, request: Request, call_next):
        path = request.url.path.rstrip("/") or "/"
        if request.method == "OPTIONS" or not path.startswith(self.prefix) or path in self.public_paths:
            return await call_next(request)

        scheme, _, token = request.headers.get("authorization", "").partition(" ")
        if scheme.lower() != "bearer" or not token:
            return self._reject("Not authenticated")
        try:
            request.state.auth_claims = decode_token(token.strip(), "access")
        except TokenError:
            return self._reject("Invalid or expired access token")
        return await call_next(request)

    @staticmethod
    def _reject(detail: str) -> JSONResponse:
        return JSONResponse({"detail": detail}, status_code=401, headers={"WWW-Authenticate": "Bearer"})
