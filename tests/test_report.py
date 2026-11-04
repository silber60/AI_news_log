"""Weekly run report to the owner (AUTO-04, D-06, research Pattern 7)."""

import re

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


# ------------------------------------------------- the rest of the decision table (D-06)

STALE = {"stage": "deliver", "error_class": "StaleIssueError"}
FETCH_FAIL = {"stage": "fetch", "error_class": "FetchError"}
RUN_URL = "https://github.com/silber60/AI_news_log/actions/runs/12345"


def test_send_paused(archive_tmp, fake_smtp, report_env):
    from newsletter.__main__ import main

    _write_report({"outcome": "paused", "issue_id": ISSUE_ID})

    assert main(["report", "--mode", "send"]) == 0

    msg = _only_message(fake_smtp)
    assert str(msg["Subject"]) == f"[일시정지] 모닥로그 AI 리포트 {ISSUE_ID}"
    assert msg.get_content().splitlines()[0] == (
        "이번 주 발송은 멈춰 두었어요. 아무에게도 보내지 않았어요."
    )


def test_send_refused_as_stale(archive_tmp, fake_smtp, report_env):
    from newsletter.__main__ import main

    store.write_current(ISSUE_ID)
    _write_status(STALE)

    assert main(["report", "--mode", "send"]) == 0

    msg = _only_message(fake_smtp)
    assert str(msg["Subject"]) == f"[발송 거부] 모닥로그 AI 리포트 {ISSUE_ID}"
    lines = msg.get_content().splitlines()
    assert lines[0] == f"발송 기한(월요일 23:59)이 지나서 {ISSUE_ID} 호를 보내지 않았어요."
    assert lines[1] == "다시 보내려면 Actions에서 mode=send로 직접 실행해 주세요."
    assert "stage: deliver" in lines
    assert "error_class: StaleIssueError" in lines


def test_send_other_failure(archive_tmp, fake_smtp, report_env):
    from newsletter.__main__ import main

    store.write_current(ISSUE_ID)
    _write_status(FETCH_FAIL)

    assert main(["report", "--mode", "send"]) == 0

    msg = _only_message(fake_smtp)
    assert str(msg["Subject"]) == f"[실패] 모닥로그 AI 리포트 {ISSUE_ID}"
    lines = msg.get_content().splitlines()
    assert lines[0] == f"모닥로그 AI 리포트 {ISSUE_ID} 실행이 실패했어요."
    for line in ("mode: send", "stage: fetch", "error_class: FetchError", f"run: {RUN_URL}"):
        assert line in lines


def test_status_wins_over_report(archive_tmp, fake_smtp, report_env):
    from newsletter.__main__ import main

    _write_report(SENT_REPORT)
    _write_status({"stage": "deliver", "error_class": "DeliveryError"})

    assert main(["report", "--mode", "send"]) == 0
    assert str(_only_message(fake_smtp)["Subject"]).startswith("[실패] ")


@pytest.mark.parametrize("mode", ["test", "send"])
def test_neither_file_is_an_unknown_failure(archive_tmp, fake_smtp, report_env, mode):
    from newsletter.__main__ import main

    assert main(["report", "--mode", mode]) == 0

    msg = _only_message(fake_smtp)
    assert str(msg["Subject"]) == "[실패] 모닥로그 AI 리포트 unknown"
    assert "stage: unknown" in msg.get_content().splitlines()


def test_successful_test_run_mails_nothing(archive_tmp, fake_smtp, monkeypatch):
    from newsletter.__main__ import main
    from newsletter.delivery.notify import build_report

    # no credentials at all: a tested run must not touch them
    for name in ("SMTP_USER", "SMTP_PASSWORD", "TEST_RECIPIENT"):
        monkeypatch.delenv(name, raising=False)
    tested = {"outcome": "tested", "issue_id": ISSUE_ID, "recipients": 1, "sent": 1}
    _write_report(tested)

    assert build_report("test", ISSUE_ID, {}, tested) is None
    assert main(["report", "--mode", "test"]) == 0
    assert fake_smtp.instances == []


def test_test_run_failure_mails_failure(archive_tmp, fake_smtp, report_env):
    from newsletter.__main__ import main

    store.write_current(ISSUE_ID)
    _write_status(FETCH_FAIL)

    assert main(["report", "--mode", "test"]) == 0
    msg = _only_message(fake_smtp)
    assert str(msg["Subject"]) == f"[실패] 모닥로그 AI 리포트 {ISSUE_ID}"
    assert "mode: test" in msg.get_content().splitlines()


def test_notify_failure_alias_matches_report(archive_tmp, fake_smtp, report_env):
    from newsletter.__main__ import main

    store.write_current(ISSUE_ID)
    _write_status(STALE)
    assert main(["report", "--mode", "send"]) == 0
    assert main(["notify-failure", "--mode", "send"]) == 0

    a, b = (inst.sent[0] for inst in fake_smtp.instances)
    assert str(a["Subject"]) == str(b["Subject"])
    assert a.get_content() == b.get_content()


# ------------------------------------------------------------ copy and leaks (T-05-16)

HANGUL = re.compile(r"[가-힣]")
HEX64 = re.compile(r"[0-9a-fA-F]{64}")
NAME = "홍길동"
LEAK_EMAIL = "subscriber@example.com"


def _every_body() -> list[str]:
    from newsletter.delivery.notify import build_report

    tested = {"outcome": "tested", "issue_id": ISSUE_ID}
    cases = [
        ("send", {}, SENT_REPORT),
        ("send", {}, {"outcome": "paused", "issue_id": ISSUE_ID}),
        ("send", STALE, {}),
        ("send", FETCH_FAIL, {}),
        ("send", FETCH_FAIL, SENT_REPORT),
        ("send", {}, {}),
        ("test", {}, {}),
        ("test", FETCH_FAIL, tested),
    ]
    bodies = []
    for mode, status, report in cases:
        built = build_report(mode, ISSUE_ID, status, report)
        assert built is not None
        bodies.append(built[1])
    return bodies


def test_every_korean_body_line_passes_lint(report_env):
    from newsletter.stages import humanize

    checked = 0
    for body in _every_body():
        for line in body.splitlines():
            if HANGUL.search(line):
                assert humanize.lint(line, kind="sentence") == [], line
                checked += 1
    assert checked >= 5


def test_no_old_formal_copy():
    from newsletter.delivery import notify

    text = notify.build_notice_text("send", ISSUE_ID, FETCH_FAIL)
    assert "실행이 실패했습니다" not in text
    assert "실행이 실패했어요." in text


def test_bodies_hold_no_personal_data(report_env, monkeypatch):
    from newsletter.__main__ import _EMAIL_RE
    from newsletter.delivery.notify import build_report

    monkeypatch.setenv("SUBSCRIBERS_CSV", f"email,name\n{LEAK_EMAIL},{NAME}\n")
    # unknown keys in report.json never reach the body
    tainted = {**SENT_REPORT, "names": [NAME], "emails": [LEAK_EMAIL], "key": "a" * 64}
    bodies = [*_every_body(), build_report("send", ISSUE_ID, {}, tainted)[1]]
    for body in bodies:
        assert not _EMAIL_RE.search(body)
        assert not HEX64.search(body)
        assert "?t=" not in body
        assert NAME not in body
