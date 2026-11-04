"""Live subscriber list from the Apps Script action=members route (D-08).

The weekly send reads the active rows of the Sheet here once the endpoint is set,
instead of the SUBSCRIBERS_CSV secret. It fails closed: any transport error,
status, shape or version problem raises DeliveryError, and zero valid rows raise
NoSubscribersError, so nobody is mailed on doubt.

Nothing here logs. Error text carries class names and status codes only, never
the key, the endpoint query, a name or an address.
"""

import httpx

from newsletter.delivery import unsubscribe
from newsletter.delivery.subscribers import Subscriber, _valid_email
from newsletter.errors import DeliveryError, NoSubscribersError

VERSION = 1


def _rows(data: object) -> list:
    if not isinstance(data, dict) or data.get("version") != VERSION:
        raise DeliveryError("subscriber list unreadable")
    rows = data.get("subscribers")
    if not isinstance(rows, list):
        raise DeliveryError("subscriber list unreadable")
    return rows


def fetch_subscribers(
    endpoint: str, key: str, client: httpx.Client | None = None
) -> tuple[list[Subscriber], int]:
    """(subscribers, skipped_rows) from the Sheet, deduplicated by trim().lower().

    The key goes in the POST body, never the URL. Apps Script answers with a 302
    to a one-time googleusercontent URL, so redirects must be followed. Rows that
    are not objects, carry an invalid address or repeat an address count as skipped.
    """
    own = client is None
    c = client or httpx.Client(timeout=unsubscribe.LIST_TIMEOUT)
    try:
        try:
            r = c.post(endpoint, data={"action": "members", "key": key}, follow_redirects=True)
        except httpx.HTTPError as e:
            raise DeliveryError(f"subscriber list {type(e).__name__}") from None
        if r.status_code != 200:
            raise DeliveryError(f"subscriber list status={r.status_code}")
        try:
            data = r.json()
        except ValueError:
            raise DeliveryError("subscriber list unreadable") from None
        rows = _rows(data)
    finally:
        if own:
            c.close()

    subscribers: list[Subscriber] = []
    seen: set[str] = set()
    skipped = 0
    for row in rows:
        raw = row.get("email") if isinstance(row, dict) else None
        email = raw.strip() if isinstance(raw, str) else ""
        norm = email.lower()
        if not _valid_email(email) or norm in seen:
            skipped += 1
            continue
        seen.add(norm)
        name = row.get("name")
        subscribers.append(
            Subscriber(email=email, name=name.strip() if isinstance(name, str) else "")
        )
    if not subscribers:
        raise NoSubscribersError(f"no valid subscribers (skipped={skipped})")
    return subscribers, skipped
