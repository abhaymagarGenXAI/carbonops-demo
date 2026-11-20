"""Local-disk evidence storage. Files never leave the server and are only reachable through authenticated endpoints.

Safety rules: extension whitelist + content sniffing (a renamed .exe/.txt is refused), size cap, server-generated
storage names (the client's file name is metadata only, never a path), SHA-256 recorded for integrity.
"""
from __future__ import annotations

import hashlib
import io
import os
import re
import uuid
import zipfile
from pathlib import Path
from typing import BinaryIO

from fastapi import HTTPException, status

from app.core.config import get_settings

# extension -> (document format label, media type)
ALLOWED: dict[str, tuple[str, str]] = {
    "pdf": ("PDF", "application/pdf"),
    "xlsx": ("XLSX", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
    "csv": ("CSV", "text/csv"),
    "docx": ("DOCX", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
}
_ZIP_MARKER = {"xlsx": "xl/workbook.xml", "docx": "word/document.xml"}


def upload_root() -> Path:
    root = Path(get_settings().upload_dir).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def clean_name(filename: str) -> str:
    name = os.path.basename((filename or "").replace("\\", "/"))
    name = re.sub(r"[\x00-\x1f\x7f]", "", name).strip()
    return name[:255]


def extension(filename: str) -> str:
    ext = clean_name(filename).rsplit(".", 1)[-1].lower() if "." in clean_name(filename) else ""
    if ext not in ALLOWED:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            f"Unsupported file type. Allowed: {', '.join('.' + e for e in ALLOWED)}")
    return ext


def read_limited(fh: BinaryIO, max_bytes: int) -> bytes:
    data = fh.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, f"File exceeds the {max_bytes // (1024 * 1024)} MB limit")
    if not data:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "The file is empty")
    return data


def verify_content(ext: str, content: bytes) -> None:
    """The bytes must really be what the extension claims."""
    bad = HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"File content does not match a valid .{ext} file")
    if ext == "pdf":
        if not content.startswith(b"%PDF-"):
            raise bad
    elif ext in _ZIP_MARKER:
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as z:
                if _ZIP_MARKER[ext] not in z.namelist():
                    raise bad
        except zipfile.BadZipFile:
            raise bad from None
    elif ext == "csv":
        if b"\x00" in content:
            raise bad


def human_size(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f} KB"
    return f"{n / (1024 * 1024):.1f} MB"


def store(doc_id: str, ext: str, content: bytes) -> tuple[str, str]:
    """Writes atomically; returns (stored_name, sha256)."""
    stored = f"{doc_id}-{uuid.uuid4().hex}.{ext}"
    root = upload_root()
    tmp = root / f".{stored}.part"
    tmp.write_bytes(content)
    os.replace(tmp, root / stored)
    return stored, hashlib.sha256(content).hexdigest()


def path_of(stored_name: str) -> Path | None:
    root = upload_root()
    p = (root / stored_name).resolve()
    if root not in p.parents or not p.is_file():  # also blocks any traversal in a tampered record
        return None
    return p


def remove(stored_name: str | None) -> None:
    if stored_name and (p := path_of(stored_name)):
        p.unlink(missing_ok=True)
