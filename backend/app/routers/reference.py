from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, status

from app.core.deps import CurrentUser, Db, require_permission
from app.repositories.reference import REFERENCE_KEYS, ReferenceRepository
from app.services.common import audit

router = APIRouter(prefix="/reference", tags=["reference data"])


def _check(key: str) -> None:
    if key not in REFERENCE_KEYS:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Unknown reference list '{key}'. Valid: {', '.join(REFERENCE_KEYS)}")


@router.get("/{key}", response_model=list[dict[str, Any]])
def get_reference(key: str, db: Db, _: CurrentUser):
    _check(key)
    return ReferenceRepository(db).get_items(key) or []


@router.put("/{key}", response_model=list[dict[str, Any]])
def put_reference(
    key: str,
    db: Db,
    items: list[dict[str, Any]] = Body(...),
    user: dict = Depends(require_permission("reference.manage")),
):
    _check(key)
    out = ReferenceRepository(db).set_items(key, items)
    audit(db, user, "Saved", key, f"Reference list '{key}' replaced ({len(items)} items).")
    return out
