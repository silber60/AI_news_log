"""Send mode: SUBSCRIBERS_CSV secret -> personalized render -> one message per recipient."""

import re
import shutil
from pathlib import Path
from urllib.parse import parse_qs

import httpx
import pytest
import respx
from conftest import mock_apps_script

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
    # 05-03: send mode keys the send ledger with this secret, endpoint or not.
    monkeypatch.setenv("UNSUBSCRIBE_TOKEN_SECRET", TOKEN_SECRET)


def test_send_mode_greets_subscriber_by_name(current_issue, send_env, fake_smtp):
    from newsletter.__main__ import main

    assert main(["deliver", "--mode", "send"]) == 0

    assert len(fake_smtp.instances) == 1
    smtp = fake_smtp.instances[0]
    assert smtp.login_calls == [("resend", "abcdefgh")]  # Phase 4.2: Resend SMTP login
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

    assert result == {
        "recipients": 2,
        "unsubscribed": 0,
        "skipped_ledger": 0,
        "sent": 2,
        "skipped_rows": 1,
    }
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


# ------------------------------------------- send-time unsubscribe filter (D-13)

LIST_KEY = "test-list-key-value"
MEMBERS_KEY = "test-members-key-value"
A, B = "a@example.com", "b@example.com"
TWO_CSV = f"email,name\n{A},가\n{B},나\n"
TWO_ROWS = [{"email": A, "name": "가"}, {"email": B, "name": "나"}]


@pytest.fixture
def filter_env(send_env, endpoint, monkeypatch):
    """Endpoint set: the live list replaces SUBSCRIBERS_CSV (D-08)."""
    monkeypatch.delenv("SUBSCRIBERS_CSV")
    monkeypatch.setenv("SUBSCRIBER_LIST_KEY", MEMBERS_KEY)
    monkeypatch.setenv("UNSUBSCRIBE_TOKEN_SECRET", TOKEN_SECRET)
    monkeypatch.setenv("UNSUBSCRIBE_LIST_KEY", LIST_KEY)


def _secret_free(text: str) -> None:
    from newsletter.delivery.unsubscribe import token

    assert "@" not in text
    for addr in (A, B, OWNER):
        assert token(addr, TOKEN_SECRET) not in text
    assert LIST_KEY not in text and TOKEN_SECRET not in text
    assert MEMBERS_KEY not in text
    assert "가" not in text and "나" not in text


def test_send_skips_unsubscribed_reader(current_issue, filter_env, fake_smtp, caplog, capsys):
    from newsletter.delivery.deliver import run_deliver
    from newsletter.delivery.unsubscribe import token

    caplog.set_level("INFO")
    with respx.mock(assert_all_mocked=True) as router:
        route = mock_apps_script(router, LONG_ENDPOINT, TWO_ROWS, ids=[token(A, TOKEN_SECRET)])
        result = run_deliver("send")
    assert route.call_count == 2
    bodies = [parse_qs(c.request.content.decode()) for c in route.calls]
    assert bodies == [
        {"action": ["members"], "key": [MEMBERS_KEY]},
        {"action": ["list"], "key": [LIST_KEY]},
    ]
    assert result == {
        "recipients": 2,
        "unsubscribed": 1,
        "skipped_ledger": 0,
        "sent": 1,
        "skipped_rows": 0,
    }
    sent = fake_smtp.instances[0].sent
    assert [m["To"] for m in sent] == [B]
    t = token(B, TOKEN_SECRET)
    assert f"<{LONG_ENDPOINT}?t={t}>" in _raw_header_lines(sent[0], "List-Unsubscribe")[0]
    assert _raw_header_lines(sent[0], "List-Unsubscribe-Post")
    assert f"unsubscribe/?t={t}" in sent[0].get_body(preferencelist=("html",)).get_content()
    assert (
        "mode=send recipients=2 unsubscribed=1 skipped_ledger=0 sent=1 skipped_rows=0"
        in caplog.text
    )
    captured = capsys.readouterr()
    _secret_free(caplog.text + captured.out + captured.err)


def test_send_with_everyone_unsubscribed_sends_nothing(
    current_issue, filter_env, fake_smtp, caplog
):
    from newsletter.delivery.deliver import run_deliver
    from newsletter.delivery.unsubscribe import token

    caplog.set_level("INFO")
    ids = [token(A, TOKEN_SECRET), token(B, TOKEN_SECRET)]
    with respx.mock(assert_all_mocked=True) as router:
        mock_apps_script(router, LONG_ENDPOINT, TWO_ROWS, ids=ids)
        result = run_deliver("send")
    assert result == {
        "recipients": 2,
        "unsubscribed": 2,
        "skipped_ledger": 0,
        "sent": 0,
        "skipped_rows": 0,
    }
    assert fake_smtp.instances == []
    assert (
        "mode=send recipients=2 unsubscribed=2 skipped_ledger=0 sent=0 skipped_rows=0"
        in caplog.text
    )
    _secret_free(caplog.text)


BAD_REPLIES = [
    httpx.Response(500),
    httpx.Response(200, text="not json"),
    httpx.ConnectError("boom"),
]
BAD_IDS = ["status-500", "bad-json", "connect-error"]


@pytest.mark.parametrize("reply", BAD_REPLIES, ids=BAD_IDS)
def test_send_fails_closed_when_list_unreadable(current_issue, filter_env, fake_smtp, reply):
    from newsletter.delivery.deliver import run_deliver
    from newsletter.errors import DeliveryError

    with respx.mock(assert_all_mocked=True) as router:
        mock_apps_script(router, LONG_ENDPOINT, TWO_ROWS, list_reply=reply)
        with pytest.raises(DeliveryError) as exc:
            run_deliver("send")
    _secret_free(str(exc.value))
    assert fake_smtp.instances == []


