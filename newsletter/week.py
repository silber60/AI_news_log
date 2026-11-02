"""ISO week math in Asia/Seoul. Never use the runner's UTC clock directly."""

import re
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from newsletter.errors import InvalidWeekError

KST = ZoneInfo("Asia/Seoul")
WEEK_RE = re.compile(r"^(\d{4})-W(\d{2})$")
_WEEKDAYS_KO = "월화수목금토일"


def previous_iso_week(now: datetime) -> str:
    """Return the ISO week before `now` (tz-aware) in KST, e.g. "2026-W44"."""
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    y, w, _ = (now.astimezone(KST).date() - timedelta(days=7)).isocalendar()
    return f"{y}-W{w:02d}"


def parse_week(s: str) -> tuple[date, date]:
    """Validate "YYYY-Www" and return its (Monday, Sunday) dates."""
    m = WEEK_RE.match(s or "")
    if not m:
        raise InvalidWeekError("week must look like YYYY-Www")
    try:
        mon = date.fromisocalendar(int(m[1]), int(m[2]), 1)
    except ValueError as e:
        raise InvalidWeekError("week does not exist in that ISO year") from e
    return mon, mon + timedelta(days=6)


def week_label(mon: date, sun: date) -> str:
    """Header label such as "10/26(월) ~ 11/1(일)"."""

    def one(d: date) -> str:
        return f"{d.month}/{d.day}({_WEEKDAYS_KO[d.weekday()]})"

    return f"{one(mon)} ~ {one(sun)}"
