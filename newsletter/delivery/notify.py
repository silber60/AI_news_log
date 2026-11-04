"""Failure notice to the owner (D-13).

Mails a short plain-text notice to TEST_RECIPIENT only, never to subscribers.
The body holds the failed stage, the error class and the Actions run URL.
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


def send_failure_notice(mode: str) -> int:
    user = _env("SMTP_USER")
    password = _env("SMTP_PASSWORD")
    recipient = _env("TEST_RECIPIENT")
    issue_id = _issue_id()
    msg = build_text_message(
        subject=f"[실패] {SENDER_NAME} {issue_id}",
        sender_addr=user,
        to=recipient,
        text=build_notice_text(mode, issue_id, _status()),
    )
    sent = send_messages([msg], password=password)
    log.info("failure notice sent=%d", sent)
    return sent