@pytest.mark.parametrize(
    "reply",
    [*BAD_REPLIES, httpx.Response(200, json={"error": "forbidden"})],
    ids=[*BAD_IDS, "forbidden"],
)
def test_send_fails_closed_when_members_unreadable(current_issue, filter_env, fake_smtp, reply):
    from newsletter.delivery.deliver import run_deliver
    from newsletter.errors import DeliveryError

    with respx.mock(assert_all_mocked=True) as router:
        route = mock_apps_script(router, LONG_ENDPOINT, members_reply=reply)
        with pytest.raises(DeliveryError) as exc:
            run_deliver("send")
    assert route.call_count == 1  # the unsubscribe list is never read
    _secret_free(str(exc.value))
    assert fake_smtp.instances == []


def test_send_fails_closed_on_empty_live_list(current_issue, filter_env, fake_smtp):
    from newsletter.delivery.deliver import run_deliver
    from newsletter.errors import NoSubscribersError

    with respx.mock(assert_all_mocked=True) as router:
        mock_apps_script(router, LONG_ENDPOINT, [{"email": "not-an-email"}])
        with pytest.raises(NoSubscribersError):
            run_deliver("send")
    assert fake_smtp.instances == []


def test_send_dedupes_live_list(current_issue, filter_env, fake_smtp, caplog):
    from newsletter.delivery.deliver import run_deliver

    caplog.set_level("INFO")
    rows = [*TWO_ROWS, {"email": " A@EXAMPLE.com ", "name": "다"}, {"email": "bad"}, None]
    with respx.mock(assert_all_mocked=True) as router:
        mock_apps_script(router, LONG_ENDPOINT, rows)
        result = run_deliver("send")
    assert result == {
        "recipients": 2,
        "unsubscribed": 0,
        "skipped_ledger": 0,
        "sent": 2,
        "skipped_rows": 3,
    }
    assert [m["To"] for m in fake_smtp.instances[0].sent] == [A, B]
    assert (
        "mode=send recipients=2 unsubscribed=0 skipped_ledger=0 sent=2 skipped_rows=3"
        in caplog.text
    )
    _secret_free(caplog.text)


def test_send_ignores_csv_when_endpoint_set(current_issue, filter_env, fake_smtp, monkeypatch):
    from newsletter.delivery.deliver import run_deliver

    monkeypatch.setenv("SUBSCRIBERS_CSV", "email,name\nc@example.com,다\n")
    with respx.mock(assert_all_mocked=True) as router:
        mock_apps_script(router, LONG_ENDPOINT, TWO_ROWS)
        run_deliver("send")
    assert [m["To"] for m in fake_smtp.instances[0].sent] == [A, B]


@pytest.mark.parametrize(
    "missing", ["SUBSCRIBER_LIST_KEY", "UNSUBSCRIBE_LIST_KEY", "UNSUBSCRIBE_TOKEN_SECRET"]
)
def test_send_fails_closed_without_unsubscribe_secret(
    current_issue, filter_env, fake_smtp, monkeypatch, missing
):
    from newsletter.delivery.deliver import run_deliver
    from newsletter.errors import DeliveryError

    monkeypatch.delenv(missing)
    with respx.mock(assert_all_mocked=True) as router:
        with pytest.raises(DeliveryError, match=f"missing environment variable {missing}"):
            run_deliver("send")
        assert router.calls.call_count == 0
    assert fake_smtp.instances == []


def test_list_failure_goes_through_cli_failure_path(
    current_issue, filter_env, fake_smtp, capsys, caplog
):
    from newsletter.__main__ import main

    with respx.mock(assert_all_mocked=True) as router:
        mock_apps_script(router, LONG_ENDPOINT, TWO_ROWS, list_reply=httpx.Response(500))
        assert main(["deliver", "--mode", "send"]) != 0
    status = store.read_json(store.out_root() / "status.json")
    assert status == {"stage": "deliver", "error_class": "DeliveryError"}
    assert fake_smtp.instances == []
    captured = capsys.readouterr()
    _secret_free(captured.out + captured.err + caplog.text)


def test_send_without_endpoint_fetches_nothing_and_mails_everyone(
    current_issue, send_env, fake_smtp, monkeypatch
):
    from newsletter.delivery import unsubscribe
    from newsletter.delivery.deliver import run_deliver

    assert unsubscribe.UNSUBSCRIBE_ENDPOINT is None
    monkeypatch.setenv("SUBSCRIBERS_CSV", TWO_CSV)
    # 05-03: the ledger key needs the secret; without an endpoint it still makes no link.
    monkeypatch.setenv("UNSUBSCRIBE_TOKEN_SECRET", TOKEN_SECRET)
    monkeypatch.delenv("UNSUBSCRIBE_LIST_KEY", raising=False)
    with respx.mock(assert_all_mocked=True) as router:
        result = run_deliver("send")
        assert router.calls.call_count == 0
    assert result == {
        "recipients": 2,
        "unsubscribed": 0,
        "skipped_ledger": 0,
        "sent": 2,
        "skipped_rows": 0,
    }
    sent = fake_smtp.instances[0].sent
    assert [m["To"] for m in sent] == [A, B]
    for m in sent:
        assert _raw_header_lines(m, "List-Unsubscribe") == [
            f"List-Unsubscribe: <mailto:{OWNER}?subject=unsubscribe>"
        ]
        assert "구독 해지" not in m.get_body(preferencelist=("html",)).get_content()
