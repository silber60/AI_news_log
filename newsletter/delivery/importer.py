"""One-time import of the SUBSCRIBERS_CSV readers into the Sheet (D-06).

The owner runs the import-subscribers workflow once after the cut-over. Rows are
parsed with parse_subscribers and posted to Apps Script action=import in batches
of at most BATCH rows, with SUBSCRIBE_ADMIN_KEY in the POST body. Apps Script
lets an earlier opt-out win and sends no mail, so a re-run is idempotent. This
module and its workflow are removed again in 04.1-06.

Nothing here logs. Error text carries class names and status codes only, never
the key, the endpoint query, a name or an address.
"""

import json

import httpx

from newsletter.delivery import unsubscribe
from newsletter.delivery.deliver import _env
from newsletter.delivery.subscribers import parse_subscribers
from newsletter.errors import DeliveryError

BATCH = 25
VERSION = 1
COUNTS = ("added", "existing", "unsubscribed", "skipped")


def _counts(r: httpx.Response) -> dict[str, int]:
    if r.status_code != 200:
        raise DeliveryError(f"import status={r.status_code}")
    try:
        data = r.json()
    except ValueError:
        raise DeliveryError("import unreadable") from None
    if not isinstance(data, dict) or data.get("version") != VERSION:
        raise DeliveryError("import unreadable")
    out = {}
    for name in COUNTS:
        value = data.get(name)
        if type(value) is not int or value < 0:
            raise DeliveryError("import unreadable")
        out[name] = value
    return out


def import_subscribers(
    endpoint: str, key: str, csv_text: str, client: httpx.Client | None = None
) -> dict[str, int]:
    """Post every valid CSV row; return the summed counts.

    Keys: rows (valid CSV rows sent), added, existing, unsubscribed, skipped (rows
    Apps Script rejected) and skipped_rows (CSV rows parse_subscribers dropped).
    """
    subscribers, skipped_rows = parse_subscribers(csv_text)
    totals = dict.fromkeys(COUNTS, 0)
    own = client is None
    c = client or httpx.Client(timeout=unsubscribe.LIST_TIMEOUT)
    try:
        for start in range(0, len(subscribers), BATCH):
            batch = subscribers[start : start + BATCH]
            rows = json.dumps(
                [{"email": s.email, "name": s.name} for s in batch], ensure_ascii=False
            )
            try:
                r = c.post(
                    endpoint,
                    data={"action": "import", "key": key, "rows": rows},
                    follow_redirects=True,
                )
            except httpx.HTTPError as e:
                raise DeliveryError(f"import {type(e).__name__}") from None
            for name, value in _counts(r).items():
                totals[name] += value
    finally:
        if own:
            c.close()
    return {"rows": len(subscribers), **totals, "skipped_rows": skipped_rows}


def run_import() -> dict[str, int]:
    """The CLI entry: endpoint check and env reads first, so nothing posts on doubt."""
    endpoint = unsubscribe.UNSUBSCRIBE_ENDPOINT
    if endpoint is None:
        raise DeliveryError("unsubscribe endpoint not set")
    key = _env("SUBSCRIBE_ADMIN_KEY")
    return import_subscribers(endpoint, key, _env("SUBSCRIBERS_CSV"))
