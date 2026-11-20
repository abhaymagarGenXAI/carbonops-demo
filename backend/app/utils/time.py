from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from app.core.config import get_settings

DISPLAY_FMT = "%Y-%m-%d %H:%M"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def as_aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def to_display(dt: datetime | None) -> str | None:
    """'2026-08-04 10:42' in APP_TIMEZONE — the format the UI already renders."""
    if dt is None:
        return None
    tz = ZoneInfo(get_settings().app_timezone)
    return as_aware(dt).astimezone(tz).strftime(DISPLAY_FMT)


def to_iso(dt: datetime | None) -> str | None:
    return as_aware(dt).isoformat() if dt else None


def parse_display(value: str) -> datetime:
    """Parse a 'YYYY-MM-DD HH:MM' (or date-only) seed string in APP_TIMEZONE -> UTC."""
    tz = ZoneInfo(get_settings().app_timezone)
    fmt = DISPLAY_FMT if " " in value.strip() else "%Y-%m-%d"
    return datetime.strptime(value.strip(), fmt).replace(tzinfo=tz).astimezone(timezone.utc)
