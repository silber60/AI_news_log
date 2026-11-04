"""Static web archive on GitHub Pages (WEB-01, WEB-02, D-01..D-03, D-06).

data/issues/<issue_id>.json is the source of truth (first send wins, like
topics.record). docs/issues/<issue_id>/index.html and docs/index.html are always
regenerated from it, with no timestamps, so a re-run changes no byte. Nothing here
writes under docs/assets/ or touches the network.
"""

import os
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

from newsletter import store
from newsletter.schema import Issue
from newsletter.stages import render

_web_env = Environment(
    loader=FileSystemLoader(store.TEMPLATES_DIR / "web"),
    autoescape=select_autoescape(["html", "j2"]),
    undefined=StrictUndefined,
    keep_trailing_newline=True,
)


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


def _card(issue: Issue) -> dict:
    return {
        "href": f"issues/{issue.issue_id}/",
        "date": render.date_line(issue),
        "headline": issue.headline_ko,
    }


def build_site() -> list[Path]:
    """Regenerate every issue page and the home page. Returns the written paths."""
    issues = load_issues()
    docs = docs_dir()
    written: list[Path] = []
    for issue in issues:
        path = docs / "issues" / issue.issue_id / "index.html"
        store.write_text(path, render.render_web_issue(issue))
        written.append(path)
    home = _web_env.get_template("home.html.j2").render(
        brand=render.BRAND, cards=[_card(i) for i in issues]
    )
    path = docs / "index.html"
    store.write_text(path, home)
    written.append(path)
    return written
