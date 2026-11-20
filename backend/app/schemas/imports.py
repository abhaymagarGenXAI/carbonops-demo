from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from app.schemas.common import MONTH_PATTERN, CamelModel
from app.schemas.submission import ActivityDataIn


class ImportRowOut(CamelModel):
    row: int  # row number in the source sheet (header = 1)
    facility_id: str | None = None
    facility_name: str | None = None
    unit: str | None = None
    month: str | None = None
    data: dict[str, Any] | None = None
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    existing_status: str | None = None
    importable: bool = False


class ImportPreviewOut(CamelModel):
    file_name: str
    sheet: str | None = None
    row_count: int
    importable_rows: int
    error_rows: int
    unmapped_columns: list[str] = Field(default_factory=list)
    rows: list[ImportRowOut]


class ImportCommitRow(CamelModel):
    facility_id: str = Field(min_length=1)
    unit: str = Field(min_length=1)
    month: str = Field(pattern=MONTH_PATTERN)
    data: ActivityDataIn


class ImportCommitRequest(CamelModel):
    status: Literal["Draft", "Submitted"] = "Draft"
    rows: list[ImportCommitRow] = Field(min_length=1, max_length=500)


class ImportCommitResultRow(CamelModel):
    facility_id: str
    month: str
    ok: bool
    submission_id: str | None = None
    detail: str = ""


class ImportCommitOut(CamelModel):
    saved: int
    failed: int
    results: list[ImportCommitResultRow]
