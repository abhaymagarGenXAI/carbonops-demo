from __future__ import annotations

from typing import Any

from app.db import collections as C
from app.repositories.base import BaseRepository
from pymongo import ReturnDocument

from app.utils.time import to_display, to_iso, utcnow


class SubmissionRepository(BaseRepository):
    collection_name = C.SUBMISSIONS
    id_field = "submissionId"

    def serialize(self, doc: dict[str, Any]) -> dict[str, Any]:
        # The UI renders updatedAt verbatim as "YYYY-MM-DD HH:MM".
        doc["updatedAt"] = to_display(doc.get("updatedAt"))
        doc["submittedAt"] = to_display(doc.get("submittedAt"))
        doc["reviewedAt"] = to_display(doc.get("reviewedAt"))
        doc["createdAt"] = to_iso(doc.get("createdAt"))
        doc["revision"] = int(doc.get("revision") or 0)
        doc.pop("seq", None)
        return doc

    def update(self, id_: str, changes: dict[str, Any]) -> dict[str, Any] | None:
        """Every write bumps `revision` atomically — the token clients send back to prove they saw the latest version."""
        ch = self.to_db({k: v for k, v in changes.items() if k not in ("id", "revision")})
        ch.pop(self.id_field, None)
        ch["updatedAt"] = utcnow()
        doc = self.col.find_one_and_update({self.id_field: id_}, {"$set": ch, "$inc": {"revision": 1}},
                                           projection={"_id": 0, "__v": 0}, return_document=ReturnDocument.AFTER)
        return self.to_public(doc)

    def get_by_facility_month(self, facility_id: str, month: str) -> dict[str, Any] | None:
        doc = self.col.find_one({"facilityId": facility_id, "month": month}, {"_id": 0, "__v": 0})
        return doc  # raw (service layer needs real datetimes / status)
