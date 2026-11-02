"""Render an `Issue` to email HTML (inlined CSS) and plain text.

Plan 04 completes layout, truncation and the size gate.
"""

from typing import Literal

import css_inline
from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

from newsletter.schema import Issue
from newsletter.store import TEMPLATES_DIR
from newsletter.week import week_label

BRAND = "AI 주간 모델 브리프"
FONT_STACK = (
    "-apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', 'Malgun Gothic', "
    "'맑은 고딕', 'Noto Sans KR', sans-serif"
)

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


def _context(issue: Issue, greeting: str) -> dict:
    return {
        "issue": issue,
        "greeting": greeting,
        "brand": BRAND,
        "font": FONT_STACK,
        "label": week_label(issue.week_start, issue.week_end),
    }


def render_html(issue: Issue, greeting: str) -> str:
    html = _html_env.get_template("email.html.j2").render(**_context(issue, greeting))
    return css_inline.inline(html)


def render_text(issue: Issue, greeting: str) -> str:
    return _text_env.get_template("email.txt.j2").render(**_context(issue, greeting))


def build_subject(issue: Issue, mode: Literal["preview", "test", "send"]) -> str:
    n = len(issue.items)
    subject = f"[{BRAND}] 이번 주 1위: {issue.items[0].title_ko}"
    if n > 1:
        subject += f" 외 {n - 1}건"
    if mode == "test":
        subject = "[TEST] " + subject
    return subject
