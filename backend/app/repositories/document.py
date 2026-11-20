from __future__ import annotations

import uuid

from app.db import collections as C
from app.repositories.base import BaseRepository


class DocumentRepository(BaseRepository):
    collection_name = C.DOCUMENTS
    id_field = "documentId"

    @staticmethod
    def new_id(facility_code: str) -> str:
        return f"DOC-{facility_code.upper()}-{uuid.uuid4().hex[:6].upper()}"
