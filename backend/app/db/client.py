"""PyMongo connection management.

PyMongo's MongoClient is thread-safe and pools connections, so we keep one
process-wide instance. FastAPI runs our sync (`def`) endpoints in a threadpool,
which is exactly the usage model PyMongo is designed for.
"""
from __future__ import annotations

import logging
from threading import Lock

from pymongo import MongoClient
from pymongo.database import Database

from app.core.config import get_settings

log = logging.getLogger(__name__)

_client: MongoClient | None = None
_db_override: Database | None = None
_lock = Lock()


def get_client() -> MongoClient:
    global _client
    if _client is None:
        with _lock:
            if _client is None:
                s = get_settings()
                _client = MongoClient(
                    s.mongodb_uri,
                    tz_aware=True,  # datetimes come back timezone-aware (UTC)
                    serverSelectionTimeoutMS=8000,
                    appname="carbonops-api",
                )
    return _client


def get_database() -> Database:
    if _db_override is not None:
        return _db_override
    return get_client()[get_settings().mongodb_db_name]


def override_database(db: Database | None) -> None:
    """Test hook: point the app at a different (e.g. mongomock) database."""
    global _db_override
    _db_override = db


def close_client() -> None:
    global _client
    if _client is not None:
        _client.close()
        _client = None
