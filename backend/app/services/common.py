from __future__ import annotations

from typing import Any, Mapping

from fastapi import HTTPException, status
from pymongo.database import Database

from app.repositories.audit import AuditRepository


def not_found(what: str, id_: str) -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, f"{what} '{id_}' was not found")


def forbidden(msg: str) -> HTTPException:
    return HTTPException(status.HTTP_403_FORBIDDEN, msg)


def conflict(msg: str) -> HTTPException:
    return HTTPException(status.HTTP_409_CONFLICT, msg)


def unprocessable(msg: str) -> HTTPException:
    return HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, msg)


def audit(db: Database, user: Mapping[str, Any], action: str, target: str, detail: str) -> None:
    """Every state-changing operation leaves an audit-trail entry attributed to the real user."""
    AuditRepository(db).log(who=user["name"], user_id=user["id"], action=action, target=target, detail=detail)
