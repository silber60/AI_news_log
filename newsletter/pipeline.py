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

from pydantic import BaseModel, ConfigDict, TypeAdapter

from newsletter import store, topics
from newsletter.schema import Explainer, HfEntry, Highlight, Issue, Item
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
_TREND = TypeAdapter(str | None)
_HIGHLIGHTS = TypeAdapter(list[Highlight])
_EXPLAINER = TypeAdapter(Explainer | None)
_HEADLINE = TypeAdapter(str)


class _Enriched(BaseModel):
    """enrich checkpoint: items before verdicts.finalize plus the EVID-01 records."""

    model_config = ConfigDict(extra="forbid")
    items: list[Item]
    records: list[dict[str, Any]]


_ENRICHED = TypeAdapter(_Enriched)
_NO_FORCE = (None, "", "none")


def _force_index(force_stage: str | None) -> int | None:
    if force_stage in _NO_FORCE:
        return None
    if force_stage not in STAGES:
        raise ValueError(f"unknown force_stage: {force_stage!r}")
    return STAGES.index(force_stage)


class _Checkpoints:
    """Per-build reuse state. A stage loads its checkpoint unless it is at or after the
    forced stage or an earlier stage was recomputed (the cascade)."""

    def __init__(self, issue_id: str, force_stage: str | None):
        self.issue_id = issue_id
        self.force_from = _force_index(force_stage)
        self.cascade = False

    def _reusable(self, stage: str) -> bool:
        if self.force_from is not None and STAGES.index(stage) >= self.force_from:
            self.cascade = True
        return not self.cascade

    def step(
        self,
        stage: str,
        load: Callable[[], tuple[bool, Any]],
        compute: Callable[[], Any],
        save: Callable[[Any], None],
    ) -> Any:
        if self._reusable(stage):
            ok, data = load()
            if ok:
                log.info("checkpoint=%s reused", stage)
                return data
            self.cascade = True
        data = compute()
        save(data)  # right after success, so a later crash keeps this stage
        log.info("checkpoint=%s computed", stage)
        return data

    def run(self, stage: str, adapter: TypeAdapter, compute: Callable[[], Any]) -> Any:
        return self.step(
            stage,
            lambda: self._load(stage, adapter),
            compute,
            lambda data: self._save(stage, data),
        )

    def _load(self, stage: str, adapter: TypeAdapter) -> tuple[bool, Any]:
        """(True, payload) for a valid checkpoint, else (False, None). Never raises."""
        path = store.checkpoint_path(self.issue_id, stage)
        if not path.is_file():
            return False, None
        try:
            doc = store.read_json(path)
            if not isinstance(doc, dict) or "data" not in doc:
                raise _Invalid("shape")
            if doc.get("version") != store.CHECKPOINT_VERSION:
                raise _Invalid("version")
            if doc.get("issue_id") != self.issue_id or doc.get("stage") != stage:
                raise _Invalid("issue_id")
            return True, adapter.validate_python(doc["data"])
        except _Invalid as e:
            _log_invalid(stage, str(e))
        except (OSError, ValueError) as e:
            _log_invalid(stage, type(e).__name__)
        return False, None

    def _save(self, stage: str, data: Any) -> None:
        store.write_json_atomic(
            store.checkpoint_path(self.issue_id, stage),
            {
                "version": store.CHECKPOINT_VERSION,
                "issue_id": self.issue_id,
                "stage": stage,
                "data": data,
            },
        )


class _Invalid(Exception):
    pass


def _log_invalid(stage: str, why: str) -> None:
    log.warning("checkpoint=%s invalid reason=%s", stage, why)


def _load_fetch(issue_id: str) -> tuple[bool, fetch.FetchResult | None]:
    """raw.json is the fetch checkpoint; its public shape is unchanged."""
    path = store.week_dir(issue_id) / "raw.json"
    if not path.is_file():
        return False, None
    try:
        doc = store.read_json(path)
        if not isinstance(doc, dict) or doc.get("issue_id") != issue_id:
            raise _Invalid("issue_id")
        method = doc.get("method")
        if method not in ("week", "date"):
            raise _Invalid("method")
        raw = doc.get("entries")
        if not isinstance(raw, list) or not raw:
            raise _Invalid("entries")
        entries = _ENTRIES.validate_python(raw)
        fetched_at = datetime.fromisoformat(doc["fetched_at"])
        if fetched_at.tzinfo is None:
            raise _Invalid("fetched_at")
    except _Invalid as e:
        _log_invalid("fetch", str(e))
        return False, None
    except (OSError, ValueError, KeyError, TypeError) as e:
        _log_invalid("fetch", type(e).__name__)
        return False, None
    return True, fetch.FetchResult(entries=entries, raw=raw, method=method, fetched_at=fetched_at)


