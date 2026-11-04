"""Send ledger (DLVR-05, D-05 as amended by the owner, research A1).

data/ledger/<YYYY-Www>.json records who already got that week's issue, so a
re-run never mails the same person twice. Each entry is
HMAC-SHA256(unsubscribe token secret, "ledger-v1:" + normalized email) as 64
hex characters; deliver passes the secret in. The key is secret-keyed so
nobody can test a guessed address against the public repo, and the
"ledger-v1:" prefix keeps it apart from the unsubscribe token for the same
address.

The file holds no address, name or timestamp; keys are sorted so the order of
sending does not show. Nothing here logs.
"""

import hashlib
import hmac
import json
import os
from collections.abc import Iterable
from pathlib import Path

from newsletter import store
from newsletter.errors import DeliveryError

LEDGER_SCHEME = "hmac-sha256-ledger-v1"
LEDGER_VERSION = 1


def ledger_dir() -> Path:
    env = os.environ.get("NEWSLETTER_LEDGER_DIR")
    return Path(env) if env else store.REPO_ROOT / "data" / "ledger"


def _path(issue_id: str) -> Path:
    return ledger_dir() / f"{issue_id}.json"


def key(email: str, secret: str) -> str:
    """Ledger key for one address (same normalization as unsubscribe.token)."""
    norm = email.strip().lower()
    digest = hmac.new(secret.encode("utf-8"), b"ledger-v1:" + norm.encode("utf-8"), hashlib.sha256)
    return digest.hexdigest()


def load(issue_id: str) -> set[str]:
    """Keys already mailed for this issue. A missing file is an empty ledger. A file for
    another issue or scheme raises DeliveryError, so a mixed-up ledger never allows a resend."""
    path = _path(issue_id)
    if not path.exists():
        return set()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        ok = (
            data["version"] == LEDGER_VERSION
            and data["issue_id"] == issue_id
            and data["scheme"] == LEDGER_SCHEME
            and isinstance(data["sent"], list)
            and all(isinstance(k, str) for k in data["sent"])
        )
    except ValueError, KeyError, TypeError:
        raise DeliveryError("ledger unreadable") from None
    if not ok:
        raise DeliveryError("ledger mismatch")
    return set(data["sent"])


def _write_atomic(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def save(issue_id: str, keys: Iterable[str]) -> None:
    _write_atomic(
        _path(issue_id),
        {
            "version": LEDGER_VERSION,
            "issue_id": issue_id,
            "scheme": LEDGER_SCHEME,
            "sent": sorted(set(keys)),
        },
    )
