"""One-time import of SUBSCRIBERS_CSV into the Sheet via action=import (D-06)."""

import json
import logging
from urllib.parse import parse_qs

import httpx
import pytest
import respx

from newsletter.delivery import unsubscribe
from newsletter.delivery.importer import BATCH, import_subscribers
from newsletter.errors import DeliveryError

ENDPOINT = "https://script.google.com/macros/s/AKfycbIMPORT/exec"
ECHO = "https://script.googleusercontent.com/macros/echo?user_content_key=import"
KEY = "admin-key-do-not-use-0987654321"
NAME = "홍길동"


def _csv(n: int, extra: str = "") -> str:
    rows = "".join(f"user{i}@example.com,{NAME}{i}\n" for i in range(n))
    return "email,name\n" + rows + extra


def _ok(added=1, existing=0, unsub=0, skipped=0) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "version": 1,
            "added": added,
            "existing": existing,
            "unsubscribed": unsub,
            "skipped": skipped,
        },
    )


def _bodies(route) -> list[dict]:
    return [parse_qs(c.request.content.decode()) for c in route.calls]


def _client() -> httpx.Client:
    return httpx.Client(timeout=5)


def test_batch_size_is_25():
    assert BATCH == 25


@respx.mock
def test_sixty_rows_post_three_batches_and_sum_counts():
    route = respx.post(ENDPOINT).mock(
        side_effect=[_ok(20, 3, 1, 1), _ok(25, 0, 0, 0), _ok(8, 1, 1, 0)]
    )
    with _client() as c:
        result = import_subscribers(ENDPOINT, KEY, _csv(60, "bad,x\n"), client=c)
    assert result == {
        "rows": 60,
        "added": 53,
        "existing": 4,
        "unsubscribed": 2,
        "skipped": 1,
        "skipped_rows": 1,
    }
    bodies = _bodies(route)
    assert [len(json.loads(b["rows"][0])) for b in bodies] == [25, 25, 10]
    for b in bodies:
        assert set(b) == {"action", "key", "rows"}
        assert b["action"] == ["import"] and b["key"] == [KEY]
    first = json.loads(bodies[0]["rows"][0])
    assert first[0] == {"email": "user0@example.com", "name": f"{NAME}0"}
    assert json.loads(bodies[2]["rows"][0])[-1]["email"] == "user59@example.com"
    for call in route.calls:
        assert KEY not in str(call.request.url) and "@" not in str(call.request.url)


@respx.mock
def test_import_follows_302():
    respx.post(ENDPOINT).mock(return_value=httpx.Response(302, headers={"Location": ECHO}))
    respx.get(ECHO).mock(return_value=_ok(1))
    result = import_subscribers(ENDPOINT, KEY, _csv(1))
    assert result["added"] == 1 and result["rows"] == 1


def _clean(text: str) -> None:
    assert KEY not in text
    assert "@" not in text
    assert NAME not in text


def _clean_error(text: str) -> None:
    _clean(text)
    assert "macros" not in text and "?" not in text


@pytest.mark.parametrize(
    ("reply", "message"),
    [
        (httpx.Response(200, json={"error": "forbidden"}), "import unreadable"),
        (httpx.Response(200, json={"error": "too_many"}), "import unreadable"),
        (httpx.Response(500, text="boom"), "import status=500"),
        (httpx.Response(200, text="<html>no</html>"), "import unreadable"),
        (httpx.Response(200, json={"version": 2, "added": 1}), "import unreadable"),
        (
            httpx.Response(
                200,
                json={"version": 1, "added": "1", "existing": 0, "unsubscribed": 0, "skipped": 0},
            ),
            "import unreadable",
        ),
        (httpx.ConnectError(f"cannot reach {ENDPOINT}?key={KEY}"), "import ConnectError"),
    ],
    ids=["forbidden", "too-many", "status-500", "not-json", "version-2", "bad-count", "connect"],
)
@respx.mock
def test_any_bad_batch_fails_with_class_or_status_only(reply, message):
    replies = [_ok(25)]
    replies.append(reply)
    route = respx.post(ENDPOINT).mock(side_effect=replies)
    with _client() as c, pytest.raises(DeliveryError) as exc:
        import_subscribers(ENDPOINT, KEY, _csv(30), client=c)
    assert str(exc.value) == message
    assert exc.value.__cause__ is None
    assert route.call_count == 2
    _clean_error(str(exc.value))


@respx.mock
def test_importer_logs_nothing_private(caplog):
    caplog.set_level(logging.DEBUG)
    respx.post(ENDPOINT).mock(return_value=_ok(2))
    with _client() as c:
        import_subscribers(ENDPOINT, KEY, _csv(2), client=c)
    _clean(caplog.text)


# ------------------------------------------------------------------- CLI


@pytest.fixture
def import_env(archive_tmp, monkeypatch):
    monkeypatch.setattr(unsubscribe, "UNSUBSCRIBE_ENDPOINT", ENDPOINT)
    monkeypatch.setenv("SUBSCRIBE_ADMIN_KEY", KEY)
    monkeypatch.setenv("SUBSCRIBERS_CSV", _csv(60))
    monkeypatch.delenv("NEWSLETTER_DEBUG", raising=False)


def test_cli_logs_one_counts_line(import_env, caplog, capsys):
    from newsletter.__main__ import main

    caplog.set_level(logging.DEBUG)
    with respx.mock(assert_all_mocked=True) as router:
        router.post(ENDPOINT).mock(side_effect=[_ok(25), _ok(24, 1), _ok(9, 0, 1)])
        assert main(["import-subscribers"]) == 0
    lines = [r.getMessage() for r in caplog.records if r.getMessage().startswith("import ")]
    assert lines == ["import rows=60 added=58 existing=1 unsubscribed=1 skipped=0 skipped_rows=0"]
    captured = capsys.readouterr()
    _clean(caplog.text + captured.out + captured.err)


def test_cli_failure_prints_stage_and_class_only(import_env, caplog, capsys):
    from newsletter.__main__ import main

    with respx.mock(assert_all_mocked=True) as router:
        router.post(ENDPOINT).mock(return_value=httpx.Response(200, json={"error": "forbidden"}))
        assert main(["import-subscribers"]) == 1
    captured = capsys.readouterr()
    out = captured.out + captured.err
    assert "stage=import-subscribers error=DeliveryError" in out
    assert "Traceback" not in out
    _clean(out + caplog.text)


def test_cli_without_endpoint_posts_nothing(import_env, monkeypatch, capsys):
    from newsletter.__main__ import main
    from newsletter.errors import DeliveryError

    monkeypatch.setattr(unsubscribe, "UNSUBSCRIBE_ENDPOINT", None)
    with respx.mock(assert_all_mocked=True) as router:
        assert main(["import-subscribers"]) == 1
        assert router.calls.call_count == 0
    err = capsys.readouterr().err
    assert "stage=import-subscribers error=DeliveryError" in err
    assert "detail=unsubscribe endpoint not set" in err

    from newsletter.__main__ import _import_subscribers

    with pytest.raises(DeliveryError, match="unsubscribe endpoint not set"):
        _import_subscribers()


@pytest.mark.parametrize("missing", ["SUBSCRIBE_ADMIN_KEY", "SUBSCRIBERS_CSV"])
def test_cli_missing_env_names_the_variable(import_env, monkeypatch, missing):
    from newsletter.__main__ import _import_subscribers

    monkeypatch.delenv(missing)
    with respx.mock(assert_all_mocked=True) as router:
        with pytest.raises(DeliveryError, match=f"missing environment variable {missing}"):
            _import_subscribers()
        assert router.calls.call_count == 0
