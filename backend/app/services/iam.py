"""Identity & access: the Role master, permission catalogue, role->permission grants and user->facility assignments.

Design (see DATABASE_ARCHITECTURE_PROPOSED.md, Stage 1):
  roles(roleId, roleCode, roleName, ...)  <-  users.roleId        (one role per user)
  permissions(permissionCode)  <-  role_permissions(roleId, permissionCode)
  user_facilities(userId, facilityId)     (facility assignment; NOT enforced - every facility stays visible to every role)

`users.appRole` is kept in sync with the role's `roleName`: the JWT claim, the UI route matrix and the
role-specific business rules (four-eyes, evidence ownership) still read it. Endpoint checks use permissions.
Everything here is idempotent; `ensure_iam` runs at start-up and after seeding.

Administrator-managed (Users & Access screen): custom roles can be created, renamed, deleted and given any set of
permissions; the grants of the built-in Plant Engineer / Sustainability Manager roles can be edited too. The built-in
Administrator role is locked (always holds every permission) so the system can never be locked out. Start-up seeding
only ever ADDS defaults for roles/permissions that did not exist yet - it never re-grants something an Administrator removed.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Mapping

from pymongo.database import Database

from app.db import collections as C
from app.services.common import conflict, not_found, unprocessable
from app.utils.time import utcnow

log = logging.getLogger(__name__)

PE, SM, AD = "R-PE", "R-SM", "R-AD"

# (code, module, description, roles that hold it). Administrator additionally holds every permission.
# The grants reproduce exactly what the former `require_roles(...)` checks allowed.
PERMISSIONS: list[tuple[str, str, str, tuple[str, ...]]] = [
    # Module access: which pages appear in the menu / can be opened. Data reads stay open to every signed-in user (as before);
    # what a user may CHANGE is controlled by the action permissions below.
    ("page.activity", "access", "Open the Activity Data page", (PE,)),
    ("page.energy", "access", "Open the Energy Management page", (PE, SM)),
    ("page.carbon", "access", "Open the Carbon Accounting page", (SM,)),
    ("page.initiatives", "access", "Open the Decarbonization Initiatives page", (SM,)),
    ("page.approvals", "access", "Open the Validation & Approvals page", (SM,)),
    ("page.documents", "access", "Open the Document repository (every file and where it is attached)", ()),
    ("activity.submit", "activity", "Save and submit monthly activity data", (PE,)),
    ("import.run", "activity", "Bulk-import activity data (CSV/XLSX)", (PE,)),
    ("activity.review", "approvals", "Approve, reject or request clarification on submissions", (SM,)),
    ("energy.edit", "energy", "Create, edit and delete energy records", (PE,)),
    ("energy.reconcile", "energy", "Reconcile energy records with submissions", (SM,)),
    ("carbon.recalculate", "carbon", "Recalculate emissions (e.g. after a factor change)", (SM,)),
    ("carbon.review", "carbon", "Review individual emission records", (SM,)),
    ("scope3.approve", "carbon", "Approve or reject Scope 3 entries (not your own)", (SM,)),
    ("period.manage", "governance", "Open reporting periods and change their status", (SM,)),
    ("rules.manage", "governance", "Edit validation rules", (SM,)),
    ("target.manage", "governance", "Set baseline and reduction targets", (SM,)),
    ("initiative.manage", "initiatives", "Create and edit decarbonisation initiatives", (SM,)),
    ("asset.edit", "master", "Edit assets", (PE,)),
    ("asset.create", "master", "Create assets", ()),
    ("asset.delete", "master", "Delete assets", ()),
    ("facility.manage", "master", "Create, edit and delete facilities", ()),
    ("master.import", "master", "Upload facilities and assets from Excel and download the upload template", ()),
    ("factor.manage", "master", "Maintain emission factors", ()),
    ("reference.manage", "master", "Replace reference lists", ()),
    ("alert.discard", "governance", "Permanently discard dashboard alerts", ()),
    ("db.tools", "admin", "Database maintenance tools", ()),
    ("user.manage", "admin", "Manage users, roles and facility assignments", ()),
]

ROLES: list[dict[str, Any]] = [
    {"roleId": PE, "roleCode": "PLANT_ENGINEER", "roleName": "Plant Engineer",
     "description": "Enters activity data, evidence and energy records."},
    {"roleId": SM, "roleCode": "SUSTAINABILITY_MANAGER", "roleName": "Sustainability Manager",
     "description": "Reviews and approves data, runs carbon accounting, targets and initiatives."},
    {"roleId": AD, "roleCode": "ADMINISTRATOR", "roleName": "Administrator",
     "description": "Maintains master data, emission factors and users."},
]
ADMIN_ROLE_ID = AD
ALL_FACILITIES_LABEL = "All Facilities"
_NO_NAME = {"", "—", "-", "Pending assignment", None}


# ------------------------------------------------------------------ seeding / migration
def ensure_iam(db: Database) -> dict[str, int]:
    """Create missing roles, permissions and default grants, then backfill users.

    Default grants are only written for a permission or role that is NEW in this run, so a grant an Administrator has
    removed is never put back by a restart. The Administrator role always holds every permission."""
    now = utcnow()
    made = {"roles": 0, "permissions": 0, "grants": 0}
    new_permissions: set[str] = set()
    new_roles: set[str] = set()
    for code, module, desc, _ in PERMISSIONS:
        r = db[C.PERMISSIONS].update_one({"permissionCode": code}, {"$setOnInsert": {
            "permissionCode": code, "module": module, "description": desc, "createdAt": now}}, upsert=True)
        if r.upserted_id:
            made["permissions"] += 1
            new_permissions.add(code)
    for role in ROLES:
        r = db[C.ROLES].update_one({"roleId": role["roleId"]}, {"$setOnInsert": {
            **role, "isSystem": True, "allFacilities": True, "isActive": True, "createdAt": now, "updatedAt": now}}, upsert=True)
        if r.upserted_id:
            made["roles"] += 1
            new_roles.add(role["roleId"])
    for code, _, _, holders in PERMISSIONS:
        targets = {rid for rid in holders if code in new_permissions or rid in new_roles} | {ADMIN_ROLE_ID}
        for rid in targets:
            r = db[C.ROLE_PERMISSIONS].update_one({"roleId": rid, "permissionCode": code},
                                                  {"$setOnInsert": {"roleId": rid, "permissionCode": code, "createdAt": now}}, upsert=True)
            made["grants"] += 1 if r.upserted_id else 0
    made.update(backfill_users(db))
    made.update(backfill_user_links(db))
    if any(made.values()):
        log.info("IAM ensured: %s", made)
    return made


def backfill_users(db: Database) -> dict[str, int]:
    """users.roleId from appRole; user_facilities from the legacy `facility` name (once per user)."""
    role_by_name = {r["roleName"]: r["roleId"] for r in db[C.ROLES].find({}, {"_id": 0})}
    fac_by_name = {f["name"].strip().lower(): f["facilityId"] for f in db[C.FACILITIES].find({}, {"_id": 0, "facilityId": 1, "name": 1})}
    out = {"usersRoleLinked": 0, "userFacilitiesCreated": 0, "unmatchedFacilityNames": 0}
    for u in db[C.USERS].find({}, {"_id": 0, "userId": 1, "appRole": 1, "roleId": 1, "facility": 1, "iamBackfilled": 1}):
        changes: dict[str, Any] = {}
        if not u.get("roleId") and u.get("appRole") in role_by_name:
            changes["roleId"] = role_by_name[u["appRole"]]
            out["usersRoleLinked"] += 1
        if not u.get("iamBackfilled"):
            label = (u.get("facility") or "").strip()
            if label and label != ALL_FACILITIES_LABEL:
                first = True
                for part in [p.strip() for p in label.split(",") if p.strip()]:
                    fid = fac_by_name.get(part.lower())
                    if fid is None:
                        out["unmatchedFacilityNames"] += 1
                        continue
                    r = db[C.USER_FACILITIES].update_one({"userId": u["userId"], "facilityId": fid}, {"$setOnInsert": {
                        "userId": u["userId"], "facilityId": fid, "isPrimary": first, "createdAt": utcnow()}}, upsert=True)
                    out["userFacilitiesCreated"] += 1 if r.upserted_id else 0
                    first = False
            changes["iamBackfilled"] = True
        if changes:
            db[C.USERS].update_one({"userId": u["userId"]}, {"$set": changes})
    return out


def backfill_user_links(db: Database) -> dict[str, int]:
    """Stage 1c: add `...Id` fields next to the legacy name fields. Only unambiguous exact-name matches are linked."""
    names: dict[str, list[str]] = {}
    for u in db[C.USERS].find({}, {"_id": 0, "userId": 1, "name": 1}):
        names.setdefault(u["name"], []).append(u["userId"])
    unique = {n: ids[0] for n, ids in names.items() if len(ids) == 1}
    plan = [(C.SUBMISSIONS, "submittedBy", "submittedById"), (C.SUBMISSIONS, "reviewer", "reviewerId"),
            (C.SCOPE3_ENTRIES, "reviewer", "reviewerId"), (C.DOCUMENTS, "uploadedBy", "uploadedById"),
            (C.AUDIT_LOG, "who", "userId")]
    linked = 0
    for coll, name_f, id_f in plan:
        for name, uid in unique.items():
            r = db[coll].update_many({name_f: name, "$or": [{id_f: {"$exists": False}}, {id_f: None}]}, {"$set": {id_f: uid}})
            linked += r.modified_count
    return {"linksBackfilled": linked}


# ------------------------------------------------------------------ lookups
def role_for_user(db: Database, user: Mapping[str, Any]) -> dict[str, Any] | None:
    q = {"roleId": user["roleId"]} if user.get("roleId") else {"roleName": user.get("appRole")}
    return db[C.ROLES].find_one(q, {"_id": 0})


def permissions_for(db: Database, user: Mapping[str, Any]) -> set[str]:
    role = role_for_user(db, user)
    if role is None:  # roles not created yet (fresh DB that skipped start-up) -> create once and retry
        ensure_iam(db)
        role = role_for_user(db, user)
    if role is None or not role.get("isActive", True):
        return set()
    return {g["permissionCode"] for g in db[C.ROLE_PERMISSIONS].find({"roleId": role["roleId"]}, {"_id": 0, "permissionCode": 1})}


def list_roles(db: Database) -> list[dict[str, Any]]:
    grants: dict[str, list[str]] = {}
    for g in db[C.ROLE_PERMISSIONS].find({}, {"_id": 0}):
        grants.setdefault(g["roleId"], []).append(g["permissionCode"])
    members: dict[str, int] = {}
    for u in db[C.USERS].find({}, {"_id": 0, "roleId": 1}):
        members[u.get("roleId")] = members.get(u.get("roleId"), 0) + 1
    out = []
    for r in db[C.ROLES].find({}, {"_id": 0}).sort("roleId", 1):
        out.append({"id": r["roleId"], "code": r["roleCode"], "name": r["roleName"], "description": r.get("description", ""),
                    "isSystem": bool(r.get("isSystem")), "isLocked": r["roleId"] == ADMIN_ROLE_ID, "allFacilities": bool(r.get("allFacilities")), "isActive": bool(r.get("isActive", True)),
                    "members": members.get(r["roleId"], 0), "permissions": sorted(grants.get(r["roleId"], []))})
    return out


def list_permissions(db: Database) -> list[dict[str, Any]]:
    return [{"code": p["permissionCode"], "module": p["module"], "description": p["description"]}
            for p in db[C.PERMISSIONS].find({}, {"_id": 0}).sort([("module", 1), ("permissionCode", 1)])]


def facility_ids_by_user(db: Database) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for r in db[C.USER_FACILITIES].find({}, {"_id": 0}).sort([("isPrimary", -1), ("facilityId", 1)]):
        out.setdefault(r["userId"], []).append(r["facilityId"])
    return out


def enrich_users(db: Database, users: list[dict[str, Any]]) -> list[dict[str, Any]]:
    roles = {r["roleId"]: r for r in db[C.ROLES].find({}, {"_id": 0})}
    by_name = {r["roleName"]: r for r in roles.values()}
    fac = facility_ids_by_user(db)
    grants: dict[str, list[str]] = {}
    for g in db[C.ROLE_PERMISSIONS].find({}, {"_id": 0}):
        grants.setdefault(g["roleId"], []).append(g["permissionCode"])
    for u in users:
        role = roles.get(u.get("roleId")) or by_name.get(u.get("appRole"))
        u["roleId"] = role["roleId"] if role else None
        u["roleCode"] = role["roleCode"] if role else None
        u["facilityIds"] = fac.get(u["id"], [])
        u["permissions"] = sorted(grants.get(role["roleId"], [])) if role and role.get("isActive", True) else []
    return users


# ------------------------------------------------------------------ changes
def facility_label(db: Database, facility_ids: list[str]) -> str:
    """Keeps the legacy `users.facility` display text in step with the assignment."""
    if not facility_ids:
        return ALL_FACILITIES_LABEL
    names = {f["facilityId"]: f["name"] for f in db[C.FACILITIES].find({"facilityId": {"$in": facility_ids}}, {"_id": 0, "facilityId": 1, "name": 1})}
    return ", ".join(names[f] for f in facility_ids if f in names) or ALL_FACILITIES_LABEL


def set_user_facilities(db: Database, user_id: str, facility_ids: list[str]) -> list[str]:
    ids = list(dict.fromkeys(facility_ids))
    known = {f["facilityId"] for f in db[C.FACILITIES].find({"facilityId": {"$in": ids}}, {"_id": 0, "facilityId": 1})}
    missing = [i for i in ids if i not in known]
    if missing:
        raise ValueError(f"Unknown facility: {', '.join(missing)}")
    db[C.USER_FACILITIES].delete_many({"userId": user_id, "facilityId": {"$nin": ids}})
    for n, fid in enumerate(ids):
        db[C.USER_FACILITIES].update_one({"userId": user_id, "facilityId": fid}, {"$set": {"isPrimary": n == 0}, "$setOnInsert": {
            "userId": user_id, "facilityId": fid, "createdAt": utcnow()}}, upsert=True)
    db[C.USERS].update_one({"userId": user_id}, {"$set": {"facility": facility_label(db, ids), "iamBackfilled": True}})
    return ids


def drop_facility_assignments(db: Database, facility_id: str) -> None:
    """A deleted facility disappears from every user's assignment list (and their display text)."""
    affected = [r["userId"] for r in db[C.USER_FACILITIES].find({"facilityId": facility_id}, {"_id": 0, "userId": 1})]
    db[C.USER_FACILITIES].delete_many({"facilityId": facility_id})
    for uid in affected:
        ids = facility_ids_by_user(db).get(uid, [])
        db[C.USERS].update_one({"userId": uid}, {"$set": {"facility": facility_label(db, ids)}})


