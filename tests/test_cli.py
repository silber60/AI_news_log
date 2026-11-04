"""Top-level CLI handler, failure notice (D-13) and build secret isolation (AUTO-02)."""

import json
import os
import re
from pathlib import Path

import respx
from conftest import FakeAnthropic, mock_hf_week

from newsletter import store

REPO = Path(__file__).parent.parent
ISSUE_ID = "2026-W44"
DELIVERY_SECRETS = (
    "SMTP_USER",
    "SMTP_PASSWORD",
    "SUBSCRIBERS_CSV",
    "TEST_RECIPIENT",
    "UNSUBSCRIBE_TOKEN_SECRET",
    "UNSUBSCRIBE_LIST_KEY",
)


def _status(root: Path) -> dict:
    return json.loads((root / "out" / "status.json").read_text(encoding="utf-8"))


# ------------------------------------------------------------ failure handler


def test_invalid_week_reports_stage_and_class_only(archive_tmp, capsys, monkeypatch):
    from newsletter.__main__ import main

    monkeypatch.delenv("NEWSLETTER_DEBUG", raising=False)
    assert main(["build", "--week", "2026-W54"]) == 1
    captured = capsys.readouterr()
    out = captured.out + captured.err
    assert "stage=week error=InvalidWeekError" in out
    assert "Traceback" not in out
    assert _status(archive_tmp) == {"stage": "week", "error_class": "InvalidWeekError"}


def test_debug_flag_prints_traceback(archive_tmp, capsys, monkeypatch):
    from newsletter.__main__ import main

    monkeypatch.setenv("NEWSLETTER_DEBUG", "1")
    assert main(["build", "--week", "2026-W54"]) == 1
    err = capsys.readouterr().err
    assert "Traceback" in err
    assert "stage=week error=InvalidWeekError" in err


def test_unexpected_error_in_build_uses_subcommand_stage(archive_tmp, capsys, monkeypatch):
    from newsletter import pipeline
    from newsletter.__main__ import main

    def boom(*a, **k):
        raise RuntimeError("secret detail subscriber@example.com")

    monkeypatch.setattr(pipeline, "run_build", boom)
    assert main(["build", "--week", ISSUE_ID]) == 1
    captured = capsys.readouterr()
    out = captured.out + captured.err
    assert "stage=build error=RuntimeError" in out
    assert "secret detail" not in out
    assert "@" not in out
    assert _status(archive_tmp) == {"stage": "build", "error_class": "RuntimeError"}


def test_unexpected_error_in_deliver_uses_subcommand_stage(archive_tmp, capsys, monkeypatch):
    from newsletter.__main__ import main
    from newsletter.delivery import deliver

    def boom(mode):
        raise RuntimeError("nope")

    monkeypatch.setattr(deliver, "run_deliver", boom)
    assert main(["deliver", "--mode", "send"]) == 1
    assert "stage=deliver error=RuntimeError" in capsys.readouterr().err
    assert _status(archive_tmp) == {"stage": "deliver", "error_class": "RuntimeError"}


def test_missing_current_issue_reports_class(archive_tmp, capsys, monkeypatch):
    from newsletter.__main__ import main

    monkeypatch.setenv("SMTP_USER", "owner@example.com")
    monkeypatch.setenv("SMTP_PASSWORD", "x")
    assert main(["deliver", "--mode", "test"]) == 1
    assert "stage=deliver error=FileNotFoundError" in capsys.readouterr().err


def test_keyboard_interrupt_propagates(archive_tmp, monkeypatch):
    import pytest

    from newsletter import pipeline
    from newsletter.__main__ import main

    def stop(*a, **k):
        raise KeyboardInterrupt

    monkeypatch.setattr(pipeline, "run_build", stop)
    with pytest.raises(KeyboardInterrupt):
        main(["build", "--week", ISSUE_ID])


# ------------------------------------------------------- build secret isolation


