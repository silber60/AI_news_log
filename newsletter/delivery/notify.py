"""Weekly run report to the owner (D-06, AUTO-04; replaces the D-13 failure notice).

Mails one short plain-text report to TEST_RECIPIENT only, never to subscribers.
It reads out/report.json (written by deliver) and out/status.json (written by the
CLI failure handler). Bodies hold counts, ids, stage, error class and URLs only:
never an address, a name, a ledger key, a token or Claude text.
"""

import logging
import os

from newsletter import store
from newsletter.delivery.send import SENDER_NAME, build_text_message, send_messages
from newsletter.errors import DeliveryError

log = logging.getLogger(__name__)

UNKNOWN = "unknown"


def _env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise DeliveryError(f"missing environment variable {name}")
    return value


def _issue_id() -> str:
    try:
        return store.read_current()
    except OSError, ValueError, KeyError, TypeError:
        return UNKNOWN


def _status() -> dict:
    try:
        data = store.read_json(store.out_root() / "status.json")
    except OSError, ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def _report() -> dict:
    try:
        data = store.read_json(store.out_root() / "report.json")
    except OSError, ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def _run_url() -> str:
    server = os.environ.get("GITHUB_SERVER_URL", "").strip()
    repo = os.environ.get("GITHUB_REPOSITORY", "").strip()
    run_id = os.environ.get("GITHUB_RUN_ID", "").strip()
    if server and repo and run_id:
        return f"{server}/{repo}/actions/runs/{run_id}"
    return UNKNOWN


def build_notice_text(mode: str, issue_id: str, status: dict) -> str:
    stage = str(status.get("stage") or UNKNOWN)
    error_class = str(status.get("error_class") or UNKNOWN)
    return (
        f"{SENDER_NAME} {issue_id} 실행이 실패했습니다.\n\n"
        f"mode: {mode}\n"
        f"stage: {stage}\n"
        f"error_class: {error_class}\n"
        f"run: {_run_url()}\n"
    )


COUNT_KEYS = ("recipients", "sent", "skipped_ledger", "unsubscribed", "skipped_rows")


def _count(report: dict, key: str) -> int:
    value = report.get(key, 0)
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _sent_text(issue_id: str, report: dict) -> str:
    from newsletter.stages.render import issue_url

    counts = "".join(f"{key}: {_count(report, key)}\n" for key in COUNT_KEYS)
    return f"{SENDER_NAME} {issue_id} 호를 보냈어요.\n\n{counts}web: {issue_url(issue_id)}\n"


def build_report(mode: str, issue_id: str, status: dict, report: dict) -> tuple[str, str] | None:
    """(subject, text) for the owner, or None when no mail is due (research Pattern 7)."""
    if not status and mode == "send" and report.get("outcome") == "sent":
        return f"[발송 완료] {SENDER_NAME} {issue_id}", _sent_text(issue_id, report)
    return f"[실패] {SENDER_NAME} {issue_id}", build_notice_text(mode, issue_id, status)


def send_report(mode: str) -> int:
    """Mail the run report; 0 without any secret use when no mail is due."""
    status = _status()
    report = _report()
    raw_id = report.get("issue_id")
    issue_id = raw_id if isinstance(raw_id, str) and raw_id.strip() else _issue_id()
    built = build_report(mode, issue_id, status, report)
    if built is None:
        log.info("report mode=%s mail=none", mode)
        return 0
    subject, text = built
    user = _env("SMTP_USER")
    password = _env("SMTP_PASSWORD")
    recipient = _env("TEST_RECIPIENT")
    msg = build_text_message(subject=subject, sender_addr=user, to=recipient, text=text)
    sent = send_messages([msg], password=password)
    log.info("report mode=%s sent=%d", mode, sent)
    return sent


def send_failure_notice(mode: str) -> int:
    """notify-failure alias (D-06): the same report as `report --mode`."""
    return send_report(mode)
