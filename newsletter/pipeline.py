"""Build stage: week -> fetch -> select -> analyze -> enrich -> verdicts -> notes -> trend
-> highlight -> explainer -> headline -> Issue -> polish -> render -> archive.

The polish pass (HUMN-03, D-13) runs on the assembled Issue before anything is
written, so issue.json, email.html and email.txt all carry the same text.

D-04, AUTO-05: every paid stage stores its output in archive/<week>/ right after it
succeeds (raw.json for fetch, issue.json for polish, checkpoints/<stage>.json for the
rest). A re-run reuses a valid checkpoint, so it makes no HF fetch and no Claude call.
Once one stage is recomputed (forced, missing or invalid file) every later stage is
recomputed too. select, verdicts.finalize and render are code and always re-run."""

import logging
from collections.abc import Callable
from datetime import datetime
from typing import Any

from pydantic import TypeAdapter

from newsletter import store, topics
from newsletter.schema import HfEntry, Issue, Item
from newsletter.stages import (
    analyze,
    enrich,
    explainer,
    fetch,
    headline,
    highlight,
    humanize,
    notes,
    render,
    select,
    trend,
    verdicts,
)
from newsletter.week import KST, parse_week

log = logging.getLogger(__name__)

PREVIEW_GREETING = "구독자님"  # D-14: de-personalized preview

# D-04: paid stages in run order. --force-stage X recomputes X and everything after it.
STAGES = (
    "fetch",
    "analyze",
    "enrich",
    "notes",
    "trend",
    "highlight",
    "explainer",
    "headline",
    "polish",
)

_ITEMS = TypeAdapter(list[Item])
_ENTRIES = TypeAdapter(list[HfEntry])


class _Checkpoints:
    """Per-build reuse state: which stages may load, and the cascade once one recomputes."""

    def __init__(self, issue_id: str):
        self.issue_id = issue_id
        self.cascade = False

    def _invalid(self, stage: str, why: str) -> None:
        log.warning("checkpoint=%s invalid reason=%s", stage, why)

    def load(self, stage: str, adapter: TypeAdapter) -> tuple[bool, Any]:
        """(True, payload) for a valid checkpoint, else (False, None). Never raises."""
        path = store.checkpoint_path(self.issue_id, stage)
        if not path.is_file():
            return False, None
        try:
            doc = store.read_json(path)
        except (OSError, ValueError) as e:
            self._invalid(stage, type(e).__name__)
            return False, None
        if not isinstance(doc, dict) or "data" not in doc:
            self._invalid(stage, "shape")
            return False, None
        if doc.get("version") != store.CHECKPOINT_VERSION:
            self._invalid(stage, "version")
            return False, None
        if doc.get("issue_id") != self.issue_id or doc.get("stage") != stage:
            self._invalid(stage, "issue_id")
            return False, None
        try:
            return True, adapter.validate_python(doc["data"])
        except ValueError as e:
            self._invalid(stage, type(e).__name__)
            return False, None

    def save(self, stage: str, data: Any) -> None:
        store.write_json_atomic(
            store.checkpoint_path(self.issue_id, stage),
            {
                "version": store.CHECKPOINT_VERSION,
                "issue_id": self.issue_id,
                "stage": stage,
                "data": data,
            },
        )

    def run(self, stage: str, adapter: TypeAdapter, compute: Callable[[], Any]) -> Any:
        if not self.cascade:
            ok, data = self.load(stage, adapter)
            if ok:
                log.info("checkpoint=%s reused", stage)
                return data
            self.cascade = True
        data = compute()
        self.save(stage, data)
        log.info("checkpoint=%s computed", stage)
        return data


def _load_fetch(issue_id: str) -> fetch.FetchResult | None:
    """raw.json is the fetch checkpoint (its public shape is unchanged)."""
    path = store.week_dir(issue_id) / "raw.json"
    if not path.is_file():
        return None
    try:
        doc = store.read_json(path)
        if not isinstance(doc, dict) or doc.get("issue_id") != issue_id:
            raise ValueError("issue_id")
        method = doc["method"]
        if method not in ("week", "date"):
            raise ValueError("method")
        raw = doc["entries"]
        if not isinstance(raw, list) or not raw:
            raise ValueError("entries")
        entries = _ENTRIES.validate_python(raw)
        fetched_at = datetime.fromisoformat(doc["fetched_at"])
    except (OSError, ValueError, KeyError, TypeError) as e:
        log.warning("checkpoint=fetch invalid reason=%s", type(e).__name__)
        return None
    return fetch.FetchResult(entries=entries, raw=raw, method=method, fetched_at=fetched_at)


