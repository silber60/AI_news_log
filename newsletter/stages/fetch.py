"""HF Papers fetch for one ISO week (D-09).

`week=` paging is the primary path. ISO week 53 and an HTTP 400 on `week=` go to
the `date=` loop over Mon..Sun. Results are deduped by `paper.id` and filtered to
entries whose `submittedOnDailyAt` falls in the week in KST.
"""

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Literal

import httpx
from tenacity import Retrying, retry_if_exception_type, stop_after_attempt, wait_exponential

from newsletter.errors import EmptyFetchError, FetchError
from newsletter.schema import HfEntry
from newsletter.week import KST, parse_week

log = logging.getLogger(__name__)

HF_BASE = "https://huggingface.co"
PAGE_LIMIT = 100
MAX_PAGES = 20
# Exponential backoff base in seconds, read per call so tests can set it to 0.
RETRY_WAIT_MULTIPLIER: float = 1.0
RETRY_WAIT_MAX = 30

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


class _WeekRejected(FetchError):
    """HTTP 400 from HF. On `week=` this switches to the `date=` loop."""


class _RetryableStatus(Exception):
    def __init__(self, status: int):
        super().__init__(status)
        self.status = status


def _get_once(client: httpx.Client, params: dict[str, Any]) -> list[dict]:
    resp = client.get("/api/daily_papers", params=params)
    code = resp.status_code
    if code == 429 or code >= 500:
        raise _RetryableStatus(code)
    if code == 400:
        raise _WeekRejected("HTTP 400")
    if code >= 400:
        raise FetchError(f"HTTP {code}")
    data = resp.json()
    if not isinstance(data, list):
        raise FetchError("unexpected payload shape")
    return data


def _get_page(client: httpx.Client, params: dict[str, Any]) -> list[dict]:
    """One GET with bounded retries on transport errors, 429 and 5xx only.

    Error messages carry the status code or exception class, never response bodies.
    """
    retrying = Retrying(
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=RETRY_WAIT_MULTIPLIER, max=RETRY_WAIT_MAX),
        retry=retry_if_exception_type((httpx.TransportError, _RetryableStatus)),
        reraise=True,
    )
    try:
        return retrying(_get_once, client, params)
    except _RetryableStatus as e:
        raise FetchError(f"HTTP {e.status}") from None
    except httpx.TransportError as e:
        raise FetchError(type(e).__name__) from e


def _page_all(client: httpx.Client, params: dict[str, Any]) -> tuple[list[dict], int]:
    """Page one query (limit 100) until a short page, capped at MAX_PAGES."""
    out: list[dict] = []
    pages = 0
    for p in range(MAX_PAGES):
        page = _get_page(client, {**params, "limit": PAGE_LIMIT, "p": p})
        pages += 1
        out.extend(page)
        if len(page) < PAGE_LIMIT:
            break
    return out, pages


def fetch_by_dates(mon: date, sun: date, client: httpx.Client) -> tuple[list[dict], int]:
    """Query `date=` for every day Mon..Sun (weekends included). Returns (entries, pages)."""
    out: list[dict] = []
    pages = 0
    day = mon
    while day <= sun:
        got, n = _page_all(client, {"date": day.isoformat()})
        out.extend(got)
        pages += n
        day += timedelta(days=1)
    return out, pages


def _kst_day(entry: dict) -> date | None:
    s = (entry.get("paper") or {}).get("submittedOnDailyAt")
    if not isinstance(s, str):
        return None
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    if dt.tzinfo is None:
        return None
    return dt.astimezone(KST).date()


def _dedupe_in_week(entries: list[dict], mon: date, sun: date) -> list[dict]:
    """Dedupe by paper.id (first wins), keep entries whose KST daily date is in Mon..Sun."""
    seen: dict[str, dict] = {}
    for d in entries:
        pid = (d.get("paper") or {}).get("id")
        if pid and pid not in seen:
            seen[pid] = d
    return [d for d in seen.values() if (k := _kst_day(d)) is not None and mon <= k <= sun]


def fetch_week(issue_id: str, *, client: httpx.Client | None = None) -> FetchResult:
    mon, sun = parse_week(issue_id)
    week_no = int(issue_id.rsplit("W", 1)[1])
    own = client is None
    if own:
        client = httpx.Client(base_url=HF_BASE, timeout=30)
    try:
        merged: list[dict] | None = None
        method: Literal["week", "date"] = "date"
        pages = 0
        if week_no <= 52:
            try:
                merged, pages = _page_all(client, {"week": issue_id})
                method = "week"
            except _WeekRejected:
                pages += 1
                merged = None
        if merged is None:
            merged, n = fetch_by_dates(mon, sun, client)
            pages += n
            method = "date"
    finally:
        if own:
            client.close()

    kept = _dedupe_in_week(merged, mon, sun)
    log.info("method=%s pages=%d fetched=%d kept=%d", method, pages, len(merged), len(kept))
    if not kept:
        raise EmptyFetchError(f"no papers for {issue_id}")
    raw = [trim_entry(d) for d in kept]
    entries = [HfEntry.model_validate(d) for d in raw]
    return FetchResult(entries=entries, raw=raw, method=method)
