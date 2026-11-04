"""Weekly run report to the owner (AUTO-04, D-06, research Pattern 7)."""

import pytest

from newsletter import store
from newsletter.stages.render import SITE_URL

ISSUE_ID = "2026-W44"
OWNER = "owner@example.com"
SENT_REPORT = {
    "outcome": "sent",
    "issue_id": ISSUE_ID,
    "recipients": 3,
    "sent": 2,
    "skipped_ledger": 1,
    "unsubscribed": 0,
    "skipped_rows": 0,
}


@pytest.fixture
def report_env(monkeypatch):
    monkeypatch.setenv("SMTP_USER", OWNER)
    monkeypatch.setenv("SMTP_PASSWORD", "abcd efgh")
    monkeypatch.setenv("TEST_RECIPIENT", OWNER)
    monkeypatch.setenv("GITHUB_SERVER_URL", "https://github.com")
    monkeypatch.setenv("GITHUB_REPOSITORY", "silber60/AI_news_log")
    monkeypatch.setenv("GITHUB_RUN_ID", "12345")


def _write_report(data: dict) -> None:
    store.write_json(store.out_root() / "report.json", data)


def _write_status(data: dict) -> None:
    store.write_json(store.out_root() / "status.json", data)


def _only_message(fake_smtp):
    sent = [m for inst in fake_smtp.instances for m in inst.sent]
    assert len(sent) == 1
    msg = sent[0]
    assert msg["To"] == OWNER
    assert msg.get_content_type() == "text/plain"
    return msg


def test_send_sent_mails_counts_and_web_link(archive_tmp, fake_smtp, report_env):
    from newsletter.__main__ import main

    _write_report(SENT_REPORT)

    assert main(["report", "--mode", "send"]) == 0

    msg = _only_message(fake_smtp)
    assert str(msg["Subject"]) == f"[발송 완료] 모닥로그 AI 리포트 {ISSUE_ID}"
    body = msg.get_content()
    assert body.splitlines()[0] == f"모닥로그 AI 리포트 {ISSUE_ID} 호를 보냈어요."
    for line in (
        "recipients: 3",
        "sent: 2",
        "skipped_ledger: 1",
        "unsubscribed: 0",
        "skipped_rows: 0",
        f"web: {SITE_URL}issues/{ISSUE_ID}/",
    ):
        assert line in body.splitlines()


def test_sent_issue_id_falls_back_to_current(archive_tmp, fake_smtp, report_env):
    from newsletter.__main__ import main

    store.write_current(ISSUE_ID)
    _write_report({k: v for k, v in SENT_REPORT.items() if k != "issue_id"})

    assert main(["report", "--mode", "send"]) == 0
    assert ISSUE_ID in str(_only_message(fake_smtp)["Subject"])


def test_report_failure_keeps_status_json(archive_tmp, monkeypatch):
    from newsletter.__main__ import main

    monkeypatch.delenv("TEST_RECIPIENT", raising=False)
    monkeypatch.setenv("SMTP_USER", OWNER)
    monkeypatch.setenv("SMTP_PASSWORD", "abcd efgh")
    status = {"stage": "deliver", "error_class": "DeliveryError"}
    _write_status(status)

    assert main(["report", "--mode", "send"]) == 1
    assert store.read_json(store.out_root() / "status.json") == status
