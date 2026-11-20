from __future__ import annotations

from app.db import collections as C
from app.repositories.base import BaseRepository


class EmissionFactorRepository(BaseRepository):
    collection_name = C.EMISSION_FACTORS
    id_field = "factorId"

    def next_id(self) -> str:
        n = self.count() + 1
        while self.exists(f"EF-{n:02d}"):
            n += 1
        return f"EF-{n:02d}"
