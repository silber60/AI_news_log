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
