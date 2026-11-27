from __future__ import annotations

from fastapi import APIRouter, Depends, status

from app.core.deps import CurrentUser, Db, require_permission
from app.repositories.emission_factor import EmissionFactorRepository
from app.schemas.common import DeleteResult
from app.schemas.emission import EmissionFactorCreate, EmissionFactorOut, EmissionFactorUpdate
from app.services import carbon, masters
from app.services.common import audit, not_found

router = APIRouter(prefix="/emission-factors", tags=["emission factors"])


@router.get("", response_model=list[EmissionFactorOut])
def list_factors(db: Db, _: CurrentUser):
    return EmissionFactorRepository(db).list()


@router.post("", response_model=EmissionFactorOut, status_code=status.HTTP_201_CREATED)
def create_factor(body: EmissionFactorCreate, db: Db, user: dict = Depends(require_permission("factor.manage"))):
    repo = EmissionFactorRepository(db)
    data = body.model_dump(by_alias=True)
    data["id"] = data.get("id") or repo.next_id()
    carbon.validate_factor_definition(db, data)
    out = repo.create(data)
    masters.link_factor(db, out["id"])
    out = repo.get(out["id"])
    carbon.supersede_older(db, out)
    audit(db, user, "Saved", out["id"], f"Emission factor {out['source']} set to {out['value']} {out['unit']}.")
    return out


@router.patch("/{factor_id}", response_model=EmissionFactorOut)
def update_factor(
    factor_id: str, body: EmissionFactorUpdate, db: Db, user: dict = Depends(require_permission("factor.manage"))
):
    repo = EmissionFactorRepository(db)
    changes = body.model_dump(by_alias=True, exclude_none=True)
    current = repo.get(factor_id)
    if current is None:
        raise not_found("Emission factor", factor_id)
    if changes:
        carbon.guard_factor_in_use(db, current, changes)
        carbon.validate_factor_definition(db, {**current, **changes}, self_id=factor_id)
    out = repo.update(factor_id, changes) if changes else current
    assert out is not None
    masters.link_factor(db, factor_id)
    out = repo.get(factor_id)
    carbon.supersede_older(db, out)
    audit(db, user, "Saved", factor_id, f"Emission factor {out['source']} set to {out['value']} {out['unit']}.")
    return out


@router.delete("/{factor_id}", response_model=DeleteResult)
def delete_factor(factor_id: str, db: Db, user: dict = Depends(require_permission("factor.manage"))):
    carbon.guard_factor_delete(db, factor_id)
    sid = (EmissionFactorRepository(db).get(factor_id) or {}).get("emissionSourceId")
    if not EmissionFactorRepository(db).delete(factor_id):
        raise not_found("Emission factor", factor_id)
    masters.refresh_factor_validity(db, sid)
    audit(db, user, "Deleted", factor_id, "Emission factor removed.")
    return DeleteResult(id=factor_id, deleted=True)
