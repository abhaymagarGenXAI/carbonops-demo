from __future__ import annotations

from typing import Any

from app.db import collections as C
from app.repositories.base import BaseRepository
from app.utils.time import to_display


class UserRepository(BaseRepository):
    collection_name = C.USERS
    id_field = "userId"

    def serialize(self, doc: dict[str, Any]) -> dict[str, Any]:
        doc.pop("passwordHash", None)  # never leaves the repository layer
        doc["lastLogin"] = to_display(doc.get("lastLogin")) or "—"
        doc.pop("createdAt", None)
        doc.pop("updatedAt", None)
        doc.pop("seq", None)
        return doc

    @staticmethod
    def normalize_email(email: str) -> str:
        return email.strip().lower()

    def get_raw_by_email(self, email: str) -> dict[str, Any] | None:
        return self.col.find_one({"email": self.normalize_email(email)}, {"_id": 0, "__v": 0})

    def next_id(self) -> str:
        """Never hands out an id that exists or ever existed: records and the audit trail still point at deleted users'
        ids (submittedById, createdById, audit userId...), and a new person must not inherit someone else's history.
        Every user creation/deletion is audited with the id as target, so the audit trail is the tombstone list."""
        audit = self.col.database[C.AUDIT_LOG]
        n = self.count() + 1
        while self.exists(f"USR-{n:02d}") or audit.count_documents({"target": f"USR-{n:02d}"}, limit=1) > 0:
            n += 1
        return f"USR-{n:02d}"
