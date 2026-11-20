from __future__ import annotations

from fastapi import APIRouter, Query

from app.core.deps import CurrentUser, Db
from app.repositories.audit import AuditRepository
from app.schemas.audit import AuditOut

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("", response_model=list[AuditOut], summary="Audit trail, newest first")
def list_audit(db: Db, _: CurrentUser, limit: int = Query(200, ge=1, le=1000)):
    return AuditRepository(db).list(limit=limit)
