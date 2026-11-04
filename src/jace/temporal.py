"""Explicit memory expiry, not inferred dates or temporal reasoning."""
from __future__ import annotations

import re
from datetime import datetime, timezone

from .models import utc_now

_TIMESTAMP = re.compile(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})', re.ASCII)


def normalize_expiration(value: str | None) -> str | None:
    """Require an explicit offset and store one canonical UTC representation."""
    if value is None:
        return None
    if not isinstance(value, str) or not _TIMESTAMP.fullmatch(value) or value.endswith('-00:00'):
        raise ValueError('expires_at must be null or an ISO timestamp with an explicit timezone, e.g. 2026-12-01T18:00:00Z')
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        # datetime accepts offset minutes >= 60 by normalizing them; reject those.
        if value[-1] != 'Z' and (int(value[-5:-3]) > 23 or int(value[-2:]) > 59):
            raise ValueError('invalid offset')
        return parsed.astimezone(timezone.utc).isoformat(timespec='microseconds')
    except (ValueError, OverflowError) as error:
        raise ValueError('expires_at must be a valid timestamp with a known timezone') from error


def recall_time() -> str:
    return normalize_expiration(utc_now())


def eligible_for_recall(expires_at: str | None, at: str) -> bool:
    if expires_at is None:
        return True
    try:
        expiry = normalize_expiration(expires_at)
    except ValueError:
        return False  # A malformed stored timestamp must never grant recall.
    return expiry > at  # Both values are normalized UTC; equality means expired.
