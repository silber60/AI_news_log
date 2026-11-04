"""Unsubscribe token scheme and the fail-closed list fetch (D-10..D-13)."""

import logging
import re
from pathlib import Path
from urllib.parse import parse_qs

import httpx
import pytest
import respx

from newsletter.delivery import unsubscribe
from newsletter.delivery.unsubscribe import TOKEN_LEN, TOKEN_RE, fetch_unsubscribed, token
from newsletter.errors import DeliveryError
from newsletter.stages import humanize

ROOT = Path(__file__).resolve().parent.parent
CODE_GS = ROOT / "apps_script" / "Code.gs"
README = ROOT / "apps_script" / "README.md"

SECRET = "test-secret-do-not-use"
VECTOR = "f290b8e448576cf84f63ac2b465c3e65"
VECTOR_A = "82a671b5104273fe07992f40d81000c8"

ENDPOINT = "https://script.google.com/macros/s/AKfycbTEST/exec"
ECHO = "https://script.googleusercontent.com/macros/echo?user_content_key=abc"
KEY = "list-key-do-not-use-1234567890"
VALID = "0123456789abcdef0123456789abcdef"


def test_token_matches_research_vectors():
    assert TOKEN_LEN == 32
    assert token("Subscriber@Example.com ", SECRET) == VECTOR
    assert token("a@example.com", SECRET) == VECTOR_A
    assert TOKEN_RE.fullmatch(VECTOR)


def test_token_normalizes_case_and_whitespace():
    assert token("  SUBSCRIBER@example.COM\n", SECRET) == VECTOR


def test_token_re_rejects_bad_ids():
    assert TOKEN_RE.fullmatch(VECTOR.upper()) is None
    assert TOKEN_RE.fullmatch(VECTOR[:-1]) is None
    assert TOKEN_RE.fullmatch(VECTOR + "0") is None


@pytest.mark.live_endpoint
def test_endpoint_is_the_deployed_exec_url():
    """T-04.1-17: the constant is one Apps Script /exec URL (04.1-05)."""
    assert isinstance(unsubscribe.UNSUBSCRIBE_ENDPOINT, str)
    assert re.fullmatch(
        r"https://script\.google\.com/macros/s/[A-Za-z0-9_-]+/exec",
        unsubscribe.UNSUBSCRIBE_ENDPOINT,
    )


def _client() -> httpx.Client:
    return httpx.Client(timeout=5)


@respx.mock
def test_fetch_follows_302_and_keeps_only_hex_ids():
    post = respx.post(ENDPOINT).mock(return_value=httpx.Response(302, headers={"Location": ECHO}))
    respx.get(ECHO).mock(
        return_value=httpx.Response(200, json={"version": 1, "ids": [VALID, "NOTHEX", 123]})
    )
    with _client() as c:
        assert fetch_unsubscribed(ENDPOINT, KEY, client=c) == {VALID}
    req = post.calls.last.request
    assert KEY not in str(req.url)
    body = parse_qs(req.content.decode())
    assert body == {"action": ["list"], "key": [KEY]}


@respx.mock
def test_fetch_without_client_uses_its_own():
    respx.post(ENDPOINT).mock(return_value=httpx.Response(200, json={"version": 1, "ids": []}))
    assert fetch_unsubscribed(ENDPOINT, KEY) == set()


def _assert_clean(err: DeliveryError):
    text = str(err)
    assert KEY not in text
    assert "macros" not in text and "?" not in text
    assert VALID not in text


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(500, text="boom"),
        httpx.Response(200, text="<html>not json</html>"),
        httpx.Response(200, json={"version": 1}),
        httpx.Response(200, json={"error": "forbidden"}),
        httpx.Response(200, json=[VALID]),
        httpx.Response(200, json={"version": 1, "ids": None}),
    ],
)
@respx.mock
def test_fetch_fails_closed(response):
    respx.post(ENDPOINT).mock(return_value=response)
    with _client() as c, pytest.raises(DeliveryError) as exc:
        fetch_unsubscribed(ENDPOINT, KEY, client=c)
    _assert_clean(exc.value)


@respx.mock
def test_fetch_fails_closed_on_302_without_follow_target():
    respx.post(ENDPOINT).mock(return_value=httpx.Response(302, headers={"Location": ECHO}))
    respx.get(ECHO).mock(return_value=httpx.Response(404))
    with _client() as c, pytest.raises(DeliveryError) as exc:
        fetch_unsubscribed(ENDPOINT, KEY, client=c)
    _assert_clean(exc.value)


