from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

Status = Literal["Draft", "Submitted", "Under Review", "Approved", "Rejected"]
ReviewDecision = Literal["Approved", "Rejected", "Under Review"]
AppRole = str  # a role name; roles are administrator-managed, so this is no longer a fixed set
MONTH_PATTERN = r"^\d{4}-(0[1-9]|1[0-2])$"
DATE_PATTERN = r"^\d{4}-\d{2}-\d{2}$"


class CamelModel(BaseModel):
    """snake_case in Python, camelCase on the wire (what the React types use)."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, from_attributes=True)


class Message(CamelModel):
    detail: str


class DeleteResult(CamelModel):
    id: str
    deleted: bool
