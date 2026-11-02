"""Deliver stage. The only package that reads SMTP and recipient secrets.

`test` sends one de-personalized message to TEST_RECIPIENT. `send` sends one
personalized message per subscriber from the SUBSCRIBERS_CSV secret. Logs carry
counts only, never addresses or names (DLVR-06).
"""

import logging
import os

from newsletter import store
from newsletter.delivery.send import build_message, send_messages
from newsletter.delivery.subscribers import DEFAULT_GREETING, display_name, parse_subscribers
from newsletter.errors import DeliveryError
from newsletter.schema import Issue
from newsletter.stages.render import build_subject, render_html, render_text

log = logging.getLogger(__name__)

TEST_GREETING = DEFAULT_GREETING
SEND_PAUSE_SECONDS = 1.0


def _env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise DeliveryError(f"missing environment variable {name}")
    return value


def load_current_issue() -> Issue:
    issue_id = store.read_current()
    return Issue.model_validate(store.read_json(store.week_dir(issue_id) / "issue.json"))


def _run_test(issue: Issue, user: str, password: str) -> dict:
    recipient = _env("TEST_RECIPIENT")
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


def _run_send(issue: Issue, user: str, password: str) -> dict:
    subscribers, skipped = parse_subscribers(_env("SUBSCRIBERS_CSV"))
    subject = build_subject(issue, "send")  # D-03: no prefix
    messages = []
    for sub in subscribers:
        greeting = display_name(sub.name)  # body only, never a header
        messages.append(
            build_message(
                subject=subject,
                sender_addr=user,
                to=sub.email,
                text=render_text(issue, greeting),
                html=render_html(issue, greeting),  # re-checks size per recipient
            )
        )
    sent = send_messages(messages, user=user, password=password, pause=SEND_PAUSE_SECONDS)
    result = {"recipients": len(subscribers), "sent": sent, "skipped_rows": skipped}
    log.info(
        "mode=send recipients=%d sent=%d skipped_rows=%d",
        result["recipients"],
        sent,
        skipped,
    )
    return result


def run_deliver(mode: str) -> dict:
    if mode not in ("test", "send"):
        raise DeliveryError(f"unsupported mode {mode}")
    user = _env("SMTP_USER")
    password = _env("SMTP_PASSWORD")
    issue = load_current_issue()
    if mode == "test":
        return _run_test(issue, user, password)
    return _run_send(issue, user, password)
