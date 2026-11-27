from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status
from pymongo.errors import DuplicateKeyError

from app.core.deps import Db, require_permission
from app.core.security import hash_password
from app.db import collections as C
from app.repositories.refresh_token import RefreshTokenRepository
from app.repositories.user import UserRepository
from app.schemas.common import DeleteResult
from app.schemas.user import (
    PasswordResetIn, PermissionOut, RoleCreate, RoleOut, RolePermissionsIn, RoleUpdate,
    UserAccessIn, UserCreate, UserOut, UserUpdate,
)
from app.services import iam
from app.services.common import audit, conflict, not_found, unprocessable

# Everything on the Users & Access screen (users, roles, role permissions) is Administrator-only: it needs `user.manage`.
router = APIRouter(prefix="/users", tags=["users"], dependencies=[Depends(require_permission("user.manage"))])
roles_router = APIRouter(tags=["roles"], dependencies=[Depends(require_permission("user.manage"))])


def _one(db, user_id: str) -> dict:
    out = UserRepository(db).get(user_id)
    if out is None:
        raise not_found("User", user_id)
    return iam.enrich_users(db, [out])[0]


def _role_out(db, role_id: str) -> dict:
    return next(r for r in iam.list_roles(db) if r["id"] == role_id)


# ------------------------------------------------------------------ roles & permissions
@roles_router.get("/roles", response_model=list[RoleOut])
def list_roles(db: Db):
    return iam.list_roles(db)


@roles_router.get("/permissions", response_model=list[PermissionOut])
def list_permissions(db: Db):
    return iam.list_permissions(db)


@roles_router.post("/roles", response_model=RoleOut, status_code=status.HTTP_201_CREATED)
def create_role(body: RoleCreate, db: Db, actor: dict = Depends(require_permission("user.manage"))):
    role = iam.create_role(db, body.name, body.description, body.permissions)
    audit(db, actor, "Saved", role["roleId"], f"Role '{role['roleName']}' created with {len(set(body.permissions))} permissions.")
    return _role_out(db, role["roleId"])


@roles_router.patch("/roles/{role_id}", response_model=RoleOut)
def update_role(role_id: str, body: RoleUpdate, db: Db, actor: dict = Depends(require_permission("user.manage"))):
    role = iam.update_role(db, role_id, body.name, body.description)
    audit(db, actor, "Saved", role_id, f"Role '{role['roleName']}' details updated.")
    return _role_out(db, role_id)


@roles_router.put("/roles/{role_id}/permissions", response_model=RoleOut)
def set_role_permissions(role_id: str, body: RolePermissionsIn, db: Db, actor: dict = Depends(require_permission("user.manage"))):
    """Replace the permission set of a role. Takes effect for every member on their very next request."""
    role, added, removed = iam.set_role_permissions(db, role_id, body.permissions)
    parts = [f"granted {', '.join(added)}" if added else "", f"revoked {', '.join(removed)}" if removed else ""]
    audit(db, actor, "Saved", role_id, f"Permissions of '{role['roleName']}': {'; '.join(p for p in parts if p) or 'no change'}.")
    return _role_out(db, role_id)


@roles_router.delete("/roles/{role_id}", response_model=DeleteResult)
def delete_role(role_id: str, db: Db, actor: dict = Depends(require_permission("user.manage"))):
    role = iam.delete_role(db, role_id)
    audit(db, actor, "Deleted", role_id, f"Role '{role['roleName']}' deleted.")
    return DeleteResult(id=role_id, deleted=True)


# ------------------------------------------------------------------ users
@router.get("", response_model=list[UserOut])
def list_users(db: Db):
    return iam.enrich_users(db, UserRepository(db).list())


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(body: UserCreate, db: Db, actor: dict = Depends(require_permission("user.manage"))):
    repo = UserRepository(db)
    role = iam.resolve_role(db, body.role_id, body.app_role)
    if repo.get_raw_by_email(body.email) is not None:
        raise conflict("A user with this e-mail already exists")
    try:
        out = repo.create(
            {
                "id": repo.next_id(),
                "name": body.name.strip(),
                "email": repo.normalize_email(body.email),
                "role": body.role,
                "appRole": role["roleName"],
                "roleId": role["roleId"],
                "facility": body.facility,
                "status": "Active",
                "lastLogin": None,
                "passwordHash": hash_password(body.password),
                "iamBackfilled": True,
            }
        )
    except DuplicateKeyError:
        raise conflict("A user with this e-mail already exists")
    if body.facility_ids:
        try:
            iam.set_user_facilities(db, out["id"], body.facility_ids)
        except ValueError as exc:
            repo.delete(out["id"])
            raise unprocessable(str(exc))
    audit(db, actor, "Saved", out["id"], f"User record for {out['name']} created with role {role['roleName']}.")
    return _one(db, out["id"])


