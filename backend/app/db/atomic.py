"""All-or-nothing multi-collection writes that work on a standalone MongoDB (and mongomock).

Real multi-document transactions need a replica set AND a session handed to every repository call. This helper
gives the same outcome for our flows without either: it snapshots the documents in scope, and if the block
raises, puts every collection back exactly as it was (re-inserting deleted docs, restoring changed ones,
removing created ones). Scopes must be narrow filters; keep the block short.
"""
from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Any, Iterator, Mapping

from pymongo.database import Database

log = logging.getLogger(__name__)


@contextmanager
def atomic(db: Database, scopes: Mapping[str, Mapping[str, Any]]) -> Iterator[None]:
    before = {name: {d["_id"]: d for d in db[name].find(dict(flt))} for name, flt in scopes.items()}
    try:
        yield
    except BaseException:
        for name, flt in scopes.items():
            col, snap = db[name], before[name]
            try:
                for d in col.find(dict(flt), {"_id": 1}):
                    if d["_id"] not in snap:
                        col.delete_one({"_id": d["_id"]})
                for _id, doc in snap.items():
                    col.replace_one({"_id": _id}, doc, upsert=True)
            except Exception:  # never mask the original error
                log.exception("rollback of %s failed", name)
        raise
