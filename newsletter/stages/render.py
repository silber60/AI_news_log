"""Render an `Issue` to email HTML (inlined CSS) and plain text.

Layout follows the Figma v2 draft (Phase 1.1, D-01..D-05); see
.planning/phases/01.1-newsletter-design-v2/01.1-FIGMA-SPEC.md.
"""

import math
from datetime import timedelta
from typing import Literal

import css_inline
from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape
from markupsafe import Markup

from newsletter.errors import RenderTooLarge
from newsletter.schema import UNKNOWN, Issue, Item
from newsletter.stages.highlight import SPACE_PREFIX
from newsletter.stages.verdicts import EVIDENCE_HOSTS, POC_GATED_LABEL
from newsletter.store import TEMPLATES_DIR

BRAND = "모닥로그 AI 리포트"
# Gmail clips messages near 102 KB; stay well under it (DSGN-04). Bytes, not characters.
MAX_EMAIL_BYTES = 90 * 1024
# Written on every presentation <table> (D-14, template-version 7), and cells inherit it,
# so each byte counts once per table (~50 in the worst case, not ~215 cells as before).
# The Korean-named duplicate of Malgun Gothic stays dropped (research Pitfall 6).
FONT_STACK = "'IBM Plex Sans KR', 'Apple SD Gothic Neo', 'Malgun Gothic', sans-serif"
# Loaded only by clients that honor <link> web fonts (Apple Mail, iOS Mail); Gmail and
# Naver strip it and fall back to the system Korean fonts in FONT_STACK.
WEB_FONT_URL = (
    "https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+KR:wght@400;500;700&display=swap"
)
_INLINER = css_inline.CSSInliner(load_remote_stylesheets=False, keep_link_tags=True)
# D-09: versioned, never-overwritten public asset directory. v2 (brand 모닥로그 AI 리포트)
# swaps the top banner; v1 stays published for emails already sent.
ASSET_BASE_URL = "https://silber60.github.io/AI_news_log/assets/email/v2"
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


# D-01, D-05: fixed code phrases for the one-line verdict row; never Claude text.
COMMERCIAL_PHRASES = {
    "가능": "💼 상업 이용 가능",
    "조건부": "💼 조건부 상업 이용",
    "불가": "💼 상업 이용 불가",
}
# D-09: only the code license is known, so the weights may differ.
COMMERCIAL_CODE_ONLY_PHRASE = "💼 코드 상업 이용 가능"
# D-11: 해당 없음 is hidden in the email.
CLAUDE_GPT_PHRASES = {
    "직접 사용": "🤖 Claude/GPT에서 바로 써요",
    "기법 적용 가능": "🤖 Claude/GPT 기법 적용",
}
# D-02: at most one license link per card, and only a short one.
EVIDENCE_LINK_MAX = 200
POC_PHRASES = {
    "바로 가능": "🧪 바로 써볼 수 있어요",
    "코드만": "🧪 코드만 공개됐어요",
    "논문만": "🧪 아직 논문만 있어요",
}
POC_GATED_PHRASE = "🧪 승인 받고 써볼 수 있어요"


def _poc_phrase(it: Item) -> str | None:
    p = it.poc
    if p.verdict == "바로 가능" and p.evidence and p.evidence[0].label == POC_GATED_LABEL:
        return POC_GATED_PHRASE
    return POC_PHRASES.get(p.verdict)


def _commercial_phrase(it: Item) -> str | None:
    c = it.commercial
    if c.verdict == "가능" and c.weights_license is None and c.code_license is not None:
        return COMMERCIAL_CODE_ONLY_PHRASE
    return COMMERCIAL_PHRASES.get(c.verdict)


def _gpu_phrase(it: Item) -> str | None:
    hw = it.hardware
    if hw.est_vram_gb is None or hw.local_run == UNKNOWN:
        return None
    n = math.ceil(hw.est_vram_gb)
    if hw.local_run == "가능":
        return f"🖥️ 개인 GPU 약 {n}GB"
    if hw.local_run == "제한적":
        return f"🖥️ 서버 GPU 약 {n}GB"
    return f"🖥️ GPU 여러 장 필요 (약 {n}GB)"


def verdict_line(it: Item) -> list[str]:
    """D-01: known verdicts only, in display order; 확인 필요 is omitted."""
    phrases = [
        _commercial_phrase(it),
        _poc_phrase(it),
        _gpu_phrase(it),
        CLAUDE_GPT_PHRASES.get(it.claude_gpt.verdict),
    ]
    return [p for p in phrases if p]


def license_link(it: Item) -> str | None:
    """D-02: the evidence URL of the side that set the 상업 verdict, when it is shown."""
    if _commercial_phrase(it) is None or not it.commercial.evidence:
        return None
    url = it.commercial.evidence[0].url
    if len(url) > EVIDENCE_LINK_MAX or not url.startswith(EVIDENCE_HOSTS):
        return None
    return url


def demo_label(url: str) -> str:
    """Highlight link text (schema v4): an HF Space is a demo, anything else a project page."""
    return "데모 써보기" if url.startswith(SPACE_PREFIX) else "프로젝트 페이지"


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
        "verdict_lines": {it.rank: verdict_line(it) for it in issue.items},
        "license_links": {it.rank: license_link(it) for it in issue.items},
        "demo_label": demo_label,
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
