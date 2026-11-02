"""CLI: `python -m newsletter build --week YYYY-Www`, `deliver --mode test|send`,
`notify-failure --mode test|send`.

The top-level handler reports a failure as `stage=<stage> error=<ClassName>` only
and writes the same two fields to out/status.json. Exception text and tracebacks
can carry addresses, names or credentials, so they are printed only when
NEWSLETTER_DEBUG=1 (never set in CI) (DLVR-06).
"""

import argparse
import logging
import os
import sys
import traceback
from datetime import datetime

from newsletter import store
from newsletter.errors import PipelineError
from newsletter.week import KST, previous_iso_week

NOTIFY = "notify-failure"


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="newsletter")
    sub = p.add_subparsers(dest="command", required=True)
    b = sub.add_parser("build", help="fetch, analyze, render and archive one week")
    b.add_argument("--week", default="", help="ISO week YYYY-Www (blank: previous week in KST)")
    d = sub.add_parser("deliver", help="send the current issue")
    d.add_argument("--mode", choices=["test", "send"], required=True)
    n = sub.add_parser(NOTIFY, help="mail a failure notice to the owner")
    n.add_argument("--mode", choices=["test", "send"], required=True)
    return p


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
