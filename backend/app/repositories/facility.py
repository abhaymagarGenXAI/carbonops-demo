from __future__ import annotations

from app.db import collections as C
from app.repositories.base import BaseRepository


class FacilityRepository(BaseRepository):
    collection_name = C.FACILITIES
    id_field = "facilityId"
    default_sort = [("name", 1)]  # same ordering the Mongoose repository used
