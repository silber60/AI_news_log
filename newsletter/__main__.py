"""CLI: `python -m newsletter build --week YYYY-Www [--force-stage STAGE]`,
`deliver --mode test|send [--allow-stale]`, `report --mode test|send` (alias
`notify-failure`),
`record-topic --mode preview|test|send`, `publish --mode preview|test|send`, `site`,
`import-subscribers`.

`build` reuses the per-stage checkpoints in archive/<week>/ (D-04), so a re-run makes
no HF fetch and no Claude call. `--force-stage STAGE` recomputes that stage and every
later one; blank or `none` reuses everything.

`deliver --mode send` refuses an issue outside its KST send day (the Monday after
the issue week) with StaleIssueError, before any secret or network use, unless
`--allow-stale` is given on purpose (D-03). A paused scheduled send (SEND_PAUSED)
reports `paused` and mails nobody (D-02).

`report` mails the owner the weekly run report (D-06): sent with counts, paused,
refused as stale, or failed with stage and class. It reads out/report.json and
out/status.json, never the subscriber list, the ledger or Claude text, and never
overwrites status.json when it fails itself.

`record-topic` appends the current issue's explainer topic to
data/explainer_topics.json, only in send mode (D-06, D-15). It logs issue ids
and status codes only, never topic text.

`publish` copies the current issue to data/issues/<issue_id>.json and regenerates
the GitHub Pages files under docs/, only in send mode (D-03). `site` only
regenerates docs/ from data/issues (after a template change). Both log ids and
counts only.

`import-subscribers` copies the readers of the old CSV secret into the Sheet
through Apps Script action=import (D-06; the secrets are read only inside
newsletter.delivery). It runs once from the import-subscribers workflow and logs
counts only. Removed again in 04.1-06.

The top-level handler reports a failure as `stage=<stage> error=<ClassName>` only
and writes the same two fields to out/status.json. Exception text and tracebacks
can carry addresses, names or credentials, so they are printed only when
NEWSLETTER_DEBUG=1 (never set in CI) (DLVR-06).
"""

import argparse
import logging
import os
import re
import sys
import traceback
from datetime import datetime

from newsletter import store
from newsletter.errors import DeliveryError, PipelineError
from newsletter.week import KST, previous_iso_week

REPORT = "report"
NOTIFY = "notify-failure"
RECORD = "record-topic"
PUBLISH = "publish"
SITE = "site"
IMPORT = "import-subscribers"

log = logging.getLogger("newsletter")

# Mirrors newsletter.pipeline.STAGES (kept here so the CLI parser stays import-light;
# a test asserts both lists match).
FORCE_STAGES = (
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
FORCE_CHOICES = ("", "none", *FORCE_STAGES)


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="newsletter")
    sub = p.add_subparsers(dest="command", required=True)
    b = sub.add_parser("build", help="fetch, analyze, render and archive one week")
    b.add_argument("--week", default="", help="ISO week YYYY-Www (blank: previous week in KST)")
    b.add_argument(
        "--force-stage",
        default="",
        choices=FORCE_CHOICES,
        help="recompute this stage and every later one (blank or none: reuse checkpoints)",
    )
    d = sub.add_parser("deliver", help="send the current issue")
    d.add_argument("--mode", choices=["test", "send"], required=True)
    d.add_argument(
        "--allow-stale",
        action="store_true",
        help="send even outside the issue's KST send day (deliberate recovery only, D-03)",
    )
    rp = sub.add_parser(REPORT, help="mail the weekly run report to the owner")
    rp.add_argument("--mode", choices=["test", "send"], required=True)
    n = sub.add_parser(NOTIFY, help="alias of report")
    n.add_argument("--mode", choices=["test", "send"], required=True)
    r = sub.add_parser(RECORD, help="append the sent issue's explainer topic to the record")
    r.add_argument("--mode", choices=["preview", "test", "send"], required=True)
    w = sub.add_parser(PUBLISH, help="publish the sent issue to the web archive")
    w.add_argument("--mode", choices=["preview", "test", "send"], required=True)
    sub.add_parser(SITE, help="regenerate docs/ from data/issues")
    sub.add_parser(IMPORT, help="one-time copy of the old CSV readers into the Sheet")
    return p


