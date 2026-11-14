"""
When people were last active, and who counts as inactive.

``last_active`` on a person is an ISO date (``2026-03-01``) or ``never`` when a scan looked
for activity and found none. People without it are of unknown activity and never count as
inactive: missing data is not evidence of absence.
"""

from datetime import date, datetime, timedelta
from typing import Any, Iterable, Optional, Union

NEVER = "never"
DEFAULT_INACTIVE_DAYS = 90

Activity = Union[date, str]  # a date, or NEVER


def parse_activity(value: Any) -> Optional[Activity]:
    """``last_active`` as a date, NEVER or None (unknown); raises ValueError if invalid."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if value == NEVER:
        return NEVER
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError:
            pass
        try:  # a timestamp such as 2026-03-01T10:00:00Z, as the GitHub API returns
            return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
        except ValueError:
            pass
    raise ValueError(f"must be a date such as 2026-03-01 or {NEVER!r}, got {value!r}")


def activity_text(value: Any) -> str:
    """For messages: 'last active 2026-03-01' or 'no activity seen'."""
    parsed = parse_activity(value)
    return "no activity seen" if parsed == NEVER else f"last active {parsed}"


def is_inactive(value: Any, days: int, today: Optional[date] = None) -> bool:
    """Whether ``last_active`` is NEVER or more than ``days`` days before ``today``."""
    parsed = parse_activity(value)
    if isinstance(parsed, date):
        return parsed < (today or date.today()) - timedelta(days=days)
    return parsed == NEVER


def latest(values: Iterable[Any]) -> Optional[str]:
    """The most recent of several ``last_active`` values (dates win over NEVER), as text."""
    parsed = [p for p in (parse_activity(v) for v in values) if p is not None]
    dates = [p for p in parsed if isinstance(p, date)]
    if dates:
        return max(dates).isoformat()
    return NEVER if parsed else None
