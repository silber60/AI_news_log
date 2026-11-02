"""CLI: `python -m newsletter build --week YYYY-Www` and `deliver --mode test`.

Plan 05 owns the top-level error handler (stage + error class only).
"""

import argparse
import logging
import sys
from datetime import datetime

from newsletter.week import KST, previous_iso_week


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="newsletter")
    sub = p.add_subparsers(dest="command", required=True)
    b = sub.add_parser("build", help="fetch, analyze, render and archive one week")
    b.add_argument("--week", default="", help="ISO week YYYY-Www (blank: previous week in KST)")
    d = sub.add_parser("deliver", help="send the current issue")
    d.add_argument("--mode", choices=["test"], required=True)
    return p


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    args = _parser().parse_args(argv)

    if args.command == "build":
        from newsletter.pipeline import run_build

        week = args.week.strip() or previous_iso_week(datetime.now(KST))
        run_build(week)
    elif args.command == "deliver":
        from newsletter.delivery.deliver import run_deliver

        run_deliver(args.mode)
    return 0


if __name__ == "__main__":
    sys.exit(main())
