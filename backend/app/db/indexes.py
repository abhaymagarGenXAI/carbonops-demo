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
        (C.ROLES, [("roleId", ASCENDING)], {"unique": True}),
        (C.ROLES, [("roleCode", ASCENDING)], {"unique": True}),
        (C.PERMISSIONS, [("permissionCode", ASCENDING)], {"unique": True}),
        (C.ROLE_PERMISSIONS, [("roleId", ASCENDING), ("permissionCode", ASCENDING)], {"unique": True}),
        (C.USER_FACILITIES, [("userId", ASCENDING), ("facilityId", ASCENDING)], {"unique": True}),
        (C.USER_FACILITIES, [("facilityId", ASCENDING)], {}),
        (C.ALERT_DISMISSALS, [("alertId", ASCENDING), ("fingerprint", ASCENDING)], {"unique": True}),
        (C.SCOPE3_ENTRIES, [("entryId", ASCENDING)], {"unique": True}),
        (C.SCOPE3_ENTRIES, [("month", ASCENDING), ("status", ASCENDING)], {}),
        (C.USERS, [("roleId", ASCENDING)], {}),
        (C.PRODUCTION_UNITS, [("unitId", ASCENDING)], {"unique": True}),
        (C.PRODUCTION_UNITS, [("facilityId", ASCENDING), ("unitName", ASCENDING)], {"unique": True}),
        (C.ASSET_TYPES, [("assetTypeId", ASCENDING)], {"unique": True}),
        (C.ASSET_TYPES, [("typeName", ASCENDING)], {"unique": True}),
        (C.UNITS_OF_MEASURE, [("uomId", ASCENDING)], {"unique": True}),
        (C.UNITS_OF_MEASURE, [("symbol", ASCENDING)], {"unique": True}),
        (C.ENERGY_STREAMS, [("streamId", ASCENDING)], {"unique": True}),
        (C.ENERGY_STREAMS, [("streamName", ASCENDING)], {"unique": True}),
        (C.EMISSION_SOURCES, [("sourceId", ASCENDING)], {"unique": True}),
        (C.EMISSION_SOURCES, [("sourceName", ASCENDING)], {"unique": True}),
        # partial: legacy rows without a source link must not collide on (null, validFrom)
        (C.EMISSION_FACTORS, [("emissionSourceId", ASCENDING), ("validFrom", ASCENDING)],
         {"unique": True, "partialFilterExpression": {"emissionSourceId": {"$type": "string"}}}),
        (C.EMISSION_RECORDS, [("emissionSourceId", ASCENDING)], {}),
        (C.EMISSION_RECORDS, [("factorVersionId", ASCENDING)], {}),
        (C.SCOPE3_ENTRIES, [("factorVersionId", ASCENDING)], {}),
        (C.SUBMISSIONS, [("unitId", ASCENDING)], {}),
    ]
    for coll, keys, opts in specs:
        try:
            db[coll].create_index(keys, **opts)
        except OperationFailure as exc:
            log.warning("Could not create index %s on %s: %s", keys, coll, exc)
