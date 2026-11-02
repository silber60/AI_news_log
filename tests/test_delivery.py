"""Send mode: SUBSCRIBERS_CSV secret -> personalized render -> one message per recipient."""

import shutil
from pathlib import Path

import pytest

from newsletter import store

FIXTURES = Path(__file__).parent / "fixtures"
EXAMPLE_CSV = (Path(__file__).parent.parent / "subscribers.example.csv").read_text(encoding="utf-8")
ISSUE_ID = "2026-W44"


@pytest.fixture
def current_issue(archive_tmp):
    week = store.week_dir(ISSUE_ID)
    week.mkdir(parents=True)
    shutil.copy(FIXTURES / "issue_w44.json", week / "issue.json")
    store.write_current(ISSUE_ID)
    return week


@pytest.fixture
def send_env(monkeypatch):
    from newsletter.delivery import deliver

    monkeypatch.setattr(deliver, "SEND_PAUSE_SECONDS", 0)
    monkeypatch.setenv("SMTP_USER", "owner@example.com")
    monkeypatch.setenv("SMTP_PASSWORD", "abcd efgh")
    monkeypatch.setenv("SUBSCRIBERS_CSV", "﻿" + EXAMPLE_CSV)


def test_send_mode_greets_subscriber_by_name(current_issue, send_env, fake_smtp):
    from newsletter.__main__ import main

    assert main(["deliver", "--mode", "send"]) == 0

    assert len(fake_smtp.instances) == 1
    smtp = fake_smtp.instances[0]
    assert smtp.login_calls == [("owner@example.com", "abcdefgh")]
    assert len(smtp.sent) == 1
    msg = smtp.sent[0]
    assert msg.get_content_type() == "multipart/alternative"
    assert msg["To"] == "subscriber@example.com"
    assert "[TEST]" not in str(msg["Subject"])
    assert "AI 주간 모델 브리프" in str(msg["Subject"])
    assert "홍길동님" in msg.get_body(preferencelist=("html",)).get_content()
    assert "홍길동님" in msg.get_body(preferencelist=("plain",)).get_content()
    for header, value in msg.items():
        assert "홍길동" not in str(value), header


def test_send_mode_one_message_per_recipient(current_issue, send_env, fake_smtp, monkeypatch):
    from newsletter.delivery.deliver import run_deliver

    csv_text = "email,name\na@example.com,가\nnot-an-email,나\nb@example.com,\n"
    monkeypatch.setenv("SUBSCRIBERS_CSV", csv_text)

    result = run_deliver("send")

    assert result == {"recipients": 2, "sent": 2, "skipped_rows": 1}
    sent = fake_smtp.instances[0].sent
    assert [m["To"] for m in sent] == ["a@example.com", "b@example.com"]
    assert "가님" in sent[0].get_body(preferencelist=("plain",)).get_content()
    assert "구독자님" in sent[1].get_body(preferencelist=("plain",)).get_content()
