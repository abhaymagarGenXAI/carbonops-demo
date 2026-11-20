from __future__ import annotations

from fastapi import APIRouter, Depends, status
from pymongo.errors import DuplicateKeyError

from app.core.deps import ADMINISTRATOR, Db, require_roles
from app.core.security import hash_password
from app.repositories.refresh_token import RefreshTokenRepository
from app.repositories.user import UserRepository
from app.schemas.user import UserCreate, UserOut, UserUpdate
from app.services.common import audit, conflict, not_found

router = APIRouter(prefix="/users", tags=["users"], dependencies=[Depends(require_roles(ADMINISTRATOR))])


@router.get("", response_model=list[UserOut])
def list_users(db: Db):
    return UserRepository(db).list()


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(body: UserCreate, db: Db, actor: dict = Depends(require_roles(ADMINISTRATOR))):
    repo = UserRepository(db)
    try:
        out = repo.create(
            {
                "id": repo.next_id(),
                "name": body.name.strip(),
                "email": repo.normalize_email(body.email),
                "role": body.role,
                "appRole": body.app_role,
                "facility": body.facility,
                "status": "Active",
                "lastLogin": None,
                "passwordHash": hash_password(body.password),
            }
        )
    except DuplicateKeyError:
        raise conflict("A user with this e-mail already exists")
    audit(db, actor, "Saved", out["id"], f"User record for {out['name']} created.")
    return out


@router.patch("/{user_id}", response_model=UserOut)
def update_user(user_id: str, body: UserUpdate, db: Db, actor: dict = Depends(require_roles(ADMINISTRATOR))):
    repo = UserRepository(db)
    changes = body.model_dump(by_alias=True, exclude_none=True)
    out = repo.update(user_id, changes) if changes else repo.get(user_id)
    if out is None:
        raise not_found("User", user_id)
    if changes.get("status") == "Suspended":
        RefreshTokenRepository(db).revoke_all_for_user(user_id)  # cut off existing sessions
    audit(db, actor, "Saved", user_id, f"User record for {out['name']} updated.")
    return out
