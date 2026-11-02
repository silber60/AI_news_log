"""Subscriber list parsing and greeting normalization (DLVR-01, DLVR-02).

The list arrives only through the SUBSCRIBERS_CSV secret. Nothing in this module
logs or raises with row content: errors carry counts only (DLVR-06).
"""

import csv
import io
from dataclasses import dataclass

from newsletter.errors import NoSubscribersError

BOM = "﻿"
DEFAULT_GREETING = "구독자님"


@dataclass(frozen=True)
class Subscriber:
    email: str
    name: str = ""


def parse_subscribers(text: str) -> tuple[list[Subscriber], int]:
    """Return (subscribers, skipped_rows). Raise NoSubscribersError on zero valid rows."""
    text = (text or "").lstrip(BOM)
    reader = csv.DictReader(io.StringIO(text))
    headers = [(h or "").strip().lstrip(BOM).strip().lower() for h in (reader.fieldnames or [])]
    if "email" not in headers:
        raise NoSubscribersError("subscriber list has no email column")
    reader.fieldnames = headers

    subscribers: list[Subscriber] = []
    skipped = 0
    for row in reader:
        email = (row.get("email") or "").strip()
        name = (row.get("name") or "").strip()
        if not email or "@" not in email:
            skipped += 1
            continue
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