def _current_issue():
    from newsletter.schema import Issue

    issue_id = store.read_current()
    return Issue.model_validate(store.read_json(store.week_dir(issue_id) / "issue.json"))


def _record_topic(mode: str) -> None:
    if mode != "send":
        log.info("topic=skipped mode=%s", mode)
        return
    from newsletter import topics

    issue = _current_issue()
    if issue.explainer is None:
        log.info("topic=none issue=%s", issue.issue_id)
    elif topics.record(issue):
        log.info("topic=recorded issue=%s", issue.issue_id)
    else:
        log.info("topic=exists issue=%s", issue.issue_id)


def _build_site() -> None:
    from newsletter import web

    log.info("web=site pages=%d", len(web.build_site()))


def _publish(mode: str) -> None:
    if mode != "send":
        log.info("web=skipped mode=%s", mode)
        return
    from newsletter import web

    issue = _current_issue()
    status = "published" if web.publish(issue) else "exists"
    log.info("web=%s issue=%s", status, issue.issue_id)
    _build_site()


def _import_subscribers() -> None:
    from newsletter.delivery.importer import run_import

    n = run_import()
    log.info(
        "import rows=%d added=%d existing=%d unsubscribed=%d skipped=%d skipped_rows=%d",
        n["rows"],
        n["added"],
        n["existing"],
        n["unsubscribed"],
        n["skipped"],
        n["skipped_rows"],
    )


def _run(args: argparse.Namespace) -> None:
    if args.command == "build":
        from newsletter.pipeline import run_build

        week = args.week.strip() or previous_iso_week(datetime.now(KST))
        run_build(week, force_stage=args.force_stage)
    elif args.command == "deliver":
        from newsletter.delivery.deliver import run_deliver

        run_deliver(args.mode, allow_stale=args.allow_stale)
    elif args.command in (REPORT, NOTIFY):
        from newsletter.delivery.notify import send_report

        send_report(args.mode)
    elif args.command == RECORD:
        _record_topic(args.mode)
    elif args.command == PUBLISH:
        _publish(args.mode)
    elif args.command == SITE:
        _build_site()
    elif args.command == IMPORT:
        _import_subscribers()


_EMAIL_RE = re.compile(r"[\w.%+-]+@[\w.-]+\.[A-Za-z]{2,}")


def _report(command: str, exc: BaseException) -> None:
    if command in (REPORT, NOTIFY, IMPORT):
        stage = command
    elif isinstance(exc, PipelineError):
        stage = exc.stage
    else:
        stage = command
    error_class = type(exc).__name__
    if os.environ.get("NEWSLETTER_DEBUG") == "1":
        traceback.print_exception(exc, file=sys.stderr)
    print(f"stage={stage} error={error_class}", file=sys.stderr)
    if isinstance(exc, DeliveryError):
        # DeliveryError text is built from env var names or SMTP class + code only.
        print(f"detail={_EMAIL_RE.sub('<redacted>', str(exc))[:200]}", file=sys.stderr)
    if command in (REPORT, NOTIFY):
        return  # keep the original failure's status.json for the workflow
    try:
        store.write_json(
            store.out_root() / "status.json", {"stage": stage, "error_class": error_class}
        )
    except OSError as e:
        print(f"stage=status error={type(e).__name__}", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    # Pitfall 3: httpx logs request URLs (repo and model ids) at INFO.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    args = _parser().parse_args(argv)
    try:
        _run(args)
    except SystemExit, KeyboardInterrupt:
        raise
    except BaseException as exc:  # noqa: BLE001 - report class only, never the text
        _report(args.command, exc)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