class GuardedEnviron(dict):
    def _check(self, key):
        if key in DELIVERY_SECRETS:
            raise AssertionError(f"build read delivery secret {key}")

    def __getitem__(self, key):
        self._check(key)
        return super().__getitem__(key)

    def get(self, key, default=None):
        self._check(key)
        return super().get(key, default)

    def __contains__(self, key):
        self._check(key)
        return super().__contains__(key)


def test_build_never_reads_delivery_secrets(hf_pages, archive_tmp, monkeypatch):
    from newsletter.pipeline import run_build

    env = GuardedEnviron(os.environ)
    for name in DELIVERY_SECRETS:
        dict.__setitem__(env, name, "should-not-be-read")
    monkeypatch.setattr(os, "environ", env)

    with respx.mock(assert_all_mocked=True) as router:
        mock_hf_week(router, hf_pages, ISSUE_ID)
        issue = run_build(ISSUE_ID, claude_client=FakeAnthropic())
    assert len(issue.items) == 10


def test_guard_actually_raises(monkeypatch):
    import pytest

    env = GuardedEnviron({"SMTP_USER": "x"})
    with pytest.raises(AssertionError):
        env.get("SMTP_USER")
    with pytest.raises(AssertionError):
        _ = "SUBSCRIBERS_CSV" in env


def test_only_delivery_package_names_delivery_secrets():
    pattern = re.compile("|".join(DELIVERY_SECRETS))
    offenders = []
    for path in (REPO / "newsletter").rglob("*.py"):
        rel = path.relative_to(REPO).as_posix()
        if rel.startswith("newsletter/delivery/"):
            continue
        if pattern.search(path.read_text(encoding="utf-8")):
            offenders.append(rel)
    assert offenders == []


def test_no_smtp_debug_anywhere():
    for path in (REPO / "newsletter").rglob("*.py"):
        assert "set_debuglevel" not in path.read_text(encoding="utf-8"), path


# --------------------------------------------------------- failure notice D-13


def _notify_env(monkeypatch):
    monkeypatch.setenv("SMTP_USER", "owner@example.com")
    monkeypatch.setenv("SMTP_PASSWORD", "abcd efgh")
    monkeypatch.setenv("TEST_RECIPIENT", "owner@example.com")
    monkeypatch.setenv("SUBSCRIBERS_CSV", "email\nsubscriber@example.com\n")
    monkeypatch.setenv("GITHUB_SERVER_URL", "https://github.com")
    monkeypatch.setenv("GITHUB_REPOSITORY", "silber60/AI_news_log")
    monkeypatch.setenv("GITHUB_RUN_ID", "12345")


def test_notify_failure_mails_owner_only(archive_tmp, fake_smtp, monkeypatch):
    from newsletter.__main__ import main

    _notify_env(monkeypatch)
    store.write_current(ISSUE_ID)
    store.write_json(
        store.out_root() / "status.json", {"stage": "fetch", "error_class": "FetchError"}
    )

    assert main(["notify-failure", "--mode", "send"]) == 0

    sent = fake_smtp.instances[0].sent
    assert len(sent) == 1
    msg = sent[0]
    assert msg["To"] == "owner@example.com"
    assert str(msg["Subject"]) == f"[실패] 모닥로그 AI 리포트 {ISSUE_ID}"
    assert msg.get_content_type() == "text/plain"
    body = msg.get_content()
    assert "fetch" in body
    assert "FetchError" in body
    assert "https://github.com/silber60/AI_news_log/actions/runs/12345" in body
    assert "subscriber@example.com" not in str(msg)


def test_notify_failure_without_status(archive_tmp, fake_smtp, monkeypatch):
    from newsletter.__main__ import main

    _notify_env(monkeypatch)
    assert main(["notify-failure", "--mode", "test"]) == 0
    msg = fake_smtp.instances[0].sent[0]
    assert "unknown" in str(msg["Subject"])
    assert "unknown" in msg.get_content()