def refresh_facility_labels(db: Database, facility_id: str) -> None:
    """After a facility rename, update the display text of the users assigned to it."""
    fac = facility_ids_by_user(db)
    for r in db[C.USER_FACILITIES].find({"facilityId": facility_id}, {"_id": 0, "userId": 1}):
        db[C.USERS].update_one({"userId": r["userId"]}, {"$set": {"facility": facility_label(db, fac.get(r["userId"], []))}})


def active_admin_count(db: Database, excluding: str | None = None) -> int:
    q: dict[str, Any] = {"appRole": "Administrator", "status": "Active"}
    if excluding:
        q["userId"] = {"$ne": excluding}
    return db[C.USERS].count_documents(q)


def is_admin(user: Mapping[str, Any]) -> bool:
    return user.get("roleId") == ADMIN_ROLE_ID or user.get("appRole") == "Administrator"


def resolve_role(db: Database, role_id: str | None, role_name: str | None) -> dict[str, Any]:
    """The active role chosen by id (preferred) or by name (legacy clients). 422 when it does not exist."""
    if role_id:
        role = db[C.ROLES].find_one({"roleId": role_id, "isActive": True}, {"_id": 0})
        if role is None:
            raise unprocessable(f"Unknown or inactive role '{role_id}'")
        return role
    role = db[C.ROLES].find_one({"roleName": role_name, "isActive": True}, {"_id": 0})
    if role is None:
        ensure_iam(db)  # a fresh database that skipped start-up
        role = db[C.ROLES].find_one({"roleName": role_name, "isActive": True}, {"_id": 0})
    if role is None:
        raise unprocessable(f"Unknown role '{role_name}'")
    return role


