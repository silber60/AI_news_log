"""Send ledger (DLVR-05, D-05 amended by owner A1): keyed HMAC-SHA256 per mailed reader
per week, written after every successful message, so a re-run never mails twice."""

import json
import re
import shutil
from pathlib import Path

import pytest

from newsletter import store

FIXTURES = Path(__file__).parent / "fixtures"
ISSUE_ID = "2026-W44"
SECRET = "test-token-secret"
OWNER = "owner@example.com"
A, B, C = "a@example.com", "b@example.com", "c@example.com"
NAMES = ("가", "나", "다")
HEX64 = re.compile(r"\b[0-9a-f]{64}\b")


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
    monkeypatch.setenv("SMTP_USER", OWNER)
    monkeypatch.setenv("SMTP_PASSWORD", "abcd efgh")
    monkeypatch.setenv("UNSUBSCRIBE_TOKEN_SECRET", SECRET)
    monkeypatch.setenv("TEST_RECIPIENT", OWNER)
    monkeypatch.setenv("SUBSCRIBERS_CSV", f"email,name\n{A},가\n{B},나\n")


def _ledger_path() -> Path:
    from newsletter import ledger

    return ledger.ledger_dir() / f"{ISSUE_ID}.json"


# ------------------------------------------------------------------ key


def test_key_normalizes_and_is_hex64():
    from newsletter import ledger

    k = ledger.key("  Alice@Example.COM ", SECRET)
    assert k == ledger.key("alice@example.com", SECRET)
    assert re.fullmatch(r"[0-9a-f]{64}", k)
    assert k != ledger.key("alice@example.com", "another-secret")


def test_key_is_not_the_unsubscribe_token():
    from newsletter import ledger
    from newsletter.delivery.unsubscribe import token

    k = ledger.key("alice@example.com", SECRET)
    t = token("alice@example.com", SECRET)
    assert k != t and not k.startswith(t)


def test_ledger_dir_honors_env(tmp_path, monkeypatch):
    from newsletter import ledger

    monkeypatch.setenv("NEWSLETTER_LEDGER_DIR", str(tmp_path / "x"))
    assert ledger.ledger_dir() == tmp_path / "x"
    monkeypatch.delenv("NEWSLETTER_LEDGER_DIR")
    assert ledger.ledger_dir() == store.REPO_ROOT / "data" / "ledger"


def test_load_missing_is_empty_and_save_roundtrips():
    from newsletter import ledger

    assert ledger.load(ISSUE_ID) == set()
    ledger.save(ISSUE_ID, {"b" * 64, "a" * 64})
    assert ledger.load(ISSUE_ID) == {"a" * 64, "b" * 64}
    data = json.loads(_ledger_path().read_text(encoding="utf-8"))
    assert data == {
        "version": 1,
        "issue_id": ISSUE_ID,
        "scheme": "hmac-sha256-ledger-v1",
        "sent": ["a" * 64, "b" * 64],
    }
    assert not list(ledger.ledger_dir().glob("*.tmp"))


# ------------------------------------------------------------------ tracer


def test_send_writes_ledger_and_rerun_sends_nothing(current_issue, send_env, fake_smtp):
    from newsletter import ledger
    from newsletter.delivery.deliver import run_deliver

    first = run_deliver("send")
    assert first["sent"] == 2 and first["skipped_ledger"] == 0
    data = json.loads(_ledger_path().read_text(encoding="utf-8"))
    assert data["version"] == 1
    assert data["issue_id"] == ISSUE_ID
    assert data["scheme"] == "hmac-sha256-ledger-v1"
    assert data["sent"] == sorted([ledger.key(A, SECRET), ledger.key(B, SECRET)])

    second = run_deliver("send")
    assert second["sent"] == 0 and second["skipped_ledger"] == 2
    assert sum(len(s.sent) for s in fake_smtp.instances) == 2
    report = store.read_json(store.out_root() / "report.json")
    assert report["outcome"] == "sent"
    assert report["sent"] == 0 and report["skipped_ledger"] == 2

    raw = _ledger_path().read_text(encoding="utf-8")
    assert "@" not in raw
    for name in NAMES:
        assert name not in raw


# ------------------------------------------------------------------ partial failure


THREE_CSV = f"email,name\n{A},가\n{B},나\n{C},다\n"


def _failing_smtp(monkeypatch, fail_on: int):
    """FakeSMTP whose send_message raises on the fail_on-th call (1-based)."""
    import smtplib

    from conftest import FakeSMTP

    from newsletter.delivery import send

    class FailingSMTP(FakeSMTP):
        def send_message(self, msg, *args, **kwargs):
            if len(self.sent) + 1 == fail_on:
                raise smtplib.SMTPRecipientsRefused({})
            return super().send_message(msg, *args, **kwargs)

    FakeSMTP.instances = []
    monkeypatch.setattr(send.smtplib, "SMTP_SSL", FailingSMTP)
    return FailingSMTP


