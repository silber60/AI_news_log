"""Send guards in run_deliver (05-01): pause switch, outcome report and the order of checks.

Every guard decides before any secret read, list fetch or SMTP connection (research Pattern 2).
"""

import json
import shutil
from pathlib import Path

import pytest
import respx

from newsletter import store

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
    assert result == {"recipients": 2, "unsubscribed": 0, "sent": 2, "skipped_rows": 0}
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
    assert result == {"recipients": 2, "unsubscribed": 0, "sent": 2, "skipped_rows": 0}
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