def _fetch(cp: _Checkpoints, issue_id: str, http_client) -> fetch.FetchResult:
    if not cp.cascade:
        fetched = _load_fetch(issue_id)
        if fetched is not None:
            log.info("checkpoint=fetch reused")
            return fetched
        cp.cascade = True
    fetched = fetch.fetch_week(issue_id, client=http_client)
    store.write_json_atomic(
        store.week_dir(issue_id) / "raw.json",
        {
            "issue_id": issue_id,
            "fetched_at": fetched.fetched_at.isoformat(),
            "method": fetched.method,
            "count": len(fetched.raw),
            "entries": fetched.raw,
        },
    )
    log.info("checkpoint=fetch computed")
    return fetched


def run_build(issue_id: str, *, http_client=None, claude_client=None) -> Issue:
    week_start, week_end = parse_week(issue_id)
    out = store.week_dir(issue_id)
    cp = _Checkpoints(issue_id)
    clients: list = [] if claude_client is None else [claude_client]

    def claude():
        # Lazy: a build that reuses every Claude stage never creates a client.
        if not clients:
            clients.append(analyze.make_client())
        return clients[0]

    fetched = _fetch(cp, issue_id, http_client)

    top = select.select_top(fetched.entries)
    raw_by_id = {d["paper"]["id"]: d for d in fetched.raw}
    store.write_json(
        out / "selected.json",
        {
            "issue_id": issue_id,
            "count": len(top),
            "items": [
                {
                    "rank": i + 1,
                    "paper_id": e.paper.id,
                    "upvotes": e.paper.upvotes,
                    "numComments": e.numComments,
                    "submittedOnDailyAt": e.paper.submittedOnDailyAt.isoformat(),
                    "github_stars": select.stars(e) if select.has_repo(e) else None,
                    "basis": "stars" if select.has_repo(e) else "upvotes",
                    "entry": raw_by_id[e.paper.id],
                }
                for i, e in enumerate(top)
            ],
        },
    )
    log.info("fetched=%d selected=%d", len(fetched.entries), len(top))

    items = cp.run("analyze", _ITEMS, lambda: analyze.analyze_items(top, claude()))
    client = claude()
    items, records = enrich.enrich_items_with_records(items, top, client=http_client)
    # EVID-01: public HF/GitHub evidence behind the verdicts, no Claude text.
    store.write_json(
        out / "enriched.json", {"issue_id": issue_id, "count": len(records), "items": records}
    )
    items = verdicts.finalize(items)
    # ANLY-04, D-14: reasons are written after finalize, so a downgraded verdict
    # gets the fixed code reason, never a Claude one. Both calls are non-fatal.
    items = notes.write_notes(items, client)
    trend_ko = trend.write_trend(items, client)  # ANLY-05, D-07: None on failure
    # HILT-02/03, D-02: 0-3 picks from the Skill/GPTs candidates; [] on failure.
    highlights = highlight.write_highlights(items, client)
    # EXPL-01/02, D-05, D-06: reads the committed topic record, never writes it; None on failure.
    explainer_ = explainer.write_explainer(items, topics.load_past(), client)

    issue = Issue(
        issue_id=issue_id,
        week_start=week_start,
        week_end=week_end,
        generated_at=datetime.now(KST),
        model=analyze.model_name(),
        fetch_method=fetched.method,
        items=items,
        trend_ko=trend_ko,
        highlights=highlights,
        explainer=explainer_,
        headline_ko=headline.write_headline(items, client),
    )
    # HUMN-03, D-08: lint-gated polish of Claude free text; 0 calls when clean.
    issue = humanize.polish_issue(issue, client)
    store.write_json(out / "issue.json", issue)
    store.write_text(out / "email.html", render.render_html(issue, PREVIEW_GREETING))
    store.write_text(out / "email.txt", render.render_text(issue, PREVIEW_GREETING))
    store.write_current(issue_id)
    log.info("built issue=%s items=%d", issue_id, len(items))
    return issue
