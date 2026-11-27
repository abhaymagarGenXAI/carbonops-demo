from __future__ import annotations

import time
import uuid
from typing import Any

from app.db import collections as C
from app.repositories.base import BaseRepository
from app.utils.time import to_display, utcnow


class AuditRepository(BaseRepository):
    collection_name = C.AUDIT_LOG
    id_field = "auditId"
    # `ns` is a monotonic tie-breaker: Mongo datetimes only have millisecond precision, so two entries
    # written in the same millisecond would otherwise order by their random id.
    default_sort = [("at", -1), ("ns", -1), ("auditId", -1)]

    def serialize(self, doc: dict[str, Any]) -> dict[str, Any]:
        doc["at"] = to_display(doc.get("at"))
        for k in ("createdAt", "updatedAt", "seq", "ns"):
            doc.pop(k, None)
        return doc

    # The audit trail is append-only: nothing in the application may change or remove an entry.
    def update(self, id_: str, changes):  # type: ignore[override]
        raise NotImplementedError("audit entries are immutable")

    def delete(self, id_: str):  # type: ignore[override]
        raise NotImplementedError("audit entries are immutable")

    def log(self, *, who: str, action: str, target: str, detail: str, user_id: str | None = None) -> None:
        self.create(
            {
                "id": f"AUD-{uuid.uuid4().hex[:8]}",
                "at": utcnow(),
                "ns": time.time_ns(),
                "who": who,
                "userId": user_id,
                "action": action,
                "target": target,
                "detail": detail,
            }
        )
