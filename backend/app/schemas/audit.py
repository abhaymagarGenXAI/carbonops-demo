from __future__ import annotations

from app.schemas.common import CamelModel


class AuditOut(CamelModel):
    id: str
    at: str | None = None
    who: str
    action: str
    target: str
    detail: str
