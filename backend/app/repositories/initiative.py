from __future__ import annotations

import re

from app.db import collections as C
from app.repositories.base import BaseRepository

_NUM = re.compile(r"(\d+)$")


class InitiativeRepository(BaseRepository):
    collection_name = C.INITIATIVES
    id_field = "initiativeId"

    def next_id(self) -> str:
        highest = 100
        for d in self.col.find({}, {"initiativeId": 1, "_id": 0}):
            m = _NUM.search(d.get("initiativeId", ""))
            if m:
                highest = max(highest, int(m.group(1)))
        return f"INIT-{highest + 1}"
