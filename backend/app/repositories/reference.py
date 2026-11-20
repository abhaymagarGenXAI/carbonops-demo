from __future__ import annotations

from typing import Any

from app.db import collections as C
from app.repositories.base import BaseRepository
from app.utils.time import utcnow

# Reference/config lists that the UI reads but that are not first-class entities.
REFERENCE_KEYS = (
    "workflows",
    "reportingPeriods",
    "assetCategories",
    "unitsOfMeasure",
    "roles",
    "recentActivity",
    "aiAlerts",
)


class ReferenceRepository(BaseRepository):
    collection_name = C.REFERENCE_DATA
    id_field = "key"
    default_sort: list[tuple[str, int]] = []

    def get_items(self, key: str) -> list[dict[str, Any]] | None:
        doc = self.col.find_one({"key": key}, {"_id": 0})
        return None if doc is None else list(doc.get("items", []))

    def set_items(self, key: str, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        self.col.update_one(
            {"key": key}, {"$set": {"items": items, "updatedAt": utcnow()}, "$setOnInsert": {"createdAt": utcnow()}}, upsert=True
        )
        return items
