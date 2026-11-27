from __future__ import annotations

from fastapi import APIRouter, Depends, status

from app.core.deps import CurrentUser, Db, require_permission
from app.repositories.initiative import InitiativeRepository
from app.schemas.common import DeleteResult
from app.schemas.initiative import AdvanceRequest, AssumptionsIn, AssumptionsOut, InitiativeCreate, InitiativeOut, InitiativeUpdate
from app.services import initiative_assumptions
from app.services import initiatives as svc
from app.services.common import audit, not_found

router = APIRouter(prefix="/initiatives", tags=["initiatives"])
_manager = require_permission("initiative.manage")


@router.get("", response_model=list[InitiativeOut])
def list_initiatives(db: Db, _: CurrentUser, facility_id: str | None = None, status: str | None = None):
    filters = {k: v for k, v in {"facilityId": facility_id, "status": status}.items() if v}
    return svc.list_enriched(db, filters)


@router.get("/assumptions", response_model=AssumptionsOut, summary="Economic assumptions behind ROI / payback / MACC")
def get_assumptions(db: Db, _: CurrentUser):
    return initiative_assumptions.load(db)


@router.put("/assumptions", response_model=AssumptionsOut, summary="Change the economic assumptions")
def put_assumptions(body: AssumptionsIn, db: Db, user: dict = Depends(_manager)):
    return initiative_assumptions.save(db, user, body.model_dump(by_alias=True))


@router.get("/analysis", summary="Portfolio MACC, target-gap coverage and measured facility reductions")
def analysis(db: Db, _: CurrentUser):
    return svc.analysis(db)


@router.get("/{initiative_id}", response_model=InitiativeOut)
def get_initiative(initiative_id: str, db: Db, _: CurrentUser):
    row = InitiativeRepository(db).get(initiative_id)
    if row is None:
        raise not_found("Initiative", initiative_id)
    return svc.enrich(row, initiative_assumptions.load(db))


@router.post("", response_model=InitiativeOut, status_code=status.HTTP_201_CREATED)
def create_initiative(body: InitiativeCreate, db: Db, user: dict = Depends(_manager)):
    return svc.enrich(svc.create_initiative(db, user, body), initiative_assumptions.load(db))


@router.patch("/{initiative_id}", response_model=InitiativeOut)
def update_initiative(initiative_id: str, body: InitiativeUpdate, db: Db, user: dict = Depends(_manager)):
    return svc.enrich(svc.update_initiative(db, user, initiative_id, body), initiative_assumptions.load(db))


@router.post("/{initiative_id}/advance", response_model=InitiativeOut, summary="Advance completion (default +10%); prefer ticking milestones")
def advance_initiative(initiative_id: str, db: Db, user: dict = Depends(_manager), body: AdvanceRequest | None = None):
    return svc.enrich(svc.advance_initiative(db, user, initiative_id, body or AdvanceRequest()), initiative_assumptions.load(db))


@router.delete("/{initiative_id}", response_model=DeleteResult)
def delete_initiative(initiative_id: str, db: Db, user: dict = Depends(_manager)):
    if not InitiativeRepository(db).delete(initiative_id):
        raise not_found("Initiative", initiative_id)
    audit(db, user, "Deleted", initiative_id, "Initiative removed.")
    return DeleteResult(id=initiative_id, deleted=True)
