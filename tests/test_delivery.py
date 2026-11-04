"""Send mode: SUBSCRIBERS_CSV secret -> personalized render -> one message per recipient."""

import re
import shutil
from pathlib import Path

import pytest
import respx

from newsletter import store
from newsletter.schema import Issue
from newsletter.stages.render import build_subject

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
    issue = Issue.model_validate_json((current_issue / "issue.json").read_text(encoding="utf-8"))
    assert str(msg["Subject"]) == build_subject(issue, "send")
    assert "[TEST]" not in str(msg["Subject"])
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


# ------------------------------------------------- List-Unsubscribe (04-05, D-14)

LONG_ENDPOINT = "https://script.google.com/macros/s/AKfycb" + "x" * 72 + "/exec"
TOKEN_SECRET = "test-token-secret"
OWNER = "owner@example.com"


def _raw_header_lines(msg, name: str) -> list[str]:
    """Header lines as they go over the wire. A folded header shows up as a
    continuation line, so it is returned joined with its continuations (Pitfall 3)."""
    head = re.split(rb"\r?\n\r?\n", msg.as_bytes(), maxsplit=1)[0]
    lines = head.decode("ascii").splitlines()
    found = []
    for i, line in enumerate(lines):
        if line.lower().startswith(name.lower() + ":"):
            j = i + 1
            while j < len(lines) and lines[j][:1] in (" ", "\t"):
                j += 1
            found.append("\n".join(lines[i:j]))
    return found


def _cte(msg, subtype: str) -> str:
    return msg.get_body(preferencelist=(subtype,))["Content-Transfer-Encoding"]


@pytest.fixture
def test_env(monkeypatch):
    monkeypatch.setenv("SMTP_USER", OWNER)
    monkeypatch.setenv("SMTP_PASSWORD", "abcd efgh")
    monkeypatch.setenv("TEST_RECIPIENT", OWNER)


@pytest.fixture
def endpoint(monkeypatch):
    from newsletter.delivery import unsubscribe

    monkeypatch.setattr(unsubscribe, "UNSUBSCRIBE_ENDPOINT", LONG_ENDPOINT)
    return LONG_ENDPOINT


def test_header_mailto_only_without_endpoint(current_issue, test_env, fake_smtp):
    from newsletter.delivery import unsubscribe
    from newsletter.delivery.deliver import run_deliver

    assert unsubscribe.UNSUBSCRIBE_ENDPOINT is None
    with respx.mock(assert_all_mocked=True) as router:
        run_deliver("test")
        assert router.calls.call_count == 0
    msg = fake_smtp.instances[0].sent[0]
    assert _raw_header_lines(msg, "List-Unsubscribe") == [
        f"List-Unsubscribe: <mailto:{OWNER}?subject=unsubscribe>"
    ]
    assert _raw_header_lines(msg, "List-Unsubscribe-Post") == []
    for subtype in ("html", "plain"):
        body = msg.get_body(preferencelist=(subtype,)).get_content()
        assert "구독 해지" not in body and "unsubscribe/?t=" not in body
        assert "수신거부" in body


def test_test_send_gets_owner_token_and_unfolded_headers(
    current_issue, test_env, endpoint, fake_smtp, monkeypatch
):
    from newsletter.delivery.deliver import run_deliver
    from newsletter.delivery.send import build_message
    from newsletter.delivery.unsubscribe import token
    from newsletter.stages.render import SITE_URL

    monkeypatch.setenv("UNSUBSCRIBE_TOKEN_SECRET", TOKEN_SECRET)
    t = token(OWNER, TOKEN_SECRET)
    with respx.mock(assert_all_mocked=True) as router:
        run_deliver("test")  # test mode never fetches the list
        assert router.calls.call_count == 0
    msg = fake_smtp.instances[0].sent[0]
    lines = _raw_header_lines(msg, "List-Unsubscribe")
    assert lines == [f"List-Unsubscribe: <mailto:{OWNER}?subject=unsubscribe>, <{endpoint}?t={t}>"]
    assert "\n" not in lines[0] and "=?utf-8?" not in lines[0].lower()
    assert b"=?utf-8?q?=3C" not in msg.as_bytes()
    assert _raw_header_lines(msg, "List-Unsubscribe-Post") == [
        "List-Unsubscribe-Post: List-Unsubscribe=One-Click"
    ]
    link = f"{SITE_URL}unsubscribe/?t={t}"
    html = msg.get_body(preferencelist=("html",)).get_content()
    text = msg.get_body(preferencelist=("plain",)).get_content()
    assert f'href="{link}"' in html and "구독 해지" in html
    assert f"구독 해지: {link}" in text
    # The policy clone runs after set_content, so body encodings match a message
    # built from the same parts without the header.
    plain = build_message(subject="s", sender_addr=OWNER, to=OWNER, text=text, html=html)
    assert _cte(msg, "html") == _cte(plain, "html")
    assert _cte(msg, "plain") == _cte(plain, "plain")
    assert max(map(len, msg.as_bytes().splitlines())) <= 998


def test_endpoint_without_token_secret_fails_before_smtp(
    current_issue, test_env, endpoint, fake_smtp, monkeypatch
):
    from newsletter.delivery.deliver import run_deliver
    from newsletter.errors import DeliveryError

    monkeypatch.delenv("UNSUBSCRIBE_TOKEN_SECRET", raising=False)
    with pytest.raises(
        DeliveryError, match="missing environment variable UNSUBSCRIBE_TOKEN_SECRET"
    ):
        run_deliver("test")
    assert all(not s.login_calls for s in fake_smtp.instances)


def test_build_message_strips_crlf_from_unsubscribe_header():
    from newsletter.delivery.send import build_message

    msg = build_message(
        subject="s",
        sender_addr=OWNER,
        to="a@example.com",
        text="t",
        html="<p>h</p>",
        list_unsubscribe="<mailto:x@example.com>\r\nBcc: evil@example.com",
        one_click=False,
    )
    raw = msg.as_bytes()
    assert b"\nBcc:" not in raw
    assert _raw_header_lines(msg, "List-Unsubscribe") == [
        "List-Unsubscribe: <mailto:x@example.com>Bcc: evil@example.com"
    ]
    assert _raw_header_lines(msg, "List-Unsubscribe-Post") == []


def test_build_message_without_unsubscribe_has_no_header():
    from newsletter.delivery.send import build_message

    msg = build_message(subject="s", sender_addr=OWNER, to="a@example.com", text="t", html="h")
    assert _raw_header_lines(msg, "List-Unsubscribe") == []
