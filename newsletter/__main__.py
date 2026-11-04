"""CLI: `python -m newsletter build --week YYYY-Www`, `deliver --mode test|send`,
`notify-failure --mode test|send`, `record-topic --mode preview|test|send`.

`record-topic` appends the current issue's explainer topic to
data/explainer_topics.json, only in send mode (D-06, D-15). It logs issue ids
and status codes only, never topic text.

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

NOTIFY = "notify-failure"
RECORD = "record-topic"

log = logging.getLogger("newsletter")


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="newsletter")
    sub = p.add_subparsers(dest="command", required=True)
    b = sub.add_parser("build", help="fetch, analyze, render and archive one week")
    b.add_argument("--week", default="", help="ISO week YYYY-Www (blank: previous week in KST)")
    d = sub.add_parser("deliver", help="send the current issue")
    d.add_argument("--mode", choices=["test", "send"], required=True)
    n = sub.add_parser(NOTIFY, help="mail a failure notice to the owner")
    n.add_argument("--mode", choices=["test", "send"], required=True)
    r = sub.add_parser(RECORD, help="append the sent issue's explainer topic to the record")
    r.add_argument("--mode", choices=["preview", "test", "send"], required=True)
    return p


def _record_topic(mode: str) -> None:
    if mode != "send":
        log.info("topic=skipped mode=%s", mode)
        return
    from newsletter import topics
    from newsletter.schema import Issue

    issue_id = store.read_current()
    issue = Issue.model_validate(store.read_json(store.week_dir(issue_id) / "issue.json"))
    if issue.explainer is None:
        log.info("topic=none issue=%s", issue.issue_id)
    elif topics.record(issue):
        log.info("topic=recorded issue=%s", issue.issue_id)
    else:
        log.info("topic=exists issue=%s", issue.issue_id)


def _run(args: argparse.Namespace) -> None:
    if args.command == "build":
        from newsletter.pipeline import run_build

        week = args.week.strip() or previous_iso_week(datetime.now(KST))
        run_build(week)
    elif args.command == "deliver":
        from newsletter.delivery.deliver import run_deliver

        run_deliver(args.mode)
    elif args.command == NOTIFY:
        from newsletter.delivery.notify import send_failure_notice

        send_failure_notice(args.mode)
    elif args.command == RECORD:
        _record_topic(args.mode)


_EMAIL_RE = re.compile(r"[\w.%+-]+@[\w.-]+\.[A-Za-z]{2,}")


def _report(command: str, exc: BaseException) -> None:
    if command == NOTIFY:
        stage = NOTIFY
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
    if command == NOTIFY:
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
