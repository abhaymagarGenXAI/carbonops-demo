from __future__ import annotations

from typing import Literal

from pydantic import Field

from app.schemas.common import MONTH_PATTERN, CamelModel


class DocumentVersion(CamelModel):
    version: str
    at: str
    by: str
    note: str = ""


class DocumentCreate(CamelModel):
    """Metadata-only registration (legacy). Real files go through POST /documents/upload."""

    name: str = Field(min_length=1, max_length=255)
    type: str = Field(min_length=1)
    facility_id: str = Field(min_length=1)
    month: str = Field(pattern=MONTH_PATTERN)
    size: str = Field(min_length=1)
    format: Literal["PDF", "XLSX", "CSV", "DOCX"]
    linked_record: str = ""


class DocumentOut(CamelModel):
    id: str
    name: str
    type: str
    facility_id: str
    month: str
    size: str
    format: str
    uploaded_by: str
    uploaded_at: str
    linked_record: str = ""
    version: str
    versions: list[DocumentVersion] = Field(default_factory=list)
    size_bytes: int | None = None
    sha256: str | None = None
    has_file: bool = False  # False for legacy metadata-only records
