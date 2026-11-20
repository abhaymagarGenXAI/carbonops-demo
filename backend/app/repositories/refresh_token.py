from __future__ import annotations

from datetime import datetime
from typing import Any

from app.db import collections as C
from app.repositories.base import BaseRepository
from app.utils.time import utcnow


class RefreshTokenRepository(BaseRepository):
    """Server-side record of issued refresh tokens (enables rotation, logout, reuse detection)."""

    collection_name = C.REFRESH_TOKENS
    id_field = "jti"
    default_sort: list[tuple[str, int]] = []

    def issue(self, *, jti: str, user_id: str, expires_at: datetime) -> None:
        self.col.insert_one(
            {"jti": jti, "userId": user_id, "expiresAt": expires_at, "createdAt": utcnow(), "revokedAt": None, "replacedBy": None}
        )

    def find(self, jti: str) -> dict[str, Any] | None:
        return self.col.find_one({"jti": jti}, {"_id": 0})

    def claim(self, jti: str, replaced_by: str) -> bool:
        """Atomically mark a token as used. Only one concurrent caller can win."""
        res = self.col.update_one(
            {"jti": jti, "revokedAt": None}, {"$set": {"revokedAt": utcnow(), "replacedBy": replaced_by}}
        )
        return res.modified_count == 1

    def revoke(self, jti: str, replaced_by: str | None = None) -> None:
        self.col.update_one(
            {"jti": jti, "revokedAt": None}, {"$set": {"revokedAt": utcnow(), "replacedBy": replaced_by}}
        )

    def revoke_all_for_user(self, user_id: str) -> None:
        self.col.update_many({"userId": user_id, "revokedAt": None}, {"$set": {"revokedAt": utcnow()}})
