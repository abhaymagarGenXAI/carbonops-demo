"""Spreadsheet formula-injection protection (CWE-1236).

Text that starts with = + - @ (or a tab / carriage return) is executed as a formula when a spreadsheet opens it. Every value that
can originate from a user (names, remarks, comments, ...) must go through these helpers before it is written to Excel or CSV.
"""
from __future__ import annotations

from typing import Any, Iterable

TRIGGERS = ("=", "+", "-", "@", "\t", "\r")


def _risky(v: Any) -> bool:
    return isinstance(v, str) and v.startswith(TRIGGERS)


def csv_cell(v: Any) -> Any:
    """CSV has no cell types, so the standard defence is a leading apostrophe."""
    return "'" + v if _risky(v) else v


def csv_row(row: Iterable[Any]) -> list[Any]:
    return [csv_cell(v) for v in row]


def append_row(ws, row: Iterable[Any]) -> None:
    """Append `row` to an openpyxl worksheet, forcing risky text to be stored as a plain string instead of a formula."""
    row = list(row)
    ws.append(row)
    cells = ws[ws.max_row]
    for cell, v in zip(cells, row):
        if _risky(v):
            cell.value = v
            cell.data_type = "s"
