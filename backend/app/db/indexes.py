from __future__ import annotations

import logging

from pymongo import ASCENDING, DESCENDING
from pymongo.database import Database
from pymongo.errors import OperationFailure

from app.db import collections as C

log = logging.getLogger(__name__)


def ensure_indexes(db: Database) -> None:
    """Idempotent. Index specs for facilities/assets/submissions are identical to the
    ones Mongoose created (same keys/options => same index names => no conflict).
    A failure (e.g. legacy duplicate data blocking a unique index) is logged, not fatal."""
    specs: list[tuple[str, list[tuple[str, int]], dict]] = [
        (C.FACILITIES, [("facilityId", ASCENDING)], {"unique": True}),
        (C.ASSETS, [("assetId", ASCENDING)], {"unique": True}),
        (C.ASSETS, [("facilityId", ASCENDING)], {}),
        (C.SUBMISSIONS, [("submissionId", ASCENDING)], {"unique": True}),
        (C.SUBMISSIONS, [("facilityId", ASCENDING)], {}),
        (C.SUBMISSIONS, [("month", ASCENDING)], {}),
        (C.SUBMISSIONS, [("facilityId", ASCENDING), ("month", ASCENDING)], {"unique": True}),
        (C.ENERGY_RECORDS, [("recordId", ASCENDING)], {"unique": True}),
        (C.ENERGY_RECORDS, [("facilityId", ASCENDING), ("month", ASCENDING)], {}),
        (C.EMISSION_RECORDS, [("emissionId", ASCENDING)], {"unique": True}),
        (C.EMISSION_RECORDS, [("facilityId", ASCENDING), ("month", ASCENDING)], {}),
        (C.EMISSION_RECORDS, [("factorId", ASCENDING)], {}),
        (C.EMISSION_FACTORS, [("factorId", ASCENDING)], {"unique": True}),
        (C.INITIATIVES, [("initiativeId", ASCENDING)], {"unique": True}),
        (C.DOCUMENTS, [("documentId", ASCENDING)], {"unique": True}),
        (C.USERS, [("userId", ASCENDING)], {"unique": True}),
        (C.USERS, [("email", ASCENDING)], {"unique": True}),
        (C.AUDIT_LOG, [("auditId", ASCENDING)], {"unique": True}),
        (C.AUDIT_LOG, [("at", DESCENDING)], {}),
        (C.REFRESH_TOKENS, [("jti", ASCENDING)], {"unique": True}),
        (C.REFRESH_TOKENS, [("userId", ASCENDING)], {}),
        # TTL: Mongo deletes expired refresh-token records automatically
        (C.REFRESH_TOKENS, [("expiresAt", ASCENDING)], {"expireAfterSeconds": 0}),
        (C.REFERENCE_DATA, [("key", ASCENDING)], {"unique": True}),
    ]
    for coll, keys, opts in specs:
        try:
            db[coll].create_index(keys, **opts)
        except OperationFailure as exc:
            log.warning("Could not create index %s on %s: %s", keys, coll, exc)
