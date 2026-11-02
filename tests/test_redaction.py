"""DLVR-06: SMTP failures never put addresses, names or credentials in output."""

import json
import shutil
import smtplib
from pathlib import Path

import pytest
from conftest import FakeSMTP

from newsletter import store

FIXTURES = Path(__file__).parent / "fixtures"
ISSUE_ID = "2026-W44"
PASSWORD = "abcd efgh"
CSV = "email,name\nsubscriber@example.com,홍길동\n"


@pytest.fixture
def ready(archive_tmp, monkeypatch):
    from newsletter.delivery import deliver

    week = store.week_dir(ISSUE_ID)
    week.mkdir(parents=True)
    shutil.copy(FIXTURES / "issue_w44.json", week / "issue.json")
    store.write_current(ISSUE_ID)
    monkeypatch.setattr(deliver, "SEND_PAUSE_SECONDS", 0)
    monkeypatch.setenv("SMTP_USER", "owner@example.com")
    monkeypatch.setenv("SMTP_PASSWORD", PASSWORD)
    monkeypatch.setenv("SUBSCRIBERS_CSV", CSV)
    return archive_tmp


def _patch_smtp(monkeypatch, cls):
    from newsletter.delivery import send

    FakeSMTP.instances = []
    monkeypatch.setattr(send.smtplib, "SMTP_SSL", cls)


def _assert_clean(out: str):
    assert "@" not in out
    assert "홍길동" not in out
    assert PASSWORD not in out
    assert PASSWORD.replace(" ", "") not in out
    assert "Traceback" not in out


def _status(root: Path) -> dict:
    return json.loads((root / "out" / "status.json").read_text(encoding="utf-8"))


class RefusingSMTP(FakeSMTP):
    def send_message(self, msg, *args, **kwargs):
        raise smtplib.SMTPRecipientsRefused({"subscriber@example.com": (550, b"no such user")})


class BadLoginSMTP(FakeSMTP):
    def login(self, user, password):
        raise smtplib.SMTPAuthenticationError(535, f"bad credentials for {user} {password}".encode())


class DebugRecordingSMTP(FakeSMTP):
    debug_calls: list = []

    def set_debuglevel(self, level):
        DebugRecordingSMTP.debug_calls.append(level)


def test_recipients_refused_is_redacted(ready, monkeypatch, capsys):
    from newsletter.__main__ import main

    _patch_smtp(monkeypatch, RefusingSMTP)
    assert main(["deliver", "--mode", "send"]) == 1

    captured = capsys.readouterr()
    out = captured.out + captured.err
    _assert_clean(out)
    assert "stage=deliver error=DeliveryError" in out
    assert _status(ready) == {"stage": "deliver", "error_class": "DeliveryError"}


def test_auth_failure_is_redacted(ready, monkeypatch, capsys):
    from newsletter.__main__ import main

    _patch_smtp(monkeypatch, BadLoginSMTP)
    assert main(["deliver", "--mode", "send"]) == 1

    captured = capsys.readouterr()
    out = captured.out + captured.err
    _assert_clean(out)
    assert "stage=deliver error=DeliveryError" in out
    assert _status(ready) == {"stage": "deliver", "error_class": "DeliveryError"}


def test_delivery_error_has_class_and_code_only(ready, monkeypatch):
    from newsletter.delivery.deliver import run_deliver
    from newsletter.errors import DeliveryError

    _patch_smtp(monkeypatch, RefusingSMTP)
    with pytest.raises(DeliveryError) as exc:
        run_deliver("send")
    assert "@" not in str(exc.value)
    assert "SMTPRecipientsRefused" in str(exc.value)
    assert exc.value.__suppress_context__
    assert exc.value.__cause__ is None


def test_connection_error_is_redacted(ready, monkeypatch):
    from newsletter.delivery.deliver import run_deliver
    from newsletter.errors import DeliveryError

    def boom(*a, **k):
        raise ConnectionRefusedError("refused")

    _patch_smtp(monkeypatch, boom)
    with pytest.raises(DeliveryError) as exc:
        run_deliver("send")
    assert str(exc.value).startswith("ConnectionRefusedError")


def test_smtp_debug_never_enabled(ready, monkeypatch):
    from newsletter.__main__ import main

    DebugRecordingSMTP.debug_calls = []
    _patch_smtp(monkeypatch, DebugRecordingSMTP)
    assert main(["deliver", "--mode", "send"]) == 0
    assert len(FakeSMTP.instances[0].sent) == 1
    assert DebugRecordingSMTP.debug_calls == []


def test_send_logs_counts_only(ready, fake_smtp, capsys, caplog):
    from newsletter.__main__ import main

    caplog.set_level("INFO")
    assert main(["deliver", "--mode", "send"]) == 0
    captured = capsys.readouterr()
    out = captured.out + captured.err + caplog.text
    assert "@" not in out
    assert "홍길동" not in out
    assert "recipients=1 sent=1 skipped_rows=0" in out
