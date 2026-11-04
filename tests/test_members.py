"""Live subscriber list from Apps Script action=members (D-08). Fails closed."""

import logging
from urllib.parse import parse_qs

import httpx
import pytest
import respx
from conftest import APPS_ECHO, mock_apps_script

from newsletter.delivery.members import fetch_subscribers
from newsletter.delivery.subscribers import Subscriber
from newsletter.errors import DeliveryError, NoSubscribersError

ENDPOINT = "https://script.google.com/macros/s/AKfycbTEST/exec"
KEY = "subscriber-list-key-do-not-use-123"


def _client() -> httpx.Client:
    return httpx.Client(timeout=5)


@respx.mock
def test_fetch_follows_302_and_returns_rows_in_order():
    rows = [
        {"email": "a@example.com", "name": " 가나 "},
        {"email": "b@example.com", "name": ""},
        {"email": "c@example.com"},
    ]
    post = mock_apps_script(respx.mock, ENDPOINT, rows)
    with _client() as c:
        subs, skipped = fetch_subscribers(ENDPOINT, KEY, client=c)
    assert subs == [
        Subscriber("a@example.com", "가나"),
        Subscriber("b@example.com", ""),
        Subscriber("c@example.com", ""),
    ]
    assert skipped == 0
    req = post.calls.last.request
    assert KEY not in str(req.url) and "members" not in str(req.url)
    assert parse_qs(req.content.decode()) == {"action": ["members"], "key": [KEY]}


@respx.mock
def test_fetch_without_client_uses_its_own():
    respx.post(ENDPOINT).mock(
        return_value=httpx.Response(
            200, json={"version": 1, "subscribers": [{"email": "a@example.com", "name": "x"}]}
        )
    )
    assert fetch_subscribers(ENDPOINT, KEY) == ([Subscriber("a@example.com", "x")], 0)


@respx.mock
def test_dedupe_and_skip_invalid_rows():
    rows = [
        {"email": "A@example.com", "name": "첫"},
        {"email": " a@example.com ", "name": "둘"},
        {"email": "not-an-email", "name": "x"},
        "b@example.com",
        {"email": None},
        {"email": "b@example.com", "name": 7},
    ]
    mock_apps_script(respx.mock, ENDPOINT, rows)
    with _client() as c:
        subs, skipped = fetch_subscribers(ENDPOINT, KEY, client=c)
    assert subs == [Subscriber("A@example.com", "첫"), Subscriber("b@example.com", "")]
    assert skipped == 4


@respx.mock
def test_zero_valid_rows_raise_no_subscribers():
    mock_apps_script(respx.mock, ENDPOINT, [{"email": "nope"}, 1])
    with _client() as c, pytest.raises(NoSubscribersError) as exc:
        fetch_subscribers(ENDPOINT, KEY, client=c)
    assert str(exc.value) == "no valid subscribers (skipped=2)"


@respx.mock
def test_empty_list_raises_no_subscribers():
    mock_apps_script(respx.mock, ENDPOINT, [])
    with _client() as c, pytest.raises(NoSubscribersError):
        fetch_subscribers(ENDPOINT, KEY, client=c)


def _assert_clean(err: Exception):
    text = str(err)
    assert KEY not in text
    assert "@" not in text
    assert "macros" not in text and "?" not in text


@pytest.mark.parametrize(
    "reply",
    [
        httpx.Response(500, text="boom"),
        httpx.Response(200, text="<html>not json</html>"),
        httpx.Response(200, json={"version": 2, "subscribers": []}),
        httpx.Response(200, json={"error": "forbidden"}),
        httpx.Response(200, json={"version": 1, "subscribers": "a@example.com"}),
        httpx.Response(200, json={"version": 1, "subscribers": None}),
        httpx.Response(200, json={"version": 1}),
        httpx.Response(200, json=[{"email": "a@example.com"}]),
        httpx.Response(404),
    ],
    ids=[
        "status-500",
        "not-json",
        "version-2",
        "forbidden",
        "not-a-list",
        "null",
        "missing",
        "top-level-list",
        "302-no-target",
    ],
)
@respx.mock
def test_fetch_fails_closed(reply):
    mock_apps_script(respx.mock, ENDPOINT, members_reply=reply)
    with _client() as c, pytest.raises(DeliveryError) as exc:
        fetch_subscribers(ENDPOINT, KEY, client=c)
    _assert_clean(exc.value)


@respx.mock
def test_fetch_fails_closed_on_forbidden_post_reply():
    respx.post(ENDPOINT).mock(return_value=httpx.Response(200, json={"error": "forbidden"}))
    with _client() as c, pytest.raises(DeliveryError, match="subscriber list unreadable"):
        fetch_subscribers(ENDPOINT, KEY, client=c)


@respx.mock
def test_fetch_fails_closed_on_connect_error():
    respx.post(ENDPOINT).mock(side_effect=httpx.ConnectError(f"cannot reach {ENDPOINT}?key={KEY}"))
    with _client() as c, pytest.raises(DeliveryError) as exc:
        fetch_subscribers(ENDPOINT, KEY, client=c)
    assert str(exc.value) == "subscriber list ConnectError"
    _assert_clean(exc.value)
    assert exc.value.__cause__ is None
    assert exc.value.__suppress_context__


@respx.mock
def test_fetch_fails_closed_on_redirect_target_error():
    mock_apps_script(
        respx.mock,
        ENDPOINT,
        members_reply=httpx.ReadTimeout(f"{APPS_ECHO}?user_content_key=members a@example.com"),
    )
    with _client() as c, pytest.raises(DeliveryError) as exc:
        fetch_subscribers(ENDPOINT, KEY, client=c)
    assert str(exc.value) == "subscriber list ReadTimeout"
    _assert_clean(exc.value)


def test_status_error_text_is_status_only():
    with respx.mock:
        respx.post(ENDPOINT).mock(return_value=httpx.Response(503))
        with _client() as c, pytest.raises(DeliveryError) as exc:
            fetch_subscribers(ENDPOINT, KEY, client=c)
    assert str(exc.value) == "subscriber list status=503"


@respx.mock
def test_fetch_logs_no_key_or_address(caplog):
    caplog.set_level(logging.DEBUG)
    mock_apps_script(
        respx.mock, ENDPOINT, [{"email": "a@example.com", "name": "홍길동"}, {"email": "bad"}]
    )
    with _client() as c:
        fetch_subscribers(ENDPOINT, KEY, client=c)
    assert KEY not in caplog.text
    assert "@" not in caplog.text
    assert "홍길동" not in caplog.text
