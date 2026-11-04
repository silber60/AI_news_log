"""Build and send email messages over Gmail SMTP (SSL, port 465).

Never enable SMTP debug output: it would print addresses and credentials to the
public Actions log.
"""

import logging
import smtplib
import ssl
import time
from collections.abc import Iterable
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid

from newsletter.errors import DeliveryError

log = logging.getLogger(__name__)

SENDER_NAME = "모닥로그 AI 리포트"
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 465


def build_message(
    *,
    subject: str,
    sender_addr: str,
    to: str,
    text: str,
    html: str,
    list_unsubscribe: str | None = None,
    one_click: bool = False,
) -> EmailMessage:
    """D-14: List-Unsubscribe when given; the one-click Post header only with an https target
    (RFC 8058), which the caller signals with one_click."""
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = formataddr((SENDER_NAME, sender_addr))
    msg["To"] = to
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain="gmail.com")
    if list_unsubscribe:
        # Header injection guard: no CR/LF may reach the header.
        msg["List-Unsubscribe"] = list_unsubscribe.replace("\r", "").replace("\n", "")
        if one_click:
            msg["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"
    msg.set_content(text)
    msg.add_alternative(html, subtype="html")
    # policy.default folds a long List-Unsubscribe into RFC 2047 encoded-words, which breaks
    # the URLs for receivers (research Pitfall 3). Body encodings stay as set above.
    msg.policy = msg.policy.clone(max_line_length=998)
    return msg


def build_text_message(*, subject: str, sender_addr: str, to: str, text: str) -> EmailMessage:
    """Plain-text only message (owner failure notice, D-13)."""
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = formataddr((SENDER_NAME, sender_addr))
    msg["To"] = to
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain="gmail.com")
    msg.set_content(text)
    return msg


def send_messages(
    messages: Iterable[EmailMessage], *, user: str, password: str, pause: float = 0.0
) -> int:
    """Send all messages over one SMTP_SSL connection.

    SMTP and socket errors are re-raised as DeliveryError carrying only the class
    name and SMTP code. Their text can hold recipient or sender addresses, so the
    original exception is dropped (DLVR-06).
    """
    sent = 0
    failure: tuple[str, object] | None = None
    try:
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=context, timeout=30) as smtp:
            smtp.login(user, password.replace(" ", ""))
            for i, msg in enumerate(messages):
                if i and pause > 0:
                    time.sleep(pause)
                smtp.send_message(msg)
                sent += 1
    except (smtplib.SMTPException, OSError) as e:
        failure = (type(e).__name__, getattr(e, "smtp_code", None))
    if failure is not None:
        log.info("sent=%d failed=1", sent)
        # Raised outside the except block so no address-bearing context is chained.
        raise DeliveryError(f"{failure[0]} code={failure[1]}") from None
    log.info("sent=%d", sent)
    return sent
