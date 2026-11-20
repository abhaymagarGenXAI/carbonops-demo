from __future__ import annotations

from typing import Any

from app.db import collections as C
from app.repositories.base import BaseRepository


class AssetRepository(BaseRepository):
    collection_name = C.ASSETS
    id_field = "assetId"
    default_sort = [("name", 1)]

    def list_by_facility(self, facility_id: str) -> list[dict[str, Any]]:
        return self.list({"facilityId": facility_id})

    def count_by_facility(self, facility_id: str) -> int:
        return self.count({"facilityId": facility_id})