# ------------------------------------------------------------------ role management (Administrator)
def _role_or_404(db: Database, role_id: str) -> dict[str, Any]:
    role = db[C.ROLES].find_one({"roleId": role_id}, {"_id": 0})
    if role is None:
        raise not_found("Role", role_id)
    return role


def _check_name(db: Database, name: str, exclude_id: str | None = None) -> str:
    name = " ".join(name.split())
    if len(name) < 2:
        raise unprocessable("A role name needs at least 2 characters")
    for r in db[C.ROLES].find({}, {"_id": 0, "roleId": 1, "roleName": 1}):
        if r["roleId"] != exclude_id and r["roleName"].strip().lower() == name.lower():
            raise conflict(f"A role named '{r['roleName']}' already exists")
    return name


def _check_codes(db: Database, codes: list[str]) -> list[str]:
    ordered = list(dict.fromkeys(codes))
    known = {p["permissionCode"] for p in db[C.PERMISSIONS].find({}, {"_id": 0, "permissionCode": 1})}
    unknown = [c for c in ordered if c not in known]
    if unknown:
        raise unprocessable(f"Unknown permission: {', '.join(unknown)}")
    return ordered


def _next_role_id(db: Database) -> str:
    used = {r["roleId"] for r in db[C.ROLES].find({}, {"_id": 0, "roleId": 1})}
    n = 1
    while f"R-{n:02d}" in used:
        n += 1
    return f"R-{n:02d}"


