"""Idempotent seeder:  python -m app.seed.seed [--reset --yes]

Loads the same dataset the old front-end shipped as `src/lib/mock-data.ts`.
Existing documents are never overwritten (upsert with $setOnInsert), so it is safe to run
against the `carbon_ops` database that already contains Mongoose-created facilities/assets.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Callable

from app.services.iam import ensure_iam
from app.services.masters import ensure_masters
from app.core.config import get_settings
from app.core.security import hash_password
from app.db import collections as C
from app.db.client import get_database
from app.db.indexes import ensure_indexes
from app.repositories.asset import AssetRepository
from app.repositories.audit import AuditRepository
from app.repositories.base import BaseRepository
from app.repositories.document import DocumentRepository
from app.repositories.emission import EmissionRecordRepository
from app.repositories.emission_factor import EmissionFactorRepository
from app.repositories.energy import EnergyRecordRepository
from app.repositories.facility import FacilityRepository
from app.repositories.initiative import InitiativeRepository
from app.repositories.reference import REFERENCE_KEYS, ReferenceRepository
from app.repositories.submission import SubmissionRepository
from app.repositories.user import UserRepository
from app.utils.time import parse_display, utcnow

SEED_FILE = Path(__file__).with_name("seed_data.json")

# display role (as shown in the Users table) -> authorization role used by UI + API
APP_ROLE_BY_ROLE = {
    "Operations Data Entry": "Plant Engineer",
    "Facility Engineer": "Plant Engineer",
    "Sustainability Analyst": "Sustainability Manager",
    "Reviewer / Approver": "Sustainability Manager",
    "Administrator": "Administrator",
}


def upsert_many(
    repo: BaseRepository, items: list[dict[str, Any]], *, seq: bool = True,
    transform: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
) -> tuple[int, int]:
    created = skipped = 0
    for i, item in enumerate(items):
        doc = repo.to_db(transform(dict(item)) if transform else dict(item))
        now = utcnow()
        doc.setdefault("createdAt", now)
        doc.setdefault("updatedAt", now)
        if seq:
            doc["seq"] = i
        res = repo.col.update_one({repo.id_field: doc[repo.id_field]}, {"$setOnInsert": doc}, upsert=True)
        if res.upserted_id is not None:
            created += 1
        else:
            skipped += 1
    return created, skipped


def _submission(item: dict[str, Any]) -> dict[str, Any]:
    ts = parse_display(item["updatedAt"])
    status = item["status"]
    item.update(
        updatedAt=ts, createdAt=ts, reviewAction="None",
        submittedAt=None if status == "Draft" else ts,
        reviewedAt=ts if status in ("Approved", "Rejected") else None,
    )
    return item


def _audit(item: dict[str, Any]) -> dict[str, Any]:
    item["at"] = parse_display(item["at"])
    return item


def run(reset: bool = False) -> dict[str, tuple[int, int]]:
    db = get_database()
    settings = get_settings()
    data = json.loads(SEED_FILE.read_text(encoding="utf-8"))

    if reset:
        for name in C.ALL:
            db[name].delete_many({})
    ensure_indexes(db)

    def user_tx(u: dict[str, Any]) -> dict[str, Any]:
        u["email"] = u["email"].strip().lower()
        u["appRole"] = APP_ROLE_BY_ROLE[u["role"]]
        try:
            u["lastLogin"] = parse_display(u["lastLogin"])
        except ValueError:
            u["lastLogin"] = None
        u["passwordHash"] = hash_password(settings.seed_default_password)
        return u

    report = {
        "facilities": upsert_many(FacilityRepository(db), data["facilities"], seq=False),
        "assets": upsert_many(AssetRepository(db), data["assets"], seq=False),
        "submissions": upsert_many(SubmissionRepository(db), data["submissions"], transform=_submission),
        "energy_records": upsert_many(EnergyRecordRepository(db), data["energyRecords"]),
        "emission_records": upsert_many(EmissionRecordRepository(db), data["emissionRecords"]),
        "emission_factors": upsert_many(EmissionFactorRepository(db), data["emissionFactors"]),
        "initiatives": upsert_many(InitiativeRepository(db), data["initiatives"]),
        "documents": upsert_many(DocumentRepository(db), data["documents"]),
        "users": upsert_many(UserRepository(db), data["users"], transform=user_tx),
        "audit_log": upsert_many(AuditRepository(db), data["audit"], seq=False, transform=_audit),
    }
    ensure_masters(db)  # production units, streams, sources, asset types, factor-version links
    ensure_iam(db)  # roles, permissions, grants, users.roleId, user_facilities, userId links
    ref = ReferenceRepository(db)
    made = 0
    for key in REFERENCE_KEYS:
        if ref.get_items(key) is None:
            ref.set_items(key, data[key])
            made += 1
    report["reference_data"] = (made, len(REFERENCE_KEYS) - made)
    return report


def main() -> None:
    ap = argparse.ArgumentParser(description="Seed the CarbonOps MongoDB database")
    ap.add_argument("--reset", action="store_true", help="DELETE all documents in every app collection first")
    ap.add_argument("--yes", action="store_true", help="confirm --reset")
    args = ap.parse_args()
    if args.reset and not args.yes:
        ap.error("--reset deletes data; re-run with --reset --yes to confirm")
    for name, (created, skipped) in run(reset=args.reset).items():
        print(f"{name:18s} created={created:<4d} already-present={skipped}")
    print(f"\nSeeded users can sign in with password: {get_settings().seed_default_password}")
    print("Demo logins: s.nair@carbonops.ongc (Plant Engineer), l.menon@carbonops.ongc (Sustainability Manager),")
    print("             m.sinha@carbonops.ongc (Administrator)")


if __name__ == "__main__":
    main()