def _save_fetch(issue_id: str, fetched: fetch.FetchResult) -> None:
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


def _load_issue(issue_id: str) -> tuple[bool, Issue | None]:
    """issue.json is the polish checkpoint."""
    path = store.week_dir(issue_id) / "issue.json"
    if not path.is_file():
        return False, None
    try:
        issue = Issue.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        _log_invalid("polish", type(e).__name__)
        return False, None
    if issue.issue_id != issue_id:
        _log_invalid("polish", "issue_id")
        return False, None
    return True, issue


def _write_selected(out, issue_id: str, fetched: fetch.FetchResult, top: list[HfEntry]) -> None:
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


def run_build(
    issue_id: str, *, http_client=None, claude_client=None, force_stage: str | None = None
) -> Issue:
    """Build one week. force_stage (a STAGES name) recomputes that stage and every later
    one; None, "" or "none" reuses every valid checkpoint."""
    week_start, week_end = parse_week(issue_id)
    out = store.week_dir(issue_id)
    cp = _Checkpoints(issue_id, force_stage)
    clients: list = [] if claude_client is None else [claude_client]

    def claude():
        # Lazy: a build that reuses every Claude stage never creates a client.
        if not clients:
            clients.append(analyze.make_client())
        return clients[0]

    fetched = cp.step(
        "fetch",
        lambda: _load_fetch(issue_id),
        lambda: fetch.fetch_week(issue_id, client=http_client),
        lambda f: _save_fetch(issue_id, f),
    )
    top = select.select_top(fetched.entries)
    _write_selected(out, issue_id, fetched, top)
    log.info("fetched=%d selected=%d", len(fetched.entries), len(top))

    items = cp.run("analyze", _ITEMS, lambda: analyze.analyze_items(top, claude()))

    def _enrich() -> _Enriched:
        got, records = enrich.enrich_items_with_records(items, top, client=http_client)
        return _Enriched(items=got, records=records)

    enriched = cp.run("enrich", _ENRICHED, _enrich)
    records = enriched.records
    # EVID-01: public HF/GitHub evidence behind the verdicts, no Claude text.
    store.write_json(
        out / "enriched.json", {"issue_id": issue_id, "count": len(records), "items": records}
    )
    items = verdicts.finalize(enriched.items)
    # ANLY-04, D-14: reasons are written after finalize, so a downgraded verdict
    # gets the fixed code reason, never a Claude one. Both calls are non-fatal.
    items = cp.run("notes", _ITEMS, lambda: notes.write_notes(items, claude()))
    # ANLY-05, D-07: None on failure, and None is a valid checkpoint.
    trend_ko = cp.run("trend", _TREND, lambda: trend.write_trend(items, claude()))
    # HILT-02/03, D-02: 0-3 picks from the Skill/GPTs candidates; [] on failure.
    highlights = cp.run(
        "highlight", _HIGHLIGHTS, lambda: highlight.write_highlights(items, claude())
    )
    # EXPL-01/02, D-05, D-06: reads the committed topic record, never writes it; None on failure.
    explainer_ = cp.run(
        "explainer",
        _EXPLAINER,
        lambda: explainer.write_explainer(items, topics.load_past(), claude()),
    )
    headline_ko = cp.run("headline", _HEADLINE, lambda: headline.write_headline(items, claude()))

    def _polish() -> Issue:
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
            headline_ko=headline_ko,
        )
        # HUMN-03, D-08: lint-gated polish of Claude free text; 0 calls when clean.
        return humanize.polish_issue(issue, claude())

    issue = cp.step(
        "polish",
        lambda: _load_issue(issue_id),
        _polish,
        lambda i: store.write_json_atomic(out / "issue.json", i),
    )
    store.write_text(out / "email.html", render.render_html(issue, PREVIEW_GREETING))
    store.write_text(out / "email.txt", render.render_text(issue, PREVIEW_GREETING))
    store.write_current(issue_id)
    log.info("built issue=%s items=%d", issue_id, len(issue.items))
    return issue