def _role_code(db: Database, name: str) -> str:
    base = re.sub(r"[^A-Z0-9]+", "_", name.upper()).strip("_") or "ROLE"
    taken = {r["roleCode"] for r in db[C.ROLES].find({}, {"_id": 0, "roleCode": 1})}
    code, n = base, 2
    while code in taken:
        code, n = f"{base}_{n}", n + 1
    return code


def _write_grants(db: Database, role_id: str, codes: list[str]) -> tuple[list[str], list[str]]:
    """Make the role's grants exactly `codes`. Returns (added, removed)."""
    before = {g["permissionCode"] for g in db[C.ROLE_PERMISSIONS].find({"roleId": role_id}, {"_id": 0, "permissionCode": 1})}
    db[C.ROLE_PERMISSIONS].delete_many({"roleId": role_id, "permissionCode": {"$nin": codes}})
    for code in codes:
        db[C.ROLE_PERMISSIONS].update_one({"roleId": role_id, "permissionCode": code},
                                          {"$setOnInsert": {"roleId": role_id, "permissionCode": code, "createdAt": utcnow()}}, upsert=True)
    return sorted(set(codes) - before), sorted(before - set(codes))


def create_role(db: Database, name: str, description: str, permissions: list[str]) -> dict[str, Any]:
    name = _check_name(db, name)
    codes = _check_codes(db, permissions)
    now = utcnow()
    role = {"roleId": _next_role_id(db), "roleCode": _role_code(db, name), "roleName": name, "description": description.strip(),
            "isSystem": False, "allFacilities": True, "isActive": True, "createdAt": now, "updatedAt": now}
    db[C.ROLES].insert_one(dict(role))
    _write_grants(db, role["roleId"], codes)
    return role


