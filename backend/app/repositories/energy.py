from __future__ import annotations

from app.db import collections as C
from app.repositories.base import BaseRepository


class EnergyRecordRepository(BaseRepository):
    collection_name = C.ENERGY_RECORDS
    id_field = "recordId"

    def list_visible(self, filters=None, limit: int = 1000):
        """Records whose submission is Draft/Rejected are hidden (kept in the DB so meter/invoice/cost survive resubmission)."""
        return self.list({**(filters or {}), "excluded": {"$ne": True}}, limit)