@router.patch("/{user_id}", response_model=UserOut)
def update_user(user_id: str, body: UserUpdate, db: Db, actor: dict = Depends(require_permission("user.manage"))):
    repo = UserRepository(db)
    current = repo.get(user_id)
    if current is None:
        raise not_found("User", user_id)
    changes = body.model_dump(by_alias=True, exclude_none=True)
    new_role_name: str | None = None
    if "roleId" in changes or "appRole" in changes:  # role changes go through the Role master so roleId and appRole never disagree
        role = iam.resolve_role(db, changes.get("roleId"), changes.get("appRole"))
        changes["roleId"], changes["appRole"] = role["roleId"], role["roleName"]
        new_role_name = role["roleName"]
    if "email" in changes:
        changes["email"] = repo.normalize_email(changes["email"])
        if repo.col.find_one({"email": changes["email"], "userId": {"$ne": user_id}}, {"_id": 1}) is not None:
            raise conflict("A user with this e-mail already exists")
    if "name" in changes:
        changes["name"] = changes["name"].strip()
    _guard_last_admin(db, current, new_role_name, changes.get("status"))
    try:
        out = repo.update(user_id, changes) if changes else current
    except DuplicateKeyError:
        raise conflict("A user with this e-mail already exists")
    if changes.get("status") == "Suspended":
        RefreshTokenRepository(db).revoke_all_for_user(user_id)  # cut off existing sessions
    audit(db, actor, "Saved", user_id, f"User record for {out['name']} updated.")
    return _one(db, user_id)


def _guard_last_admin(db, current: dict, new_role: str | None, new_status: str | None) -> None:
    is_active_admin = iam.is_admin(current) and current.get("status") == "Active"
    losing = (new_role is not None and new_role != "Administrator") or (new_status is not None and new_status != "Active")
    if is_active_admin and losing and iam.active_admin_count(db, excluding=current["id"]) == 0:
        raise conflict("This is the last active Administrator; keep at least one so the system can still be managed")


@router.put("/{user_id}/access", response_model=UserOut)
def set_access(user_id: str, body: UserAccessIn, db: Db, actor: dict = Depends(require_permission("user.manage"))):
    """Assign a user's role (Role master) and facilities. Takes effect on the user's very next request."""
    repo = UserRepository(db)
    current = repo.get(user_id)
    if current is None:
        raise not_found("User", user_id)
    role = iam.resolve_role(db, body.role_id, None)
    _guard_last_admin(db, current, role["roleName"], None)
    try:
        ids = iam.set_user_facilities(db, user_id, body.facility_ids)
    except ValueError as exc:
        raise unprocessable(str(exc))
    repo.update(user_id, {"roleId": role["roleId"], "appRole": role["roleName"]})
    audit(db, actor, "Saved", user_id,
          f"Access for {current['name']}: role {role['roleName']}, facilities {', '.join(ids) if ids else 'none assigned (all visible)'}.")
    return _one(db, user_id)


@router.put("/{user_id}/password", status_code=status.HTTP_204_NO_CONTENT, summary="Administrator sets a new password for a user")
def reset_password(user_id: str, body: PasswordResetIn, db: Db, actor: dict = Depends(require_permission("user.manage"))):
    repo = UserRepository(db)
    current = repo.get(user_id)
    if current is None:
        raise not_found("User", user_id)
    repo.update(user_id, {"passwordHash": hash_password(body.new_password)})
    RefreshTokenRepository(db).revoke_all_for_user(user_id)  # sessions opened with the old password end now
    audit(db, actor, "Updated", user_id, f"Password for {current['name']} reset by an administrator; their sessions were revoked.")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/{user_id}", response_model=DeleteResult)
def delete_user(user_id: str, db: Db, actor: dict = Depends(require_permission("user.manage"))):
    """Remove a user. Records they created keep the name they were saved under (the audit trail is never rewritten)
    and their id is never handed to anyone else. Suspend instead if the person may come back."""
    repo = UserRepository(db)
    current = repo.get(user_id)
    if current is None:
        raise not_found("User", user_id)
    if user_id == actor["id"]:
        raise conflict("You cannot delete your own account")
    _guard_last_admin(db, current, None, "Deleted")
    RefreshTokenRepository(db).revoke_all_for_user(user_id)
    db[C.USER_FACILITIES].delete_many({"userId": user_id})
    repo.delete(user_id)
    audit(db, actor, "Deleted", user_id, f"User record for {current['name']} ({current['email']}) deleted.")
    return DeleteResult(id=user_id, deleted=True)
