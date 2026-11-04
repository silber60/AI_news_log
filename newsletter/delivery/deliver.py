"""Deliver stage. The only package that reads SMTP and recipient secrets.

`test` sends one de-personalized message to TEST_RECIPIENT. `send` sends one
personalized message per subscriber, skipping anyone whose unsubscribe token is
on the Apps Script list (D-13). The subscribers come from the live Sheet list
(Apps Script action=members with SUBSCRIBER_LIST_KEY, D-08) once
UNSUBSCRIBE_ENDPOINT is set, and from the SUBSCRIBERS_CSV secret while it is None
(the transition until 04.1-06). Readers already in that week's send ledger are
skipped, and each successful message is added to the ledger at once (DLVR-05).
Logs carry counts only, never addresses, names, tokens or keys (DLVR-06).
"""

import logging
import os
from datetime import datetime

from newsletter import ledger, store, week
from newsletter.delivery import members, unsubscribe
from newsletter.delivery.send import build_message, send_messages
from newsletter.delivery.subscribers import DEFAULT_GREETING, display_name, parse_subscribers
from newsletter.errors import DeliveryError, StaleIssueError
from newsletter.schema import Issue
from newsletter.stages.render import SITE_URL, build_subject, render_html, render_text

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


def _token_secret() -> str | None:
    """D-11: the HMAC secret, needed only once the endpoint exists. Never send a link
    without a token (research: Secrets)."""
    if unsubscribe.UNSUBSCRIBE_ENDPOINT is None:
        return None
    return _env("UNSUBSCRIBE_TOKEN_SECRET")


def _unsubscribe_parts(
    addr: str, user: str, secret: str | None
) -> tuple[str | None, str | None, str]:
    """(token, footer link, List-Unsubscribe value) for one address (D-11, D-14).

    The mailto part uses SMTP_USER at runtime and is never hardcoded. With no endpoint
    there is no token: mailto only and no footer link. None of these values is logged.
    """
    header = f"<mailto:{user}?subject=unsubscribe>"
    endpoint = unsubscribe.UNSUBSCRIBE_ENDPOINT
    if endpoint is None or secret is None:
        return None, None, header
    t = unsubscribe.token(addr, secret)
    return t, f"{SITE_URL}unsubscribe/?t={t}", f"{header}, <{endpoint}?t={t}>"


def _run_test(issue: Issue, user: str, password: str) -> dict:
    recipient = _env("TEST_RECIPIENT")
    # The owner's own token, so the test send exercises the real flow; no list fetch.
    t, link, header = _unsubscribe_parts(recipient, user, _token_secret())
    msg = build_message(
        subject=build_subject(issue, "test"),
        sender_addr=user,
        to=recipient,
        text=render_text(issue, TEST_GREETING, unsubscribe_url=link),
        html=render_html(issue, TEST_GREETING, unsubscribe_url=link),
        list_unsubscribe=header,
        one_click=t is not None,
    )
    sent = send_messages([msg], password=password)
    result = {"recipients": 1, "sent": sent}
    log.info("mode=test recipients=%d sent=%d", result["recipients"], sent)
    return result