def test_partial_failure_then_rerun_sends_only_the_rest(current_issue, send_env, monkeypatch):
    from conftest import FakeSMTP

    from newsletter import ledger
    from newsletter.delivery import send
    from newsletter.delivery.deliver import run_deliver
    from newsletter.errors import DeliveryError

    monkeypatch.setenv("SUBSCRIBERS_CSV", THREE_CSV)
    failing = _failing_smtp(monkeypatch, fail_on=3)
    with pytest.raises(DeliveryError):
        run_deliver("send")
    assert [m["To"] for m in failing.instances[0].sent] == [A, B]
    assert ledger.load(ISSUE_ID) == {ledger.key(A, SECRET), ledger.key(B, SECRET)}

    FakeSMTP.instances = []
    monkeypatch.setattr(send.smtplib, "SMTP_SSL", FakeSMTP)
    result = run_deliver("send")
    sent = [m for s in FakeSMTP.instances for m in s.sent]
    assert len(sent) == 1
    assert sent[0]["To"] == C
    assert result["sent"] == 1 and result["skipped_ledger"] == 2
    assert ledger.load(ISSUE_ID) == {ledger.key(x, SECRET) for x in (A, B, C)}


# ------------------------------------------------------------------ test mode


def test_test_mode_leaves_existing_ledger_untouched(current_issue, send_env, fake_smtp):
    import os

    from newsletter import ledger
    from newsletter.delivery.deliver import run_deliver

    ledger.save(ISSUE_ID, {ledger.key(OWNER, SECRET)})
    path = _ledger_path()
    before = (path.read_bytes(), os.stat(path).st_mtime_ns)
    run_deliver("test")
    assert (path.read_bytes(), os.stat(path).st_mtime_ns) == before
    assert len(fake_smtp.instances[0].sent) == 1


def test_test_mode_creates_no_ledger(current_issue, send_env, fake_smtp, monkeypatch):
    from newsletter import ledger
    from newsletter.delivery.deliver import run_deliver

    def boom(*a, **kw):
        raise AssertionError("test mode must not touch the ledger")

    monkeypatch.setattr(ledger, "load", boom)
    monkeypatch.setattr(ledger, "save", boom)
    run_deliver("test")
    assert not ledger.ledger_dir().exists()


# ------------------------------------------------------------------ fail closed


def test_send_without_secret_fails_before_list_and_smtp(
    current_issue, send_env, fake_smtp, monkeypatch
):
    import respx

    from newsletter.delivery import unsubscribe
    from newsletter.delivery.deliver import run_deliver
    from newsletter.errors import DeliveryError

    monkeypatch.delenv("UNSUBSCRIBE_TOKEN_SECRET")
    monkeypatch.setattr(unsubscribe, "UNSUBSCRIBE_ENDPOINT", "https://example.invalid/exec")
    monkeypatch.setenv("SUBSCRIBER_LIST_KEY", "k1")
    monkeypatch.setenv("UNSUBSCRIBE_LIST_KEY", "k2")
    with respx.mock(assert_all_mocked=True) as router:
        with pytest.raises(DeliveryError, match="UNSUBSCRIBE_TOKEN_SECRET"):
            run_deliver("send")
        assert router.calls.call_count == 0
    assert fake_smtp.instances == []
    assert not _ledger_path().exists()


def test_send_without_secret_and_endpoint_fails_before_smtp(
    current_issue, send_env, fake_smtp, monkeypatch
):
    from newsletter.delivery.deliver import run_deliver
    from newsletter.errors import DeliveryError

    monkeypatch.delenv("UNSUBSCRIBE_TOKEN_SECRET")
    with pytest.raises(DeliveryError, match="UNSUBSCRIBE_TOKEN_SECRET"):
        run_deliver("send")
    assert fake_smtp.instances == []


@pytest.mark.parametrize(
    "payload",
    [
        {"version": 1, "issue_id": ISSUE_ID, "scheme": "sha256", "sent": []},
        {"version": 1, "issue_id": "2026-W43", "scheme": "hmac-sha256-ledger-v1", "sent": []},
        {"version": 2, "issue_id": ISSUE_ID, "scheme": "hmac-sha256-ledger-v1", "sent": []},
        "not json",
    ],
    ids=["other-scheme", "other-issue", "other-version", "unreadable"],
)
def test_mismatched_ledger_fails_closed(current_issue, send_env, fake_smtp, payload):
    from newsletter.delivery.deliver import run_deliver
    from newsletter.errors import DeliveryError

    path = _ledger_path()
    path.parent.mkdir(parents=True)
    path.write_text(payload if isinstance(payload, str) else json.dumps(payload), "utf-8")
    with pytest.raises(DeliveryError):
        run_deliver("send")
    assert fake_smtp.instances == []


# ------------------------------------------------------------------ leaks


def _snapshot(d: Path) -> list[tuple[str, bytes]]:
    if not d.exists():
        return []
    return sorted((p.name, p.read_bytes()) for p in d.iterdir() if p.is_file())


def test_no_test_writes_the_repo_ledger(current_issue, send_env, fake_smtp):
    from newsletter import ledger
    from newsletter.delivery.deliver import run_deliver

    repo_ledger = store.REPO_ROOT / "data" / "ledger"
    before = _snapshot(repo_ledger)
    assert ledger.ledger_dir() != repo_ledger
    run_deliver("send")
    run_deliver("send")
    assert _snapshot(repo_ledger) == before
    assert _ledger_path().exists()


def test_send_logs_hold_no_address_or_key(current_issue, send_env, fake_smtp, caplog, capsys):
    from newsletter import ledger
    from newsletter.delivery.deliver import run_deliver

    caplog.set_level("DEBUG")
    run_deliver("send")
    run_deliver("send")
    captured = capsys.readouterr()
    text = caplog.text + captured.out + captured.err
    assert "@" not in text
    assert not HEX64.search(text)
    for addr in (A, B):
        assert ledger.key(addr, SECRET) not in text
    assert SECRET not in text
    assert "skipped_ledger=2 sent=0" in caplog.text
