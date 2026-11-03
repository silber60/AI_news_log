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
from newsletter.schema import UNKNOWN, Issue, Item
from newsletter.store import TEMPLATES_DIR

BRAND = "AI 주간 해달 브리프"
# Gmail clips messages near 102 KB; stay well under it (DSGN-04). Bytes, not characters.
MAX_EMAIL_BYTES = 90 * 1024
# Written on every text cell (~23 per card), so each byte counts ~230 times
# (research Pitfall 6): the Korean-named duplicate of Malgun Gothic is dropped.
FONT_STACK = "'IBM Plex Sans KR', 'Apple SD Gothic Neo', 'Malgun Gothic', sans-serif"
# Loaded only by clients that honor <link> web fonts (Apple Mail, iOS Mail); Gmail and
# Naver strip it and fall back to the system Korean fonts in FONT_STACK.
WEB_FONT_URL = (
    "https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+KR:wght@400;500;700&display=swap"
)
_INLINER = css_inline.CSSInliner(load_remote_stylesheets=False, keep_link_tags=True)
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


def _info_rows(it: Item) -> list[tuple[str, str]]:
    """D-10: 모델 정보 rows with a known value; stored UNKNOWN values stay in the Issue."""
    mi = it.model_info
    rows = [
        ("유형", mi.kind_ko),
        ("구조", mi.architecture_ko),
        ("크기", mi.size),
        ("학습 데이터", mi.training_data),
        ("공개 범위", mi.release),
    ]
    return [(label, value) for label, value in rows if value != UNKNOWN]


def rest_title(n: int) -> str | None:
    """D-04, D-21: the rest section names the real last rank; none when N <= 3."""
    if n <= 3:
        return None
    if n == 4:
        return "놓치기 아까운 4위 👀"
    return f"놓치기 아까운 4위부터 {n}위까지 👀"


def basis_note(issue: Issue) -> str:
    """Section subtitle. An item without stars was ranked by upvotes (D-03, D-17)."""
    if any(it.github_stars is None for it in issue.items):
        return "GitHub star 기준 (코드 없는 논문은 Hugging Face 추천 수)"
    return "GitHub star 기준"


def _context(issue: Issue, greeting: str) -> dict:
    return {
        "issue": issue,
        "greeting": greeting,
        "brand": BRAND,
        "font": Markup(FONT_STACK),  # trusted constant; keeps quotes unescaped in style=
        "web_font_url": WEB_FONT_URL,
        "asset": ASSET_BASE_URL,
        "web_url": WEB_URL,
        "hashtags": _hashtags(issue),
        "date_line": date_line(issue),
        "top3": issue.items[:3],
        "rest": issue.items[3:],
        "rest_title": rest_title(len(issue.items)),
        "basis_note": basis_note(issue),
        "info_rows": {it.rank: _info_rows(it) for it in issue.items},
    }


def render_html(issue: Issue, greeting: str) -> str:
    html = _html_env.get_template("email.html.j2").render(**_context(issue, greeting))
    html = _INLINER.inline(html)
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
