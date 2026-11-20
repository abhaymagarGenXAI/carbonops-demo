from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.db.client import get_database

router = APIRouter(tags=["health"])


@router.get("/health", summary="Liveness + MongoDB connectivity (public)")
def health():
    try:
        get_database().command("ping")
        return {"status": "ok", "database": "up"}
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"status": "degraded", "database": "down", "error": type(exc).__name__}, status_code=503)
