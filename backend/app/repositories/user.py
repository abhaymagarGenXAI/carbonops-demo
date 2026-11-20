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
        n = self.count() + 1
        while self.exists(f"USR-{n:02d}"):
            n += 1
        return f"USR-{n:02d}"
