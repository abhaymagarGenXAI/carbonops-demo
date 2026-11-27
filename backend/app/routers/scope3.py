from __future__ import annotations

from fastapi import APIRouter, Depends, status

from app.core.deps import CurrentUser, Db, require_permission
from app.schemas.common import DeleteResult
from app.schemas.scope3 import Scope3EntryIn, Scope3EntryOut, Scope3ReviewIn
from app.services import scope3 as svc
from app.services import scope3_engine as eng

router = APIRouter(prefix="/scope3", tags=["scope 3"])


@router.get("/categories", summary="GHG Protocol Scope 3 categories")
def categories(_: CurrentUser) -> list[str]:
    return list(eng.CATEGORIES)


@router.get("", response_model=list[Scope3EntryOut])
def list_entries(db: Db, _: CurrentUser, month: str | None = None, status: str | None = None):
    return svc.list_entries(db, month, status)


@router.post("", response_model=Scope3EntryOut, status_code=status.HTTP_201_CREATED)
def create_entry(body: Scope3EntryIn, db: Db, user: CurrentUser):
    return svc.create(db, user, body.model_dump(by_alias=True))


@router.put("/{entry_id}", response_model=Scope3EntryOut, summary="Correct and resubmit an entry")
def update_entry(entry_id: str, body: Scope3EntryIn, db: Db, user: CurrentUser):
    return svc.update(db, user, entry_id, body.model_dump(by_alias=True))


@router.delete("/{entry_id}", response_model=DeleteResult)
def delete_entry(entry_id: str, db: Db, user: CurrentUser):
    svc.delete(db, user, entry_id)
    return DeleteResult(id=entry_id, deleted=True)


@router.post("/{entry_id}/review", response_model=Scope3EntryOut)
def review_entry(entry_id: str, body: Scope3ReviewIn, db: Db, user: dict = Depends(require_permission("scope3.approve"))):
    return svc.review(db, user, entry_id, body.decision, body.comment)
