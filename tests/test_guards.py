"""Send guards in run_deliver (05-01): pause switch, stale-week guard, outcome report and
the order of checks.

Every guard decides before any secret read, list fetch or SMTP connection (research Pattern 2).
"""

import json
import shutil
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
import respx

from newsletter import store, week
from newsletter.week import KST

FIXTURES = Path(__file__).parent / "fixtures"
ISSUE_ID = "2026-W44"
CREDENTIALS = (
    "SMTP_USER",
    "SMTP_PASSWORD",
    "TEST_RECIPIENT",
    "SUBSCRIBERS_CSV",
    "SUBSCRIBER_LIST_KEY",
    "UNSUBSCRIBE_LIST_KEY",
    "UNSUBSCRIBE_TOKEN_SECRET",
)


@pytest.fixture
def current_issue(archive_tmp):
    week = store.week_dir(ISSUE_ID)
    week.mkdir(parents=True)
    shutil.copy(FIXTURES / "issue_w44.json", week / "issue.json")
    store.write_current(ISSUE_ID)
    return week


@pytest.fixture
def gh_output(tmp_path, monkeypatch) -> Path:
    path = tmp_path / "github_output"
    path.write_text("", encoding="utf-8")
    monkeypatch.setenv("GITHUB_OUTPUT", str(path))
    return path


@pytest.fixture
def no_credentials(monkeypatch):
    for name in CREDENTIALS:
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def creds(monkeypatch):
    from newsletter.delivery import deliver

    monkeypatch.setattr(deliver, "SEND_PAUSE_SECONDS", 0)
    monkeypatch.setenv("SMTP_USER", "owner@example.com")
    monkeypatch.setenv("SMTP_PASSWORD", "pw")
    monkeypatch.setenv("TEST_RECIPIENT", "owner@example.com")
    monkeypatch.setenv("SUBSCRIBERS_CSV", "email,name\na@example.com,가\nb@example.com,\n")
    monkeypatch.setenv("UNSUBSCRIBE_TOKEN_SECRET", "guards-token-secret")  # 05-03 ledger key


def _report() -> dict:
    return json.loads((store.out_root() / "report.json").read_text(encoding="utf-8"))


# ------------------------------------------------------------------ pause (D-02)


@pytest.mark.parametrize("value", ["true", " TRUE ", "True"])
def test_paused_send_mails_nobody(
    value, current_issue, gh_output, no_credentials, fake_smtp, monkeypatch
):
    from newsletter.delivery.deliver import run_deliver

    monkeypatch.setenv("SEND_PAUSED", value)
    with respx.mock(assert_all_mocked=True) as router:
        result = run_deliver("send")
    assert result == {"outcome": "paused", "issue_id": ISSUE_ID}
    assert _report() == {"outcome": "paused", "issue_id": ISSUE_ID}
    assert gh_output.read_text(encoding="utf-8") == "outcome=paused\n"
    assert fake_smtp.instances == []
    assert router.calls.call_count == 0


@pytest.mark.parametrize("value", ["false", "", "yes", "1"])
def test_other_pause_values_send(value, current_issue, gh_output, creds, fake_smtp, monkeypatch):
    from newsletter.delivery.deliver import run_deliver

    monkeypatch.setenv("SEND_PAUSED", value)
    result = run_deliver("send")
    assert result == {
        "recipients": 2,
        "unsubscribed": 0,
        "skipped_ledger": 0,
        "sent": 2,
        "skipped_rows": 0,
    }
    assert gh_output.read_text(encoding="utf-8") == "outcome=sent\n"


def test_test_mode_never_pauses(current_issue, gh_output, creds, fake_smtp, monkeypatch):
    from newsletter.delivery.deliver import run_deliver

    monkeypatch.setenv("SEND_PAUSED", "true")
    result = run_deliver("test")
    assert result == {"recipients": 1, "sent": 1}
    assert len(fake_smtp.instances[0].sent) == 1
    assert gh_output.read_text(encoding="utf-8") == "outcome=tested\n"


# ----------------------------------------------------------- outcome report


def test_send_reports_counts_and_outcome(current_issue, gh_output, creds, fake_smtp):
    from newsletter.delivery.deliver import run_deliver

    result = run_deliver("send")
    assert result == {
        "recipients": 2,
        "unsubscribed": 0,
        "skipped_ledger": 0,
        "sent": 2,
        "skipped_rows": 0,
    }
    report = _report()
    assert report == {**result, "outcome": "sent", "issue_id": ISSUE_ID}
    raw = (store.out_root() / "report.json").read_text(encoding="utf-8")
    assert "@" not in raw and "가" not in raw  # counts and ids only (DLVR-06)
    assert gh_output.read_text(encoding="utf-8") == "outcome=sent\n"


def test_test_send_reports_tested(current_issue, gh_output, creds, fake_smtp):
    from newsletter.delivery.deliver import run_deliver

    result = run_deliver("test")
    assert _report() == {**result, "outcome": "tested", "issue_id": ISSUE_ID}
    assert "@" not in (store.out_root() / "report.json").read_text(encoding="utf-8")


