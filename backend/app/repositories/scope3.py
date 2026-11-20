from __future__ import annotations

import re

from app.db import collections as C
from app.repositories.base import BaseRepository

_NUM = re.compile(r"(\d+)$")


class Scope3Repository(BaseRepository):
    collection_name = C.SCOPE3_ENTRIES
    id_field = "entryId"

    def next_id(self) -> str:
        highest = 0
        for d in self.col.find({}, {"entryId": 1, "_id": 0}):
            m = _NUM.search(d.get("entryId", ""))
            if m:
                highest = max(highest, int(m.group(1)))
        return f"S3-{highest + 1:04d}"
