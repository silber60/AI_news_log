"""Build and send email messages over Gmail SMTP (SSL, port 465).

Never enable SMTP debug output: it would print addresses and credentials to the
public Actions log.
"""

import logging
import smtplib
import ssl
from collections.abc import Iterable
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid

log = logging.getLogger(__name__)

SENDER_NAME = "AI 주간 모델 브리프"
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 465


def build_message(*, subject: str, sender_addr: str, to: str, text: str, html: str) -> EmailMessage:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = formataddr((SENDER_NAME, sender_addr))
    msg["To"] = to
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain="gmail.com")
    msg.set_content(text)
    msg.add_alternative(html, subtype="html")
    return msg


def send_messages(messages: Iterable[EmailMessage], *, user: str, password: str) -> int:
    sent = 0
    context = ssl.create_default_context()
    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=context, timeout=30) as smtp:
        smtp.login(user, password.replace(" ", ""))
        for msg in messages:
            smtp.send_message(msg)
            sent += 1
    log.info("sent=%d", sent)
    return sent
