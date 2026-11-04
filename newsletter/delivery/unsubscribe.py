"""Unsubscribe token and list fetch (D-10..D-13).

The token is HMAC-SHA256 over the normalized address, keyed with
UNSUBSCRIBE_TOKEN_SECRET, as the first TOKEN_LEN lowercase hex characters.
apps_script/Code.gs computes the same value (shared test vector
f290b8e448576cf84f63ac2b465c3e65). The scheme and the secret never change:
every sent email carries its token forever. A v2 would need a new parameter
name (t2) with old tokens still honored.

Nothing here logs. Error text carries class names and status codes only,
never the key, the endpoint query, an id or an address.
"""

import hashlib
import hmac
import re

import httpx

from newsletter.errors import DeliveryError

TOKEN_LEN = 32
TOKEN_RE = re.compile(rf"[0-9a-f]{{{TOKEN_LEN}}}")

# The /exec URL of the one Apps Script deployment. Not a secret: it appears in
# every List-Unsubscribe header. Deployed by the owner on 2026-11-04 (04.1-05).
# Change the script only via 배포 관리 → 수정 → 새 버전, never 새 배포 (the URL
# would change and every sent List-Unsubscribe link would break).
UNSUBSCRIBE_ENDPOINT: str | None = (
    "https://script.google.com/macros/s/AKfycbwE-1PysSDJn_tkkinRVATaeCqnsm2wOwFCXy0fSrobig7Sb03AEx-ei0so6ueILzRetw/exec"
)

LIST_TIMEOUT = 20


def token(email: str, secret: str) -> str:
    """Opaque unsubscribe id for one address."""
    norm = email.strip().lower()
    digest = hmac.new(secret.encode("utf-8"), norm.encode("utf-8"), hashlib.sha256)
    return digest.hexdigest()[:TOKEN_LEN]


def fetch_unsubscribed(endpoint: str, key: str, client: httpx.Client | None = None) -> set[str]:
    """Ids recorded in the Sheet. Fails closed: any doubt raises DeliveryError.

    The key goes in the POST body, never the URL. Apps Script answers with a
    302 to a one-time googleusercontent URL, so redirects must be followed.
    """
    own = client is None
    c = client or httpx.Client(timeout=LIST_TIMEOUT)
    try:
        try:
            r = c.post(endpoint, data={"action": "list", "key": key}, follow_redirects=True)
        except httpx.HTTPError as e:
            raise DeliveryError(f"unsubscribe list {type(e).__name__}") from None
        if r.status_code != 200:
            raise DeliveryError(f"unsubscribe list status={r.status_code}")
        try:
            data = r.json()
            ids = {i for i in data["ids"] if isinstance(i, str) and TOKEN_RE.fullmatch(i)}
        except ValueError, KeyError, TypeError:
            raise DeliveryError("unsubscribe list unreadable") from None
        return ids
    finally:
        if own:
            c.close()