def _run_send(issue: Issue, user: str, password: str) -> dict:
    subject = build_subject(issue, "send")  # D-03: no prefix
    # DLVR-05: the ledger key needs the secret even without an endpoint; read it before
    # any list fetch or SMTP connection (fail closed).
    ledger_secret = _env("UNSUBSCRIBE_TOKEN_SECRET")
    secret = _token_secret()
    gone: set[str] = set()
    endpoint = unsubscribe.UNSUBSCRIBE_ENDPOINT
    if endpoint is None:
        subscribers, skipped = parse_subscribers(_env("SUBSCRIBERS_CSV"))
    else:
        # D-08 / D-13 fail closed: read both keys first, then the live list and the
        # unsubscribe list, all before any message or SMTP connection. A missing key or
        # any read problem raises DeliveryError (no rows: NoSubscribersError).
        list_key = _env("SUBSCRIBER_LIST_KEY")
        unsub_key = _env("UNSUBSCRIBE_LIST_KEY")
        subscribers, skipped = members.fetch_subscribers(endpoint, list_key)
        gone = unsubscribe.fetch_unsubscribed(endpoint, unsub_key)
    done = ledger.load(issue.issue_id)
    messages = []
    keys: list[str] = []
    unsubscribed = 0
    skipped_ledger = 0
    for sub in subscribers:
        t, link, header = _unsubscribe_parts(sub.email, user, secret)
        if t is not None and t in gone:
            unsubscribed += 1
            continue
        k = ledger.key(sub.email, ledger_secret)
        if k in done:
            skipped_ledger += 1
            continue
        keys.append(k)
        greeting = display_name(sub.name)  # body only, never a header
        messages.append(
            build_message(
                subject=subject,
                sender_addr=user,
                to=sub.email,
                text=render_text(issue, greeting, unsubscribe_url=link),
                html=render_html(issue, greeting, unsubscribe_url=link),  # size per recipient
                list_unsubscribe=header,
                one_click=t is not None,
            )
        )

    def record(i: int) -> None:
        # Rewrite the ledger right after each message, so a run that stops partway
        # keeps everyone already mailed (D-05).
        done.add(keys[i])
        ledger.save(issue.issue_id, done)

    sent = 0
    if messages:
        sent = send_messages(messages, password=password, pause=SEND_PAUSE_SECONDS, on_sent=record)
    else:
        log.info("mode=send nothing to send after unsubscribe and ledger filter")
    result = {
        "recipients": len(subscribers),
        "unsubscribed": unsubscribed,
        "skipped_ledger": skipped_ledger,
        "sent": sent,
        "skipped_rows": skipped,
    }
    log.info(
        "mode=send recipients=%d unsubscribed=%d skipped_ledger=%d sent=%d skipped_rows=%d",
        result["recipients"],
        unsubscribed,
        skipped_ledger,
        sent,
        skipped,
    )
    return result


def _now() -> datetime:
    return datetime.now(week.KST)


def _paused() -> bool:
    """D-02: SEND_PAUSED reaches only scheduled runs (the workflow passes '' on dispatch)."""
    return os.environ.get("SEND_PAUSED", "").strip().lower() == "true"


def _finish(report: dict) -> dict:
    """Write out/report.json and hand the outcome to the workflow (counts and ids only)."""
    store.write_json(store.out_root() / "report.json", report)
    output = os.environ.get("GITHUB_OUTPUT", "").strip()
    if output:
        with open(output, "a", encoding="utf-8") as f:
            f.write(f"outcome={report['outcome']}\n")
    return report


def run_deliver(mode: str, *, allow_stale: bool = False) -> dict:
    """Order in send mode: pause, then stale, then secrets, then the lists, then SMTP
    (research Pattern 2). `allow_stale` comes only from the deliberate --allow-stale flag."""
    if mode not in ("test", "send"):
        raise DeliveryError(f"unsupported mode {mode}")
    issue = load_current_issue()
    if mode == "send" and _paused():
        log.info("mode=send outcome=paused issue=%s", issue.issue_id)
        return _finish({"outcome": "paused", "issue_id": issue.issue_id})
    if mode == "send" and not allow_stale and not week.is_sendable(issue.issue_id, _now()):
        log.info("mode=send outcome=stale issue=%s", issue.issue_id)
        raise StaleIssueError("issue outside its send day")
    user = _env("SMTP_USER")
    password = _env("SMTP_PASSWORD")
    if mode == "test":
        result = _run_test(issue, user, password)
        outcome = "tested"
    else:
        result = _run_send(issue, user, password)
        outcome = "sent"
    _finish({**result, "outcome": outcome, "issue_id": issue.issue_id})
    return result