@respx.mock
def test_fetch_fails_closed_on_connect_error():
    respx.post(ENDPOINT).mock(side_effect=httpx.ConnectError(f"cannot reach {ENDPOINT}?key={KEY}"))
    with _client() as c, pytest.raises(DeliveryError) as exc:
        fetch_unsubscribed(ENDPOINT, KEY, client=c)
    _assert_clean(exc.value)
    assert exc.value.__cause__ is None
    assert exc.value.__suppress_context__


@respx.mock
def test_fetch_logs_no_key_id_or_address(caplog):
    caplog.set_level(logging.DEBUG)
    respx.post(ENDPOINT).mock(
        return_value=httpx.Response(200, json={"version": 1, "ids": [VALID, VECTOR]})
    )
    with _client() as c:
        fetch_unsubscribed(ENDPOINT, KEY, client=c)
    assert KEY not in caplog.text
    assert VALID not in caplog.text and VECTOR not in caplog.text
    assert "@" not in caplog.text


# ---- Apps Script side (static checks; the owner runs selfTest in Google) ----


def test_code_gs_carries_the_same_vector_and_scheme():
    src = CODE_GS.read_text(encoding="utf-8")
    assert src.count(VECTOR) == 1
    assert "'test-secret-do-not-use'" in src
    assert "computeHmacSha256Signature" in src
    assert "toLowerCase()" in src and "trim()" in src
    assert "& 0xff" in src
    assert f".slice(0, {TOKEN_LEN})" in src
    assert f"/^[0-9a-f]{{{TOKEN_LEN}}}$/" in src


def test_code_gs_logs_only_the_selftest_line():
    src = CODE_GS.read_text(encoding="utf-8")
    assert src.count("Logger.log") == 1
    assert "console." not in src


def test_code_gs_get_never_writes():
    src = CODE_GS.read_text(encoding="utf-8")
    body = re.search(r"function doGet\(e\) \{(.*?)\n\}", src, re.DOTALL).group(1)
    assert "record_" not in body and "appendRow" not in body


def test_code_gs_holds_no_secrets_and_quotes_the_token():
    src = CODE_GS.read_text(encoding="utf-8")
    # Only the reserved example.com test-vector address and the public sender
    # address (Phase 4.2, newsletter@ on the owner's verified domain) may appear.
    found = re.findall(r"[\w.%+-]+@[\w.-]+\.[A-Za-z]{2,}", src)
    allowed = ("@example.com", "newsletter@modaklog.characterplanner.co.kr")
    assert found and all(a.lower().endswith(allowed) for a in found), found
    header = src.split("const SHEET")[0]
    for name in ("SHEET_ID", "TOKEN_SECRET", "LIST_KEY", "SEND_LIST_KEY", "ADMIN_KEY"):
        assert name in header
    for name in ("SHEET_ID", "LIST_KEY"):
        assert f"prop_('{name}')" in src
    # The token reaches the script through a quoted attribute, never a JS-context scriptlet.
    assert 'data-t="<?= t ?>"' in src
    assert '.unsubscribe(b.getAttribute("data-t"))' in src
    assert re.search(r"<script>[^<]*<\?=", src) is None
    assert "safeEq_(" in src and "LockService" in src and "matchEntireCell(true)" in src
    assert "postData.contents" in src


def test_brand_and_no_old_name():
    old = "해달 " + "브리프"
    for path in (CODE_GS, README):
        assert old not in path.read_text(encoding="utf-8")
    assert "모닥로그 AI 리포트 홈" in CODE_GS.read_text(encoding="utf-8")
    readme = README.read_text(encoding="utf-8")
    assert "모닥로그 AI 리포트 구독 관리" in readme
    assert "새 배포" in readme and "새 버전" in readme


CODE_GS_SENTENCES = (
    "구독이 해지됐어요. 다음 주부터는 메일이 가지 않아요.",
    "링크가 올바르지 않아요.",
    "잠시 후 다시 눌러 주세요.",
)


@pytest.mark.parametrize("sentence", CODE_GS_SENTENCES)
def test_code_gs_korean_passes_humanizer(sentence):
    assert sentence in CODE_GS.read_text(encoding="utf-8")
    codes = humanize.lint(sentence)
    assert not [c for c in codes if c in humanize.HARD_CODES], codes
