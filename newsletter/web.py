"""Static web archive on GitHub Pages (WEB-01, WEB-02, D-01..D-03, D-06).

data/issues/<issue_id>.json is the source of truth (first send wins, like
topics.record). docs/issues/<issue_id>/index.html and docs/index.html are always
regenerated from it, as is docs/unsubscribe/index.html (the D-12 confirm page) and
docs/welcome/latest.json (the 04.1 welcome mail payload), with no timestamps, so a
re-run changes no byte. Nothing here
writes under docs/assets/ or touches the network.
"""

import json
import logging
import os
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape
from markupsafe import Markup

from newsletter import store
from newsletter.delivery import unsubscribe
from newsletter.errors import RenderTooLarge
from newsletter.schema import Issue
from newsletter.stages import render

log = logging.getLogger(__name__)

_web_env = Environment(
    loader=FileSystemLoader(store.TEMPLATES_DIR / "web"),
    autoescape=select_autoescape(["html", "j2"]),
    undefined=StrictUndefined,
    keep_trailing_newline=True,
)

# D-09, D-10: unsubscribe.UNSUBSCRIBE_ENDPOINT is the one switch. The subscribe forms and
# the nav 구독하기 button post to that same Apps Script /exec URL and render only once it
# is set; it is read at render time, never copied here.
PRIVACY_URL: str | None = None
# The consent-text version each form posts as cv. Code.gs CONSENT_VERSIONS must list it,
# and it is the privacy page 시행일 (04.1-02 contract).
CONSENT_VERSION = "2026-11-04"


def issues_dir() -> Path:
    env = os.environ.get("NEWSLETTER_ISSUES_DIR")
    return Path(env) if env else store.REPO_ROOT / "data" / "issues"


def docs_dir() -> Path:
    env = os.environ.get("NEWSLETTER_DOCS_DIR")
    return Path(env) if env else store.REPO_ROOT / "docs"


def publish(issue: Issue) -> bool:
    """Store this issue once per issue_id. True when the data file was written."""
    path = issues_dir() / f"{issue.issue_id}.json"
    if path.exists():
        return False
    store.write_json(path, issue)
    return True


def load_issues() -> list[Issue]:
    """Every published issue, newest first. One invalid file raises."""
    d = issues_dir()
    if not d.is_dir():
        return []
    issues = [Issue.model_validate(store.read_json(p)) for p in d.glob("*.json")]
    return sorted(issues, key=lambda i: i.issue_id, reverse=True)


def card(issue: Issue) -> dict:
    """D-08: one 지난 호 card. Relative url so the home page works under any Pages base."""
    first = issue.items[0]
    return {
        "url": f"issues/{issue.issue_id}/",
        "date": render.date_line(issue),
        "headline": issue.headline_ko,
        "top3": [it.title_ko for it in issue.items[:3]],
        "image": first.image,  # ItemImage | None; hotlinked like the email
        "image_alt": first.title_ko,
    }


def _home_context(issues: list[Issue]) -> dict:
    cards = [card(i) for i in issues]
    return {
        "brand": render.BRAND,
        "cards": cards,
        "latest": cards[0] if cards else None,
        "subscribe_url": unsubscribe.UNSUBSCRIBE_ENDPOINT,  # read at call time (one switch)
        "consent_version": CONSENT_VERSION,
        "privacy_url": PRIVACY_URL,
        "archive_id": render.ARCHIVE_ANCHOR.removeprefix("#"),
        "archive_href": render.ARCHIVE_ANCHOR,
        "asset": render.ASSET_BASE_URL,
        "web_font_url": render.WEB_FONT_URL,
        "font": Markup(render.FONT_STACK),  # trusted constant; keeps quotes unescaped
    }


def _unsubscribe_context() -> dict:
    """D-12: the confirm page lives one level down, so its nav links climb with ../."""
    return {
        **_home_context([]),
        "subscribe_url": None,  # no subscribe CTA on the way out
        "home_href": "../",
        "archive_href": "../" + render.ARCHIVE_ANCHOR,
        "endpoint": unsubscribe.UNSUBSCRIBE_ENDPOINT,
        "token_len": unsubscribe.TOKEN_LEN,
    }


def welcome_payload(issues: list[Issue]) -> dict:
    """D-03, D-04: what Apps Script fills and sends to a new reader (04.1-02 contract).

    Built only from the newest published issue plus constants, never recipient data.
    With no issue, or when the welcome variant is too large, Apps Script gets
    issue_id null: it registers the reader and sends no welcome mail."""
    null = {"version": 1, "issue_id": None}
    if not issues:
        return null
    issue = issues[0]
    try:
        mail = render.render_welcome(issue)
    except RenderTooLarge as e:
        # The message is "bytes=<n>" and holds only the size.
        log.info("welcome=too_large bytes=%s", str(e).removeprefix("bytes="))
        return null
    return {
        "version": 1,
        "issue_id": issue.issue_id,
        "subject": mail["subject"],
        "html": mail["html"],
        "text": mail["text"],
        "slots": {"greeting": render.GREETING_SLOT, "unsubscribe_url": render.UNSUB_SLOT},
        "unsubscribe_page": render.SITE_URL + "unsubscribe/?t=",
        "endpoint": unsubscribe.UNSUBSCRIBE_ENDPOINT,  # read at call time (one switch)
        "from_name": render.BRAND,
    }


def build_site() -> list[Path]:
    """Regenerate every issue page, the home page, the unsubscribe confirm page and the
    welcome payload. Returns the written paths."""
    issues = load_issues()
    docs = docs_dir()
    written: list[Path] = []
    for issue in issues:
        path = docs / "issues" / issue.issue_id / "index.html"
        store.write_text(path, render.render_web_issue(issue))
        written.append(path)
    home = _web_env.get_template("home.html.j2").render(**_home_context(issues))
    path = docs / "index.html"
    store.write_text(path, home)
    written.append(path)
    page = _web_env.get_template("unsubscribe.html.j2").render(**_unsubscribe_context())
    path = docs / "unsubscribe" / "index.html"
    store.write_text(path, page)
    written.append(path)
    payload = welcome_payload(issues)
    path = docs / "welcome" / "latest.json"
    store.write_text(path, json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
    written.append(path)
    return written
