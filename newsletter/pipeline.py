"""Build stage: week -> fetch -> select -> analyze -> enrich -> verdicts -> Issue -> render -> archive."""

import logging
from datetime import datetime

from newsletter import store
from newsletter.schema import Issue
from newsletter.stages import analyze, enrich, fetch, headline, render, select, verdicts
from newsletter.week import KST, parse_week

log = logging.getLogger(__name__)

PREVIEW_GREETING = "구독자님"  # D-14: de-personalized preview


def run_build(issue_id: str, *, http_client=None, claude_client=None) -> Issue:
    week_start, week_end = parse_week(issue_id)
    out = store.week_dir(issue_id)

    fetched = fetch.fetch_week(issue_id, client=http_client)
    store.write_json(
        out / "raw.json",
        {
            "issue_id": issue_id,
            "fetched_at": fetched.fetched_at.isoformat(),
            "method": fetched.method,
            "count": len(fetched.raw),
            "entries": fetched.raw,
        },
    )

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

    client = claude_client if claude_client is not None else analyze.make_client()
    items = analyze.analyze_items(top, client)
    items, records = enrich.enrich_items_with_records(items, top, client=http_client)
    # EVID-01: public HF/GitHub evidence behind the verdicts, no Claude text.
    store.write_json(
        out / "enriched.json", {"issue_id": issue_id, "count": len(records), "items": records}
    )
    items = verdicts.finalize(items)

    issue = Issue(
        issue_id=issue_id,
        week_start=week_start,
        week_end=week_end,
        generated_at=datetime.now(KST),
        model=analyze.model_name(),
        fetch_method=fetched.method,
        items=items,
        headline_ko=headline.write_headline(items, client),
    )
    store.write_json(out / "issue.json", issue)
    store.write_text(out / "email.html", render.render_html(issue, PREVIEW_GREETING))
    store.write_text(out / "email.txt", render.render_text(issue, PREVIEW_GREETING))
    store.write_current(issue_id)
    log.info("built issue=%s items=%d", issue_id, len(items))
    return issue
