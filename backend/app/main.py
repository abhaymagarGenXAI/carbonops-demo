from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pymongo.errors import DuplicateKeyError, PyMongoError

from app.core.config import get_settings
from app.core.middleware import AccessTokenMiddleware
from app.db.client import close_client, get_database
from app.db.indexes import ensure_indexes
from app.services.iam import ensure_iam
from app.services.masters import ensure_masters
from app.routers import (
    admin_tools, alerts, assets, audit, auth, documents, emission_factors, emissions, energy, scope3, forecast, assistant,
    facilities, health, initiatives, masters, master_data, periods, validation_rules, reference, submissions, targets, reports, users,
)

log = logging.getLogger("carbonops")


def create_app() -> FastAPI:
    settings = get_settings()

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        try:
            ensure_indexes(get_database())
            ensure_iam(get_database())
            ensure_masters(get_database())
        except Exception:  # noqa: BLE001 - keep the API up so /health can report the problem
            log.exception("Could not reach MongoDB / create indexes at startup")
        yield
        close_client()

    app = FastAPI(
        title="CarbonOps AI API",
        version="1.0.0",
        description="FastAPI + PyMongo backend for CarbonOps AI (JWT authentication).",
        lifespan=lifespan,
    )

    p = settings.api_prefix
    public = {f"{p}/auth/login", f"{p}/auth/refresh", f"{p}/auth/logout", f"{p}/health"}
    app.add_middleware(AccessTokenMiddleware, prefix=p, public_paths=public)
    # Added last => outermost, so even 401 responses from the middleware carry CORS headers.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,  # needed for the httpOnly refresh cookie
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
    )

    @app.middleware("http")
    async def _security_headers(request: Request, call_next):
        response = await call_next(request)
        h = response.headers
        h.setdefault("X-Content-Type-Options", "nosniff")
        h.setdefault("X-Frame-Options", "DENY")
        h.setdefault("Referrer-Policy", "no-referrer")
        h.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        if not request.url.path.startswith(("/docs", "/redoc", "/openapi")):
            h.setdefault("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'; base-uri 'none'")
        if request.url.path.startswith(p):
            h.setdefault("Cache-Control", "no-store")
        if request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https":
            h.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        return response

    @app.exception_handler(DuplicateKeyError)
    async def _duplicate(_: Request, __: DuplicateKeyError):
        return JSONResponse({"detail": "A record with the same unique key already exists"}, status_code=409)

    @app.exception_handler(PyMongoError)
    async def _mongo(_: Request, exc: PyMongoError):
        log.error("MongoDB error: %s", exc)
        return JSONResponse({"detail": "Database unavailable or operation failed"}, status_code=503)

    api = APIRouter(prefix=p)
    for module in (
        health, alerts, periods, validation_rules, targets, reports, forecast, assistant, auth, users, facilities, assets, submissions, energy, emissions,
        emission_factors, scope3, initiatives, documents, audit, reference, admin_tools, masters, master_data,
    ):
        api.include_router(module.router)
    api.include_router(users.roles_router)
    app.include_router(api)
    return app


app = create_app()
