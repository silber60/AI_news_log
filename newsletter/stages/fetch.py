"""HF Papers fetch (tracer path: `week=` pagination only).

Plan 02 adds the `date=` fallback, retries and the KST filter behind the same
signature.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

import httpx

from newsletter.errors import EmptyFetchError, FetchError
from newsletter.schema import HfEntry
from newsletter.week import KST

log = logging.getLogger(__name__)

HF_BASE = "https://huggingface.co"
PAGE_LIMIT = 100
MAX_PAGES = 20

_PAPER_KEYS = (
    "id",
    "title",
    "summary",
    "upvotes",
    "publishedAt",
    "submittedOnDailyAt",
    "ai_summary",
    "ai_keywords",
    "githubRepo",
    "githubStars",
    "projectPage",
)


@dataclass
class FetchResult:
    entries: list[HfEntry]
    raw: list[dict]
    method: Literal["week", "date"]
    fetched_at: datetime = field(default_factory=lambda: datetime.now(KST))


def trim_entry(d: dict[str, Any]) -> dict[str, Any]:
    """Keep only the keys the pipeline reads. Drops authors / submittedBy profile data."""
    paper = d.get("paper") or {}
    out: dict[str, Any] = {"paper": {k: paper[k] for k in _PAPER_KEYS if k in paper}}
    for k in ("title", "numComments"):
        if k in d:
            out[k] = d[k]
    org = d.get("organization")
    if isinstance(org, dict):
        out["organization"] = {k: org[k] for k in ("name", "fullname") if k in org}
    return out


def _get_page(client: httpx.Client, params: dict[str, Any]) -> list[dict]:
    try:
        resp = client.get("/api/daily_papers", params=params)
        resp.raise_for_status()
    except httpx.HTTPError as e:
        raise FetchError(type(e).__name__) from e
    data = resp.json()
    if not isinstance(data, list):
        raise FetchError("unexpected payload shape")
    return data


def fetch_week(issue_id: str, *, client: httpx.Client | None = None) -> FetchResult:
    own = client is None
    if own:
        client = httpx.Client(base_url=HF_BASE, timeout=30)
    try:
        seen: dict[str, dict] = {}
        for p in range(MAX_PAGES):
            page = _get_page(client, {"week": issue_id, "limit": PAGE_LIMIT, "p": p})
            for d in page:
                pid = (d.get("paper") or {}).get("id")
                if pid and pid not in seen:
                    seen[pid] = trim_entry(d)
            if len(page) < PAGE_LIMIT:
                break
    finally:
        if own:
            client.close()

    raw = list(seen.values())
    if not raw:
        raise EmptyFetchError(f"no papers for {issue_id}")
    entries = [HfEntry.model_validate(d) for d in raw]
    log.info("fetched=%d method=week", len(entries))
    return FetchResult(entries=entries, raw=raw, method="week")
