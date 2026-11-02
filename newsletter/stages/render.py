"""Render an `Issue` to email HTML (inlined CSS) and plain text.

Layout follows the Figma v2 draft (Phase 1.1, D-01..D-05); see
.planning/phases/01.1-newsletter-design-v2/01.1-FIGMA-SPEC.md.
"""

from datetime import timedelta
from typing import Literal

import css_inline
from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape
from markupsafe import Markup

from newsletter.errors import RenderTooLarge
from newsletter.schema import Issue
from newsletter.store import TEMPLATES_DIR

BRAND = "AI 주간 모델 브리프"
# Gmail clips messages near 102 KB; stay well under it (DSGN-04). Bytes, not characters.
MAX_EMAIL_BYTES = 90 * 1024
FONT_STACK = (
    "-apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', 'Malgun Gothic', "
    "'맑은 고딕', 'Noto Sans KR', sans-serif"
)
# D-09: versioned, never-overwritten public asset directory (docs/assets/email/v1/).
ASSET_BASE_URL = "https://silber60.github.io/AI_news_log/assets/email/v1"
# D-16: 웹에서 보기 / 지난 호 보기 stay hidden until the web archive exists (Phase 4).
WEB_URL: str | None = None
# Max hashtags in the header (research Assumption A9).
HASHTAG_MAX = 3
_WEEKDAYS_KO = ("월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일")

_html_env = Environment(
    loader=FileSystemLoader(TEMPLATES_DIR),
    autoescape=select_autoescape(["html", "j2"]),
    undefined=StrictUndefined,
)
_text_env = Environment(
    loader=FileSystemLoader(TEMPLATES_DIR),
    autoescape=False,
    undefined=StrictUndefined,
    keep_trailing_newline=True,
)


def _hashtags(issue: Issue) -> list[str]:
    tags: list[str] = []
    for it in issue.items:
        tag = "#" + it.ai_type.replace(" ", "")
        if tag not in tags:
            tags.append(tag)
        if len(tags) == HASHTAG_MAX:
            break
    return tags


def date_line(issue: Issue) -> str:
    """Send date = the Monday after the KST week (Pitfall 9: never runner time)."""
    d = issue.week_end + timedelta(days=1)
    return f"{d:%Y.%m.%d} {_WEEKDAYS_KO[d.weekday()]}"


def _context(issue: Issue, greeting: str) -> dict:
    return {
        "issue": issue,
        "greeting": greeting,
        "brand": BRAND,
        "font": Markup(FONT_STACK),  # trusted constant; keeps quotes unescaped in style=
        "asset": ASSET_BASE_URL,
        "web_url": WEB_URL,
        "hashtags": _hashtags(issue),
        "date_line": date_line(issue),
        "top3": issue.items[:3],
        "rest": issue.items[3:],
        "hero_image": issue.items[0].image,
    }


def render_html(issue: Issue, greeting: str) -> str:
    html = _html_env.get_template("email.html.j2").render(**_context(issue, greeting))
    html = css_inline.inline(html)
    n = len(html.encode("utf-8"))
    if n >= MAX_EMAIL_BYTES:
        # Message holds only the size; never content or recipient data.
        raise RenderTooLarge(f"bytes={n}")
    return html


def render_text(issue: Issue, greeting: str) -> str:
    return _text_env.get_template("email.txt.j2").render(**_context(issue, greeting))


def build_subject(issue: Issue, mode: Literal["preview", "test", "send"]) -> str:
    """D-12 / DLVR-07: the issue headline; `[TEST] ` prefix only in test mode."""
    subject = issue.headline_ko
    if mode == "test":
        subject = "[TEST] " + subject
    # Header injection guard: no CR/LF may reach the Subject header.
    return subject.replace("\r", " ").replace("\n", " ")
