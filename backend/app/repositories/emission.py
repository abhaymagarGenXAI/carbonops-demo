from __future__ import annotations

from app.db import collections as C
from app.repositories.base import BaseRepository


class EmissionRecordRepository(BaseRepository):
    collection_name = C.EMISSION_RECORDS
    id_field = "emissionId"
