"""Subscriber list parsing and greeting normalization (DLVR-01, DLVR-02).

The list arrives only through the SUBSCRIBERS_CSV secret, either as pasted CSV
text or as base64 of a CSV file (UTF-8, UTF-8 with BOM, or CP949). Nothing in this
module logs or raises with row content: errors carry counts only (DLVR-06).
"""

import base64
import csv
import io
import re
from dataclasses import dataclass
from email.utils import parseaddr

from newsletter.errors import NoSubscribersError

BOM = "﻿"
DEFAULT_GREETING = "구독자님"

_BASE64_RE = re.compile(r"[A-Za-z0-9+/=\s]+")
_EMAIL_RE = re.compile(r"[^@\s,;<>\"']+@[^@\s,;<>\"']+\.[^@\s,;<>\"']+")


@dataclass(frozen=True)
class Subscriber:
    email: str
    name: str = ""


def _maybe_base64(text: str) -> str:
    """Decode a base64-encoded CSV file; return the input unchanged if it is not one."""
    compact = "".join(text.split())
    if not compact or "," in text or not _BASE64_RE.fullmatch(text):
        return text
    try:
        raw = base64.b64decode(compact, validate=True)
    except ValueError:  # binascii.Error subclasses ValueError
        return text
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        pass
    try:
        return raw.decode("cp949")
    except UnicodeDecodeError:
        return text


def _valid_email(email: str) -> bool:
    return bool(_EMAIL_RE.fullmatch(email)) and parseaddr(email)[1] == email


def parse_subscribers(text: str) -> tuple[list[Subscriber], int]:
    """Return (subscribers, skipped_rows). Raise NoSubscribersError on zero valid rows.

    Invalid emails and duplicates (case-insensitive) count as skipped rows.
    """
    text = _maybe_base64((text or "").strip().lstrip(BOM)).lstrip(BOM)
    reader = csv.DictReader(io.StringIO(text))
    headers = [(h or "").strip().lstrip(BOM).strip().lower() for h in (reader.fieldnames or [])]
    if "email" not in headers:
        raise NoSubscribersError("subscriber list has no email column")
    reader.fieldnames = headers

    subscribers: list[Subscriber] = []
    seen: set[str] = set()
    skipped = 0
    for row in reader:
        email = (row.get("email") or "").strip()
        name = (row.get("name") or "").strip()
        key = email.lower()
        if not _valid_email(email) or key in seen:
            skipped += 1
            continue
        seen.add(key)
        subscribers.append(Subscriber(email=email, name=name))
    if not subscribers:
        raise NoSubscribersError(f"no valid subscribers (skipped={skipped})")
    return subscribers, skipped


def load_subscribers(text: str) -> list[Subscriber]:
    return parse_subscribers(text)[0]


def display_name(raw: str | None) -> str:
    """'<name>님' with control characters removed; '구독자님' when empty."""
    n = "".join(ch for ch in (raw or "") if ch.isprintable()).strip()
    n = n.removesuffix("님").strip()
    return f"{n}님" if n else DEFAULT_GREETING