def test_notify_failure_failing_prints_class_only(archive_tmp, capsys, monkeypatch):
    from newsletter.__main__ import main

    monkeypatch.delenv("TEST_RECIPIENT", raising=False)
    monkeypatch.setenv("SMTP_USER", "owner@example.com")
    monkeypatch.setenv("SMTP_PASSWORD", "abcd efgh")
    status = {"stage": "fetch", "error_class": "FetchError"}
    store.write_json(store.out_root() / "status.json", status)

    assert main(["notify-failure", "--mode", "test"]) == 1
    captured = capsys.readouterr()
    out = captured.out + captured.err
    assert "error=DeliveryError" in out
    assert "@" not in out
    assert "Traceback" not in out
    # the original failure status is preserved for the workflow
    assert _status(archive_tmp) == status


def test_delivery_error_detail_is_printed_without_addresses(capsys):
    from newsletter import __main__ as cli
    from newsletter.errors import DeliveryError

    cli._report("notify-failure", DeliveryError("SMTPAuthenticationError code=535 a@b.co"))
    err = capsys.readouterr().err
    assert "stage=notify-failure error=DeliveryError" in err
    assert "detail=SMTPAuthenticationError code=535" in err
    assert "@" not in err


# ------------------------------------------------------------ record-topic (D-06, D-15)


def _stage_issue(root: Path, issue) -> None:
    store.write_json(store.week_dir(issue.issue_id) / "issue.json", issue)
    store.write_current(issue.issue_id)


def _topics_file(root: Path, monkeypatch) -> Path:
    p = root / "explainer_topics.json"
    p.write_text('{"version": 1, "topics": []}\n', encoding="utf-8")
    monkeypatch.setenv("NEWSLETTER_TOPICS_PATH", str(p))
    return p


def _explained(issue):
    from newsletter.schema import Explainer

    topic = Explainer(topic="Mixture of Experts", body_ko="본문", related_ranks=[1])
    return issue.model_copy(update={"explainer": topic})


def test_record_topic_send_writes_one_entry_once(archive_tmp, issue_w44, monkeypatch, caplog):
    from newsletter.__main__ import main

    p = _topics_file(archive_tmp, monkeypatch)
    _stage_issue(archive_tmp, _explained(issue_w44))
    with caplog.at_level("INFO"):
        assert main(["record-topic", "--mode", "send"]) == 0
        assert main(["record-topic", "--mode", "send"]) == 0
    entries = json.loads(p.read_text(encoding="utf-8"))["topics"]
    assert entries == [{"issue_id": ISSUE_ID, "date": "2026-11-02", "topic": "Mixture of Experts"}]
    assert f"topic=recorded issue={ISSUE_ID}" in caplog.text
    assert f"topic=exists issue={ISSUE_ID}" in caplog.text
    assert "Mixture" not in caplog.text


def test_record_topic_preview_and_test_write_nothing(archive_tmp, issue_w44, monkeypatch, caplog):
    from newsletter.__main__ import main

    p = _topics_file(archive_tmp, monkeypatch)
    before = p.read_bytes()
    _stage_issue(archive_tmp, _explained(issue_w44))
    with caplog.at_level("INFO"):
        for mode in ("preview", "test"):
            assert main(["record-topic", "--mode", mode]) == 0
            assert f"topic=skipped mode={mode}" in caplog.text
    assert p.read_bytes() == before


def test_record_topic_without_explainer_writes_nothing(archive_tmp, issue_w44, monkeypatch, caplog):
    from newsletter.__main__ import main

    p = _topics_file(archive_tmp, monkeypatch)
    before = p.read_bytes()
    _stage_issue(archive_tmp, issue_w44)
    with caplog.at_level("INFO"):
        assert main(["record-topic", "--mode", "send"]) == 0
    assert f"topic=none issue={ISSUE_ID}" in caplog.text
    assert p.read_bytes() == before


def test_record_topic_without_current_issue_fails(archive_tmp, monkeypatch, capsys):
    from newsletter.__main__ import main

    p = _topics_file(archive_tmp, monkeypatch)
    before = p.read_bytes()
    monkeypatch.delenv("NEWSLETTER_DEBUG", raising=False)
    assert main(["record-topic", "--mode", "send"]) == 1
    assert "stage=record-topic error=FileNotFoundError" in capsys.readouterr().err
    assert p.read_bytes() == before
