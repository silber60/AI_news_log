"""Deliver stage. The only package that reads SMTP and recipient secrets.

Phase 1 tracer: `test` mode sends one message to TEST_RECIPIENT. Plan 05 adds
`send` mode, subscribers and redaction.
"""

import logging
import os

from newsletter import store
from newsletter.delivery.send import build_message, send_messages
from newsletter.errors import DeliveryError
from newsletter.schema import Issue
from newsletter.stages.render import build_subject, render_html, render_text

log = logging.getLogger(__name__)

TEST_GREETING = "구독자님"


def _env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise DeliveryError(f"missing environment variable {name}")
    return value


def load_current_issue() -> Issue:
    issue_id = store.read_current()
    return Issue.model_validate(store.read_json(store.week_dir(issue_id) / "issue.json"))


def run_deliver(mode: str) -> dict:
    if mode != "test":
        raise DeliveryError(f"unsupported mode {mode}")
    user = _env("SMTP_USER")
    password = _env("SMTP_PASSWORD")
    recipient = _env("TEST_RECIPIENT")

    issue = load_current_issue()
    msg = build_message(
        subject=build_subject(issue, "test"),
        sender_addr=user,
        to=recipient,
        text=render_text(issue, TEST_GREETING),
        html=render_html(issue, TEST_GREETING),
    )
    sent = send_messages([msg], user=user, password=password)
    result = {"recipients": 1, "sent": sent}
    log.info("mode=test recipients=%d sent=%d", result["recipients"], sent)
    return result
