"""Generic PyMongo repository.

Documents are stored with camelCase keys (matching the Mongoose schemas that were
already in the database) and a business key such as `facilityId`. The public
shape exposes that key as `id`, which is what the React app uses everywhere.
"""
from __future__ import annotations

from typing import Any, Iterable, Mapping

from pymongo import ReturnDocument
from pymongo.database import Database

from app.utils.time import to_iso, utcnow

_HIDDEN = {"_id", "__v"}


class BaseRepository:
    collection_name: str = ""
    id_field: str = "id"
    # None -> natural order. Seeded collections use `seq` to preserve the original array order.
    default_sort: list[tuple[str, int]] = [("seq", 1)]

    def __init__(self, db: Database):
        self.col = db[self.collection_name]

    # ------------------------------------------------------------------ mapping
    def serialize(self, doc: dict[str, Any]) -> dict[str, Any]:
        """Hook: turn datetimes into the strings the API exposes."""
        for key in ("createdAt", "updatedAt"):
            if key in doc:
                doc[key] = to_iso(doc[key]) if doc[key] is not None else None
        doc.pop("seq", None)
        return doc

    def to_public(self, doc: Mapping[str, Any] | None) -> dict[str, Any] | None:
        if doc is None:
            return None
        out = {k: v for k, v in doc.items() if k not in _HIDDEN}
        out["id"] = out.pop(self.id_field, None)
        return self.serialize(out)

    def to_db(self, data: Mapping[str, Any]) -> dict[str, Any]:
        d = dict(data)
        if "id" in d:
            d[self.id_field] = d.pop("id")
        return d

    # --------------------------------------------------------------------- reads
    def list(self, filters: Mapping[str, Any] | None = None, limit: int = 1000) -> list[dict[str, Any]]:
        cur = self.col.find(dict(filters or {}), {"_id": 0, "__v": 0})
        if self.default_sort:
            cur = cur.sort(self.default_sort)
        return [self.to_public(d) for d in cur.limit(limit)]  # type: ignore[misc]

    def get_raw(self, id_: str) -> dict[str, Any] | None:
        return self.col.find_one({self.id_field: id_}, {"_id": 0, "__v": 0})

    def get(self, id_: str) -> dict[str, Any] | None:
        return self.to_public(self.get_raw(id_))

    def exists(self, id_: str) -> bool:
        return self.col.count_documents({self.id_field: id_}, limit=1) > 0

    def count(self, filters: Mapping[str, Any] | None = None) -> int:
        return self.col.count_documents(dict(filters or {}))

    # -------------------------------------------------------------------- writes
    def _next_seq(self) -> int:
        """New documents sort first (the in-memory store used to prepend new rows)."""
        first = self.col.find_one({"seq": {"$exists": True}}, {"seq": 1}, sort=[("seq", 1)])
        return (first["seq"] - 1) if first else 0

    def create(self, data: Mapping[str, Any]) -> dict[str, Any]:
        """Raises pymongo.errors.DuplicateKeyError on a unique-key clash (mapped to HTTP 409)."""
        now = utcnow()
        doc = self.to_db(data)
        doc.setdefault("createdAt", now)
        doc.setdefault("updatedAt", now)
        if self.default_sort and self.default_sort[0][0] == "seq":
            doc.setdefault("seq", self._next_seq())
        self.col.insert_one(doc)
        return self.to_public(doc)  # type: ignore[return-value]

    def update(self, id_: str, changes: Mapping[str, Any]) -> dict[str, Any] | None:
        ch = self.to_db({k: v for k, v in changes.items() if k != "id"})
        ch.pop(self.id_field, None)  # the business key is immutable
        ch["updatedAt"] = utcnow()
        doc = self.col.find_one_and_update(
            {self.id_field: id_},
            {"$set": ch},
            projection={"_id": 0, "__v": 0},
            return_document=ReturnDocument.AFTER,
        )
        return self.to_public(doc)

    def delete(self, id_: str) -> bool:
        return self.col.delete_one({self.id_field: id_}).deleted_count > 0

    def insert_many_raw(self, docs: Iterable[dict[str, Any]]) -> int:
        docs = list(docs)
        if not docs:
            return 0
        return len(self.col.insert_many(docs).inserted_ids)
