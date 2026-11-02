"""Render an `Issue` to email HTML (inlined CSS) and plain text.

Phase 1 layout per D-04/D-06/D-08; final Figma design is Phase 4.
"""

from typing import Literal

import css_inline
from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape
from markupsafe import Markup

from newsletter.errors import RenderTooLarge
from newsletter.schema import AiType, Issue
from newsletter.store import TEMPLATES_DIR
from newsletter.week import week_label

BRAND = "AI 주간 모델 브리프"
# Gmail clips messages near 102 KB; stay well under it (DSGN-04). Bytes, not characters.
MAX_EMAIL_BYTES = 90 * 1024
# D-01: cap the #1 title in the subject so it stays readable on mobile.
SUBJECT_TITLE_MAX = 32
FONT_STACK = (
    "-apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', 'Malgun Gothic', "
    "'맑은 고딕', 'Noto Sans KR', sans-serif"
)

# AI 종류 badge colors: (background, text). Text badge only, never an image.
AI_TYPE_COLORS: dict[AiType, tuple[str, str]] = {
    "LLM": ("#dbeafe", "#1e40af"),
    "비전": ("#dcfce7", "#166534"),
    "멀티모달": ("#ede9fe", "#5b21b6"),
    "음성": ("#fef3c7", "#92400e"),
    "에이전트": ("#ffe4e6", "#9f1239"),
    "이미지/비디오 생성": ("#fce7f3", "#9d174d"),
    "기타": ("#f4f4f5", "#3f3f46"),
}

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
        "font": Markup(FONT_STACK),  # trusted constant; keeps quotes unescaped in style=
        "colors": AI_TYPE_COLORS,
        "label": week_label(issue.week_start, issue.week_end),
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
    """D-01 subject; `[TEST] ` prefix only in test mode (D-03); count follows N (D-11)."""
    n = len(issue.items)
    title = issue.items[0].title_ko.replace("\r", " ").replace("\n", " ")
    if len(title) > SUBJECT_TITLE_MAX:
        title = title[:SUBJECT_TITLE_MAX].rstrip() + "…"
    subject = f"[{BRAND}] 이번 주 1위: {title}"
    if n > 1:
        subject += f" 외 {n - 1}건"
    if mode == "test":
        subject = "[TEST] " + subject
    # Header injection guard: no CR/LF may reach the Subject header.
    return subject.replace("\r", " ").replace("\n", " ")
