"""Check that every image in a rendered email is served over HTTPS.

Run from the repo root (no project install needed):

    uv run python scripts/check_email_images.py [email.html] [--dry-run]

With no argument it renders tests/fixtures/issue_w44.json with the greeting
구독자님 and checks only the srcs that start with ASSET_BASE_URL (the fixture's
HF image URL may be synthetic). With an email.html argument it checks every
img src in that file.

Each URL is fetched with GET (15 s timeout, redirects followed). One line per
URL is printed: status, content-type, bytes, URL. Exit 1 if any URL is not
200 or its content-type is not image/png, image/jpeg or image/gif. Run this
before any mail-sending run: Gmail's image proxy caches 404s.

Only public image URLs are printed, never email content or addresses.
"""

from __future__ import annotations

import argparse
import json
import sys
from html.parser import HTMLParser
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

import httpx

from newsletter.schema import Issue
from newsletter.stages.render import ASSET_BASE_URL, render_html

FIXTURE = REPO_ROOT / "tests" / "fixtures" / "issue_w44.json"
IMAGE_TYPES = {"image/png", "image/jpeg", "image/gif"}
TIMEOUT = 15.0


class _ImgSrcParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.srcs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "img":
            return
        for name, value in attrs:
            if name == "src" and value:
                self.srcs.append(value)


def extract_srcs(html: str) -> list[str]:
    """Return unique img srcs in document order."""
    parser = _ImgSrcParser()
    parser.feed(html)
    parser.close()
    return list(dict.fromkeys(parser.srcs))


def fixture_html() -> str:
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return render_html(Issue.model_validate(data), "구독자님")


def collect_srcs(email_path: str | None) -> list[str]:
    if email_path is None:
        return [s for s in extract_srcs(fixture_html()) if s.startswith(ASSET_BASE_URL)]
    html = Path(email_path).read_text(encoding="utf-8")
    return extract_srcs(html)


def check_url(client: httpx.Client, url: str) -> tuple[bool, str]:
    try:
        resp = client.get(url)
    except httpx.HTTPError as exc:
        return False, f"ERR  {type(exc).__name__}  -  {url}"
    ctype = resp.headers.get("content-type", "").split(";")[0].strip().lower()
    ok = resp.status_code == 200 and ctype in IMAGE_TYPES
    line = f"{resp.status_code}  {ctype or '-'}  {len(resp.content)}  {url}"
    return ok, line


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Fetch every img src of a rendered email and report status per URL.",
    )
    parser.add_argument(
        "email_html",
        nargs="?",
        help="Path to an email.html. Default: render tests/fixtures/issue_w44.json "
        "and check only ASSET_BASE_URL srcs.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List the srcs that would be checked, without network access.",
    )
    args = parser.parse_args(argv)

    srcs = collect_srcs(args.email_html)
    if not srcs:
        print("no image srcs found", file=sys.stderr)
        return 1

    if args.dry_run:
        for src in srcs:
            print(src)
        return 0

    failed = 0
    with httpx.Client(timeout=TIMEOUT, follow_redirects=True) as client:
        for src in srcs:
            ok, line = check_url(client, src)
            print(("OK   " if ok else "FAIL ") + line)
            if not ok:
                failed += 1
    print(f"{len(srcs) - failed}/{len(srcs)} ok")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