def update_role(db: Database, role_id: str, name: str | None, description: str | None) -> dict[str, Any]:
    """Rename / re-describe a role. Built-in roles keep their name (the code and some rules refer to them)."""
    role = _role_or_404(db, role_id)
    changes: dict[str, Any] = {}
    if name is not None:
        new_name = _check_name(db, name, exclude_id=role_id)
        if new_name != role["roleName"]:
            if role.get("isSystem"):
                raise conflict(f"'{role['roleName']}' is a built-in role and cannot be renamed")
            changes["roleName"] = new_name
    if description is not None:
        changes["description"] = description.strip()
    if changes:
        changes["updatedAt"] = utcnow()
        db[C.ROLES].update_one({"roleId": role_id}, {"$set": changes})
        if "roleName" in changes:  # users.appRole mirrors the role name
            db[C.USERS].update_many({"roleId": role_id}, {"$set": {"appRole": changes["roleName"]}})
    return _role_or_404(db, role_id)


def set_role_permissions(db: Database, role_id: str, permissions: list[str]) -> tuple[dict[str, Any], list[str], list[str]]:
    role = _role_or_404(db, role_id)
    if role_id == ADMIN_ROLE_ID:
        raise conflict("The Administrator role always holds every permission and cannot be changed")
    codes = _check_codes(db, permissions)
    added, removed = _write_grants(db, role_id, codes)
    db[C.ROLES].update_one({"roleId": role_id}, {"$set": {"updatedAt": utcnow()}})
    return role, added, removed


def delete_role(db: Database, role_id: str) -> dict[str, Any]:
    role = _role_or_404(db, role_id)
    if role.get("isSystem"):
        raise conflict(f"'{role['roleName']}' is a built-in role and cannot be deleted")
    members = db[C.USERS].count_documents({"$or": [{"roleId": role_id}, {"appRole": role["roleName"]}]})
    if members:
        raise conflict(f"{members} user{'s' if members != 1 else ''} still hold the role '{role['roleName']}'. Move them to another role first")
    db[C.ROLE_PERMISSIONS].delete_many({"roleId": role_id})
    db[C.ROLES].delete_one({"roleId": role_id})
    return role