def test_no_github_output_still_writes_report(current_issue, creds, fake_smtp):
    from newsletter.delivery.deliver import run_deliver

    run_deliver("send")
    assert _report()["outcome"] == "sent"


# ---------------------------------------------------------- send day (D-03)


def test_send_day_is_the_monday_after_the_week():
    assert week.send_day("2026-W44") == date(2026, 11, 2)
    assert week.send_day("2026-W45") == date(2026, 11, 9)
    _, sun = week.parse_week("2026-W53")
    assert week.send_day("2026-W53") == date(2027, 1, 4)
    assert (week.send_day("2026-W53") - sun).days == 1


@pytest.mark.parametrize(
    ("now", "ok"),
    [
        (datetime(2026, 11, 2, 0, 0, 0, tzinfo=KST), True),
        (datetime(2026, 11, 2, 23, 59, 59, tzinfo=KST), True),
        (datetime(2026, 11, 1, 23, 59, 59, tzinfo=KST), False),
        (datetime(2026, 11, 3, 0, 0, 0, tzinfo=KST), False),
        (datetime(2026, 11, 1, 15, 0, 0, tzinfo=UTC), True),  # 11-02 00:00 KST
        (datetime(2026, 11, 1, 14, 59, 59, tzinfo=UTC), False),
    ],
)
def test_is_sendable_uses_the_kst_day(now, ok):
    assert week.is_sendable("2026-W44", now) is ok


def test_is_sendable_rejects_naive_datetime():
    with pytest.raises(ValueError):
        week.is_sendable("2026-W44", datetime(2026, 11, 2, 9, 0))


# ------------------------------------------------------- stale guard (D-03)

LATE = datetime(2026, 11, 4, 9, 0, tzinfo=KST)


@pytest.fixture
def late(monkeypatch):
    from newsletter.delivery import deliver

    monkeypatch.setattr(deliver, "_now", lambda: LATE)


@pytest.mark.real_clock
def test_stale_send_refused_before_any_network(
    current_issue, gh_output, no_credentials, late, fake_smtp
):
    from newsletter.delivery.deliver import run_deliver
    from newsletter.errors import StaleIssueError

    with respx.mock(assert_all_mocked=True) as router, pytest.raises(StaleIssueError) as e:
        run_deliver("send")
    assert e.value.stage == "deliver"
    assert "@" not in str(e.value)
    assert fake_smtp.instances == []
    assert router.calls.call_count == 0
    assert gh_output.read_text(encoding="utf-8") == ""


@pytest.mark.real_clock
def test_allow_stale_passes_the_guard(current_issue, gh_output, creds, late, fake_smtp):
    from newsletter.delivery.deliver import run_deliver

    result = run_deliver("send", allow_stale=True)
    assert result["sent"] == 2
    assert gh_output.read_text(encoding="utf-8") == "outcome=sent\n"


@pytest.mark.real_clock
def test_pause_wins_over_stale(current_issue, gh_output, no_credentials, late, monkeypatch):
    from newsletter.delivery.deliver import run_deliver

    monkeypatch.setenv("SEND_PAUSED", "true")
    assert run_deliver("send") == {"outcome": "paused", "issue_id": ISSUE_ID}


@pytest.mark.real_clock
def test_stale_checked_before_secrets(current_issue, no_credentials, late):
    """Missing credentials would raise DeliveryError; the stale guard must come first."""
    from newsletter.delivery.deliver import run_deliver
    from newsletter.errors import StaleIssueError

    with pytest.raises(StaleIssueError):
        run_deliver("send")


@pytest.mark.real_clock
def test_test_mode_is_never_stale_checked(current_issue, gh_output, creds, late, fake_smtp):
    from newsletter.delivery.deliver import run_deliver

    assert run_deliver("test") == {"recipients": 1, "sent": 1}


def test_default_clock_is_w44_send_day(current_issue, gh_output, creds, fake_smtp):
    """The autouse clock keeps the W44 fixture sendable for every send test."""
    from newsletter.delivery import deliver

    assert week.is_sendable(ISSUE_ID, deliver._now())
    assert deliver.run_deliver("send")["sent"] == 2


@pytest.mark.real_clock
def test_cli_stale_send_fails_with_status(current_issue, no_credentials, late):
    from newsletter.__main__ import main

    assert main(["deliver", "--mode", "send"]) == 1
    status = json.loads((store.out_root() / "status.json").read_text(encoding="utf-8"))
    assert status == {"stage": "deliver", "error_class": "StaleIssueError"}


@pytest.mark.real_clock
def test_cli_allow_stale_flag_sends(current_issue, creds, late, fake_smtp):
    from newsletter.__main__ import main

    assert main(["deliver", "--mode", "send", "--allow-stale"]) == 0
    assert len(fake_smtp.instances[0].sent) == 2
