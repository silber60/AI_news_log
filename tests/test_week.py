"""KST ISO-week math (COLL-01): never read the runner's UTC clock as the week."""

from datetime import UTC, date, datetime

import pytest

from newsletter.errors import InvalidWeekError
from newsletter.week import parse_week, previous_iso_week, week_label


@pytest.mark.parametrize(
    ("now", "expected"),
    [
        ("2026-11-01T23:00:00", "2026-W44"),  # Mon 08:00 KST cron
        ("2026-11-02T01:30:00", "2026-W44"),  # late cron
        ("2026-11-04T05:00:00", "2026-W44"),  # Wednesday manual run
        ("2026-12-27T23:00:00", "2026-W52"),
        ("2027-01-03T23:00:00", "2026-W53"),  # ISO week 53 (HF rejects week=)
        ("2021-01-03T23:00:00", "2020-W53"),
    ],
)
def test_previous_iso_week_uses_kst(now, expected):
    assert previous_iso_week(datetime.fromisoformat(now).replace(tzinfo=UTC)) == expected


def test_previous_iso_week_rejects_naive_datetime():
    with pytest.raises(ValueError):
        previous_iso_week(datetime(2026, 11, 2, 8, 0))


def test_parse_week_returns_monday_and_sunday():
    assert parse_week("2026-W44") == (date(2026, 10, 26), date(2026, 11, 1))
    assert parse_week("2026-W53") == (date(2026, 12, 28), date(2027, 1, 3))


@pytest.mark.parametrize("bad", ["2026-W54", "2025-W53", "2026-W00", "abc", "2026-w44", ""])
def test_parse_week_rejects_invalid(bad):
    with pytest.raises(InvalidWeekError):
        parse_week(bad)


def test_week_label():
    assert week_label(date(2026, 10, 26), date(2026, 11, 1)) == "10/26(월) ~ 11/1(일)"
