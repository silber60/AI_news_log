"""Figma v2 email render (Phase 1.1): sections, cards, email-safe markup, size, text, subject."""

import hashlib
import html as html_lib
import re
from html.parser import HTMLParser

import pytest
import respx
from conftest import FakeAnthropic, mock_hf_week

from newsletter.errors import RenderTooLarge
from newsletter.schema import (
    IMAGE_URL_MAX,
    UNKNOWN,
    EvidenceLink,
    Explainer,
    Highlight,
    ItemImage,
    LicenseInfo,
)
from newsletter.stages import render as render_mod
from newsletter.stages.render import (
    ASSET_BASE_URL,
    CLAUDE_GPT_PHRASES,
    COMMERCIAL_CODE_ONLY_PHRASE,
    COMMERCIAL_PHRASES,
    EVIDENCE_LINK_MAX,
    MAX_EMAIL_BYTES,
    build_subject,
    license_link,
    render_html,
    render_text,
    verdict_line,
)
from newsletter.stages.verdicts import POC_GATED_LABEL

ISSUE_ID = "2026-W44"


def _meta(it) -> str:
    """D-17: ★ stars (thousands separator) for star-ranked items, ▲ upvotes otherwise."""
    if it.github_stars is not None:
        return f"{it.rank}위 ㅣ {it.ai_type} ㅣ ★ {it.github_stars:,}"
    return f"{it.rank}위 ㅣ {it.ai_type} ㅣ ▲ {it.upvotes}"


def _build(hf_pages):
    from newsletter.pipeline import run_build

    with respx.mock(assert_all_mocked=True, assert_all_called=True) as router:
        mock_hf_week(router, hf_pages, ISSUE_ID)
        return run_build(ISSUE_ID, claude_client=FakeAnthropic())


# ---------------------------------------------------------------- Task 1 tracer


def test_build_renders_full_card_email(hf_pages, archive_tmp):
    issue = _build(hf_pages)
    out = (archive_tmp / "archive" / ISSUE_ID / "email.html").read_text(encoding="utf-8")

    assert out.count("data-card=") == 10
    for it in issue.items:
        assert html_lib.escape(it.title_ko, quote=False) in out
        assert _meta(it) in out
    assert "1위 ㅣ 멀티모달 ㅣ ★ 5,221" in out
    assert "▲" not in out
    assert "구독자님" in out
    assert "2026.11.02 월요일" in out


SECTION_ORDER = [
    "banner",
    "header",
    "hero",
    "greeting",
    "trend",
    "highlight",
    "top3",
    "explainer",
    "rest",
    "closing",
    "footer",
]


def _sections(out: str) -> list[str]:
    return re.findall(r'data-section="([a-z0-9]+)"', out)


def _full_issue(issue):
    """W44 plus every Phase 3 slot filled."""
    return issue.model_copy(
        update={
            "highlights": [
                Highlight(
                    rank=2, tag="Claude Skill", why_ko="왜 좋은지 문장", how_ko="만드는 법 문장"
                )
            ],
            "trend_ko": "이번 주 트렌드 문장",
            "explainer": Explainer(
                topic="MoE 해설",
                body_ko="전문가 혼합 설명",
                related_ranks=[1],
                point_ko="핵심 한 줄",
                example_ko="예시 문장",
            ),
        }
    )


def test_w44_sections_in_figma_order_without_phase3_slots(issue_w44):
    """W44 has no trend or explainer. The highlight section always renders (D-01)."""
    out = render_html(issue_w44, "구독자님")
    assert _sections(out) == [
        "banner",
        "header",
        "hero",
        "greeting",
        "highlight",
        "top3",
        "rest",
        "closing",
        "footer",
    ]


def test_empty_highlights_render_the_fallback_line(issue_w44):
    """HILT-03, D-01: no pick (none fit, or the call failed) still shows the section
    with exactly one fallback line and no tag pill, in both parts."""
    issue = issue_w44.model_copy(update={"highlights": []})
    out = render_html(issue, "구독자님")
    section = out[_section_pos(out, "highlight") : _section_pos(out, "top3")]
    assert "이번 주 바로 써볼 만한 것 ✨" in section
    assert section.count("이번 주는 해당 항목 없음") == 1
    for tag in ("Claude Skill", "GPTs", "둘 다"):
        assert tag not in section
    assert "왜 좋은지" not in section and "<span" not in section
    txt = render_text(issue, "구독자님")
    head, rest = txt.split("이번 주 바로 써볼 만한 것 ✨", 1)
    block = rest.split("이것만 보면 끝!", 1)[0]
    assert block.count("이번 주는 해당 항목 없음") == 1
    assert "[" not in block and "왜 좋은지" not in block
    assert "안녕하세요" in head  # the section sits below the greeting


def test_filled_highlights_hide_the_fallback_line(issue_w44):
    full = _full_issue(issue_w44)
    assert full.highlights
    for part in (render_html(full, "구독자님"), render_text(full, "구독자님")):
        assert "이번 주는 해당 항목 없음" not in part


def test_all_eleven_sections_render_in_order_when_filled(issue_w44):
    assert _sections(render_html(_full_issue(issue_w44), "구독자님")) == SECTION_ORDER


def _section_pos(out: str, name: str) -> int:
    return out.index(f'data-section="{name}"')


def test_cards_split_between_top3_and_rest(issue_w44):
    out = render_html(_full_issue(issue_w44), "구독자님")
    top3, explainer, rest = (_section_pos(out, n) for n in ("top3", "explainer", "rest"))
    for rank in range(1, 11):
        pos = out.index(f'data-card="{rank}"')
        if rank <= 3:
            assert top3 < pos < explainer, rank
        else:
            assert pos > rest, rank
    assert "이것만 보면 끝! 이번 주 AI 모델 Top 3 ⚡️" in out
    assert "놓치기 아까운 4위부터 10위까지 👀" in out
    assert out.count(BASIS_MIXED) == 2


def test_two_item_issue_has_no_rest_section(issue_w44):
    issue = issue_w44.model_copy(update={"items": issue_w44.items[:2]})
    out = render_html(issue, "구독자님")
    assert "rest" not in _sections(out)
    assert "놓치기 아까운" not in out
    assert out.count("data-card=") == 2
    assert "놓치기 아까운" not in render_text(issue, "구독자님")


def test_header_date_is_monday_after_week(issue_w44):
    out = render_html(issue_w44, "구독자님")
    assert "2026.11.02 월요일" in out
    assert "#멀티모달" in out
    assert "모닥로그 AI 리포트" in out
    assert "매주 월요일, 실무에 바로 쓸 AI 모델만 골라 드려요" in out


def test_hero_shows_headline_and_no_image(issue_w44):
    # D-07: nothing under the headline; the top otter banner stays.
    assert issue_w44.items[0].image is not None
    out = render_html(issue_w44, "구독자님")
    hero = out[_section_pos(out, "hero") : _section_pos(out, "greeting")]
    assert html_lib.escape(issue_w44.headline_ko, quote=False) in hero
    assert "<img" not in hero
    banner = out[_section_pos(out, "banner") : _section_pos(out, "header")]
    assert "otter-banner.jpg" in banner


def _greeting(name: str, n: int) -> str:
    return (
        f"{name}, 안녕하세요. 지난주 Hugging Face Papers에 올라온 모델 중 "
        f"GitHub star를 많이 받은 {n}개를 골랐어요!"
    )


def _n_items(issue, n: int):
    return issue.model_copy(update={"items": issue.items[:n]})


def test_star_greeting_line(issue_w44):
    # D-06: the star-based sentence with the real N.
    assert _greeting("구독자님", 10) in render_html(issue_w44, "구독자님")
    assert _greeting("구독자님", 10) in render_text(issue_w44, "구독자님")
    assert "추천을 많이 받은" not in render_html(issue_w44, "구독자님")


@pytest.mark.parametrize("n", [3, 10])
def test_star_greeting_counts_items(issue_w44, n):
    issue = _n_items(issue_w44, n)
    assert _greeting("구독자님", n) in render_html(issue, "구독자님")
    assert _greeting("구독자님", n) in render_text(issue, "구독자님")


def test_star_greeting_uses_name_as_given(issue_w44):
    assert _greeting("홍길동님", 10) in render_html(issue_w44, "홍길동님")
    assert _greeting("홍길동님", 10) in render_text(issue_w44, "홍길동님")


BASIS_STARS = "GitHub star 기준"
BASIS_MIXED = "GitHub star 기준 (코드 없는 논문은 Hugging Face 추천 수)"


@pytest.mark.parametrize(
    ("n", "title"),
    [
        (3, None),
        (4, "놓치기 아까운 4위 👀"),
        (7, "놓치기 아까운 4위부터 7위까지 👀"),
        (10, "놓치기 아까운 4위부터 10위까지 👀"),
    ],
)
def test_rest_title_follows_n(issue_w44, n, title):
    # D-04, D-21: the rest title names the real last rank; N == 3 has no rest section.
    issue = _n_items(issue_w44, n)
    out = render_html(issue, "구독자님")
    txt = render_text(issue, "구독자님")
    if title is None:
        assert "rest" not in _sections(out)
        assert "놓치기 아까운" not in out and "놓치기 아까운" not in txt
    else:
        rest = out[_section_pos(out, "rest") : _section_pos(out, "closing")]
        assert title in rest
        assert title in txt
        assert out.count("놓치기 아까운") == 1 and txt.count("놓치기 아까운") == 1
    assert "이것만 보면 끝! 이번 주 AI 모델 Top 3 ⚡️" in out


def test_basis_note_stars_only_when_every_item_has_stars(issue_w44):
    items = [it.model_copy(update={"github_stars": 100 + it.rank}) for it in issue_w44.items]
    issue = issue_w44.model_copy(update={"items": items})
    out = render_html(issue, "구독자님")
    txt = render_text(issue, "구독자님")
    for part in (out, txt):
        assert part.count(BASIS_STARS) == 2
        assert BASIS_MIXED not in part
        assert "Hugging Face 추천 수 기준" not in part


def test_basis_note_mentions_upvotes_when_an_item_has_no_stars(issue_w44):
    items = [it.model_copy(update={"github_stars": 100 + it.rank}) for it in issue_w44.items]
    items[9] = items[9].model_copy(update={"github_stars": None})
    issue = issue_w44.model_copy(update={"items": items})
    for part in (render_html(issue, "구독자님"), render_text(issue, "구독자님")):
        assert part.count(BASIS_MIXED) == 2


# ------------------------------------------------- Task 2 email-safe markup


class _Cells(HTMLParser):
    """Collect every <td>'s style, its nearest ancestor table's style and its own visible
    text (nested tables excluded). Also keep every <table>, <td> and <span> style."""

    def __init__(self):
        super().__init__()
        self.stack: list[dict] = []
        self.tables: list[str] = []  # styles of the open tables, innermost last
        self.cells: list[dict] = []
        self.tags: set[str] = set()
        self.styles: dict[str, list[str]] = {"table": [], "td": [], "span": []}
        self.presentation: list[str] = []

    def handle_starttag(self, tag, attrs):
        self.tags.add(tag)
        a = dict(attrs)
        style = a.get("style") or ""
        if tag in self.styles:
            self.styles[tag].append(style)
        if tag == "table":
            self.tables.append(style)
            if a.get("role") == "presentation":
                self.presentation.append(style)
        elif tag == "td":
            table = self.tables[-1] if self.tables else ""
            self.stack.append({"style": style, "table": table, "text": ""})

    def handle_endtag(self, tag):
        if tag == "td" and self.stack:
            self.cells.append(self.stack.pop())
        elif tag == "table" and self.tables:
            self.tables.pop()

    def handle_data(self, data):
        if self.stack:
            self.stack[-1]["text"] += data


def _cells(out: str) -> _Cells:
    p = _Cells()
    p.feed(out)
    p.close()
    return p


class _Imgs(HTMLParser):
    def __init__(self):
        super().__init__()
        self.imgs: list[dict] = []

    def handle_starttag(self, tag, attrs):
        if tag == "img":
            self.imgs.append(dict(attrs))


def _imgs(out: str) -> list[dict]:
    p = _Imgs()
    p.feed(out)
    p.close()
    return p.imgs


def _cards(out: str) -> list[str]:
    """Each card's markup, cut before the next card or section."""
    return [c.split("data-section=")[0] for c in out.split("data-card=")[1:]]


def _with_item(issue, idx: int, **update):
    items = list(issue.items)
    items[idx] = items[idx].model_copy(update=update)
    return issue.model_copy(update={"items": items})


def test_no_style_block_and_tables_only(issue_w44):
    out = render_html(issue_w44, "구독자님")
    assert "<style" not in out
    assert "<div" not in out
    assert "class=" not in out
    for img in _imgs(out):
        assert img.get("alt"), img
        assert (img.get("width") or "").isdigit() and (img.get("height") or "").isdigit(), img
        assert (img.get("src") or "").startswith("https://"), img
    assert 'width="640"' in out
    p = _cells(out)
    assert "table" in p.tags and "div" not in p.tags


def _variant(issue_w44, variant: str):
    return {"w44": issue_w44, "full": _full_issue(issue_w44), "worst": _worst_case(issue_w44)}[
        variant
    ]


@pytest.mark.parametrize("variant", ["w44", "full", "worst"])
def test_every_text_cell_has_korean_font_stack(issue_w44, variant):
    """D-14: the stack sits on the cell or, from template-version 7, its nearest table."""
    p = _cells(render_html(_variant(issue_w44, variant), "구독자님"))
    text_cells = [c for c in p.cells if c["text"].strip()]
    assert len(text_cells) > 40
    for c in text_cells:
        own = "font-family" in c["style"]
        style = c["style"] if own else c["table"]
        assert "IBM Plex Sans KR" in style, c["text"][:40]
        assert "Malgun Gothic" in style, c["text"][:40]


@pytest.mark.parametrize("variant", ["w44", "full", "worst"])
def test_font_on_every_table_and_no_cell_or_span(issue_w44, variant):
    p = _cells(render_html(_variant(issue_w44, variant), "구독자님"))
    assert len(p.presentation) == len(p.styles["table"]) > 10
    for style in p.presentation:
        assert "font-family" in style and "IBM Plex Sans KR" in style, style
    for tag in ("td", "span"):
        assert p.styles[tag]
        for style in p.styles[tag]:
            assert "font-family" not in style, (tag, style)


def test_font_family_count_in_worst_case(issue_w44):
    """D-14: per-table stack. Per-cell (template-version 6) rendered 215 declarations."""
    n = render_html(_worst_case(issue_w44), "구독자님").count("font-family")
    print(f"worst-case font-family declarations={n}")
    assert n <= 60


class _Visible(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data):
        self.parts.append(data)


def _visible_text(out: str) -> str:
    p = _Visible()
    p.feed(out)
    p.close()
    return " ".join(" ".join(p.parts).split())


# sha256 of the visible text (tags stripped, whitespace normalized) rendered with the
# per-cell font stack, captured at 03-05 Task 1 (commit 4edc407) before the D-14 move.
# A fixture or copy change moves these on purpose: re-check the text, then recompute.
# Recomputed for schema v4 (어떻게 만들지 -> 어떻게 써 볼지; the only text change).
# Recomputed for the brand rename (모닥로그 AI 리포트, 이번 주 리포트는; the only text change).
# Recomputed for the 04-01 web links (웹에서 보기 / 지난 호 보기; the only text change).
# Recomputed after the owner removed 웹에서 보기 (header and footer; the only text change).
PER_CELL_VISIBLE_SHA256 = {
    "w44": "d648ac4eb899bed7b39ac0be88a4626ac7761e14aa349eb52c750249a8545e05",
    "full": "3437f9db9defb7a89d29e97cd1adea6436d91fbbcaa0c386db0dac52e62b0c64",
    "worst": "7bfd63b0427fd9e21e02298b477bf8fd7ae97b565f3c9c3ff81f0b16b8f78139",
}


@pytest.mark.parametrize("variant", ["w44", "full", "worst"])
def test_font_move_keeps_visible_text_identical(issue_w44, variant):
    text = _visible_text(render_html(_variant(issue_w44, variant), "구독자님"))
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    assert digest == PER_CELL_VISIBLE_SHA256[variant]


def test_ai_type_appears_in_each_card(issue_w44):
    types = ["LLM", "비전", "멀티모달", "음성", "에이전트", "이미지/비디오 생성", "기타"]
    items = [
        it.model_copy(update={"ai_type": types[i % len(types)]})
        for i, it in enumerate(issue_w44.items)
    ]
    issue = issue_w44.model_copy(update={"items": items})
    cards = render_html(issue, "구독자님").split("data-card=")[1:]
    for it, card in zip(items, cards, strict=True):
        assert it.ai_type in card, it.rank


def test_absent_links_are_omitted_and_present_links_exact(issue_w44):
    issue = _with_item(issue_w44, 0, github_url=None, project_url=None)
    issue = _with_item(
        issue, 1, github_url="https://github.com/acme/repo", project_url="https://acme.example/p"
    )
    out = render_html(issue, "구독자님")
    cards = out.split("data-card=")[1:]
    assert len(cards) == 10
    assert "코드 →" not in cards[0] and "프로젝트 →" not in cards[0]
    assert re.search(r'href="https://github\.com/acme/repo"[^>]*>코드 →<', cards[1])
    assert re.search(r'href="https://acme\.example/p"[^>]*>프로젝트 →<', cards[1])
    for it, card in zip(issue.items, cards, strict=True):
        assert re.search(rf'href="{re.escape(it.hf_url)}"[^>]*>논문 보기 →<', card), it.rank


def _ordered(text: str, parts: list[str]) -> bool:
    pos = [text.index(p) for p in parts]
    return pos == sorted(pos)


def test_card_content_in_figma_order(issue_w44):
    issue = _with_item(issue_w44, 1, image=issue_w44.items[0].image)
    cards = _cards(render_html(issue, "구독자님"))
    it = issue.items[1]
    esc = lambda s: html_lib.escape(s, quote=False)
    assert _ordered(
        cards[1],
        [
            "<img",
            _meta(it),
            f">{esc(it.title_ko)}<",
            f">{esc(it.title_en)}<",
            f">{esc(it.summary_ko)}<",
            "· " + esc(it.summary_lines_ko[0]),
            "💡 " + esc(it.use_idea_ko),
            "🧩 모델 정보",
            "논문 보기 →",
        ],
    )
    assert "활용 아이디어" not in "".join(cards)


def test_every_item_image_is_on_its_own_card(issue_w44):
    # D-08: each card shows its own image at the top, card 1 included (no hero).
    assert issue_w44.items[0].image is not None
    img2 = ItemImage(
        url="https://raw.githubusercontent.com/acme/repo/main/assets/teaser.png",
        width=576,
        height=300,
    )
    issue = _with_item(issue_w44, 1, image=img2)
    out = render_html(issue, "구독자님")
    cards = _cards(out)
    for it, card in zip(issue.items, cards, strict=True):
        if it.image is None:
            continue
        imgs = _imgs(card)
        assert len(imgs) == 1, it.rank
        assert imgs[0]["src"] == it.image.url
        assert imgs[0]["alt"] == f"{it.title_ko} 대표 그림"
        assert imgs[0]["width"] == str(it.image.width)
        assert imgs[0]["height"] == str(it.image.height)
        assert card.index("<img") < card.index(_meta(it)), it.rank
        assert out.count(it.image.url) == 1, it.rank


def test_card_without_image_has_no_img(issue_w44):
    cards = _cards(render_html(issue_w44, "구독자님"))
    for it, card in zip(issue_w44.items, cards, strict=True):
        if it.image is None:
            assert "<img" not in card, it.rank


def test_no_verdict_line_while_all_verdicts_unknown(issue_w44):
    out = render_html(issue_w44, "구독자님")
    for word in ("PoC", "Claude/GPT"):
        assert word not in out
    for card in _cards(out):
        for word in ("💼", "🧪", "🖥️", "🤖", "상업", "라이선스"):
            assert word not in card
    assert "🧪" not in render_text(issue_w44, "구독자님")


def test_verdict_line_shows_only_poc_when_only_poc_known(issue_w44):
    it = issue_w44.items[4]
    issue = _with_item(issue_w44, 4, poc=it.poc.model_copy(update={"verdict": "바로 가능"}))
    cards = _cards(render_html(issue, "구독자님"))
    assert ">🧪 바로 써볼 수 있어요<" in cards[4]
    for word in ("💼", "🖥️", "🤖", "확인 필요", "PoC"):
        assert word not in cards[4]
    assert _ordered(cards[4], ["🧩 모델 정보", "🧪 바로 써볼 수 있어요", "논문 보기 →"])
    for i, card in enumerate(cards):
        if i != 4:
            assert "🧪" not in card
    txt = render_text(issue, "구독자님")
    assert "\n🧪 바로 써볼 수 있어요\n" in txt


def test_highlight_pick_content(issue_w44):
    out = render_html(_full_issue(issue_w44), "구독자님")
    block = out[_section_pos(out, "highlight") : _section_pos(out, "top3")]
    assert "이번 주 바로 써볼 만한 것 ✨" in block
    assert ">Claude Skill<" in block
    assert html_lib.escape(issue_w44.items[1].title_ko, quote=False) in block
    assert "왜 좋은지: 왜 좋은지 문장" in block
    assert "어떻게 써 볼지: 만드는 법 문장" in block
    assert "otter-tool.png" in block


def test_highlight_demo_link_v4(issue_w44):
    space = "https://huggingface.co/spaces/org/demo"
    page = "https://example.org/project"
    picks = [
        Highlight(rank=1, tag="데모", why_ko="왜요.", how_ko="해 봐요.", demo_url=space),
        Highlight(
            rank=2, tag="Claude/GPT 에이전트", why_ko="왜요.", how_ko="해 봐요.", demo_url=page
        ),
        Highlight(rank=3, tag="GPTs", why_ko="왜요.", how_ko="해 봐요."),
    ]
    issue = issue_w44.model_copy(update={"highlights": picks})
    out = render_html(issue, "구독자님")
    block = out[_section_pos(out, "highlight") : _section_pos(out, "top3")]
    assert ">데모<" in block and ">Claude/GPT 에이전트<" in block
    assert f'href="{space}"' in block and "데모 써보기 →" in block
    assert f'href="{page}"' in block and "프로젝트 페이지 →" in block
    assert block.count("→") == 2  # no link row without a demo_url
    txt = render_text(issue, "구독자님")
    assert f"데모 써보기: {space}" in txt and f"프로젝트 페이지: {page}" in txt


def test_explainer_title_is_left_aligned(issue_w44):
    # Owner request 2026-11-04: the 칸 title moved from center to left.
    full = render_html(_full_issue(issue_w44), "구독자님")
    block = full[_section_pos(full, "explainer") : _section_pos(full, "rest")]
    head = block[: block.index("AI 기술 쉽게 보기 🔍")]
    cell = head[head.rindex("<td") :]
    assert 'align="left"' in cell and "center" not in cell


def test_explainer_point_and_example_boxes_only_when_set(issue_w44):
    full = render_html(_full_issue(issue_w44), "구독자님")
    block = full[_section_pos(full, "explainer") : _section_pos(full, "rest")]
    assert _ordered(block, ["AI 기술 쉽게 보기 🔍", "오늘의 포인트", "핵심 한 줄", "MoE 해설"])
    assert _ordered(block, ["전문가 혼합 설명", "예를 들어", "예시 문장"])
    assert "otter-chalkboard.png" in block
    bare = issue_w44.model_copy(
        update={"explainer": Explainer(topic="MoE 해설", body_ko="본문", related_ranks=[1])}
    )
    out = render_html(bare, "구독자님")
    assert "오늘의 포인트" not in out and "예를 들어" not in out
    assert "MoE 해설" in out and "본문" in out


def test_text_part_card_format(issue_w44):
    issue = _with_item(
        issue_w44,
        1,
        github_url="https://github.com/acme/repo",
        project_url="https://acme.example/p",
    )
    txt = render_text(issue, "구독자님")
    for it in issue.items:
        assert _meta(it) in txt
        assert f"논문: {it.hf_url}" in txt
        assert f"arXiv: {it.arxiv_url}" in txt
    assert "코드: https://github.com/acme/repo" in txt
    assert "1위 ㅣ 멀티모달 ㅣ ▲ 153" in txt  # no repo: upvotes
    assert "4위 ㅣ 멀티모달 ㅣ ★ 445" in txt
    assert "프로젝트: https://acme.example/p" in txt
    for it in issue.items:
        assert f"· {it.summary_lines_ko[2]}\n💡 {it.use_idea_ko}\n" in txt, it.rank


def test_text_part_phase3_slots(issue_w44):
    txt = render_text(_full_issue(issue_w44), "구독자님")
    for s in (
        "이번 주 바로 써볼 만한 것 ✨",
        "왜 좋은지: 왜 좋은지 문장",
        "어떻게 써 볼지: 만드는 법 문장",
        "이번 주 흐름 한눈에 📈",
        "이번 주 트렌드 문장",
        "AI 기술 쉽게 보기 🔍",
        "오늘의 포인트",
        "핵심 한 줄",
        "예를 들어",
        "예시 문장",
    ):
        assert s in txt, s
    assert _ordered(txt, ["흐름 한눈에", "바로 써볼 만한", "Top 3", "AI 기술 쉽게", "4위부터"])


def test_affiliation_not_rendered_in_html(issue_w44):
    # D-05 card order has no affiliation row.
    issue = _with_item(issue_w44, 1, affiliation="Acme Research Lab")
    assert "Acme Research Lab" not in render_html(issue, "구독자님")


def test_card_has_three_lines_and_info_rows(issue_w44):
    cards = render_html(issue_w44, "구독자님").split("data-card=")[1:]
    assert len(cards) == 10
    for it, card in zip(issue_w44.items, cards, strict=True):
        a, b, c = (html_lib.escape(s, quote=False) for s in it.summary_lines_ko)
        idea = html_lib.escape(it.use_idea_ko, quote=False)
        # D-22: the idea sits inside the 3-line cell, after the three lines.
        assert f"· {a}<br>· {b}<br>· {c}<br>💡 {idea}</td>" in card
        assert "🧩 모델 정보" in card
        for label, _ in _known_info(it):
            assert f">{label}<" in card, label
        assert "활용 아이디어" not in card


def test_greeting_is_escaped(issue_w44):
    out = render_html(issue_w44, "<b>x</b>님")
    assert "<b>x</b>" not in out
    assert "&lt;b&gt;x&lt;/b&gt;님" in out


def test_title_script_is_escaped(issue_w44):
    issue = _with_item(issue_w44, 2, title_ko='<script>alert("x")</script> 제목')
    out = render_html(issue, "구독자님")
    assert "<script" not in out
    assert "&lt;script&gt;" in out


def test_explainer_renders_in_its_slot_when_set(issue_w44):
    issue = issue_w44.model_copy(
        update={
            "explainer": Explainer(topic="MoE 해설", body_ko="전문가 혼합 설명", related_ranks=[1])
        }
    )
    out = render_html(issue, "구독자님")
    ex = _section_pos(out, "explainer")
    assert _section_pos(out, "top3") < ex < _section_pos(out, "rest")
    block = out[ex : _section_pos(out, "rest")]
    assert "MoE 해설" in block
    assert "전문가 혼합 설명" in block
    assert out.count("data-card=") == 10


def test_trend_renders_only_when_set(issue_w44):
    issue = issue_w44.model_copy(update={"trend_ko": "이번 주 트렌드 문장"})
    out = render_html(issue, "구독자님")
    tr = _section_pos(out, "trend")
    assert "이번 주 트렌드 문장" in out[tr : _section_pos(out, "top3")]
    assert "이번 주 흐름 한눈에 📈" in out
    plain = render_html(issue_w44, "구독자님")
    assert 'data-section="trend"' not in plain
    assert "이번 주 흐름 한눈에" not in plain


def _info_box(card: str) -> str | None:
    if "data-model-info=" not in card:
        return None
    return card.split("data-model-info=")[1].split("</table>")[0]


def _known_info(it) -> list[tuple[str, str]]:
    mi = it.model_info
    values = (mi.kind_ko, mi.architecture_ko, mi.size, mi.training_data, mi.release)
    return [(lb, v) for lb, v in zip(INFO_LABELS, values, strict=True) if v != UNKNOWN]


def test_info_rows_hidden_when_unknown(issue_w44):
    # D-10: rank 1 has size, training data and release unknown.
    it = issue_w44.items[0]
    mi = it.model_info
    assert (mi.size, mi.training_data, mi.release) == (UNKNOWN,) * 3
    assert UNKNOWN not in (mi.kind_ko, mi.architecture_ko)
    box = _info_box(_cards(render_html(issue_w44, "구독자님"))[0])
    assert "🧩 모델 정보" in box
    assert ">유형<" in box and ">구조<" in box
    for label in ("크기", "학습 데이터", "공개 범위"):
        assert f">{label}<" not in box, label
    rows = box.split("<tr>")[2:]
    assert len(rows) == 2
    pads = ("padding: 4px 0 14px 16px", "padding: 4px 16px 14px 0")
    assert not any(p in rows[0] for p in pads)
    assert all(p in rows[1] for p in pads)  # last visible row gets the bottom padding


def test_info_rows_hidden_drops_box_when_all_unknown(issue_w44):
    mi = issue_w44.items[6].model_info.model_copy(
        update={"kind_ko": UNKNOWN, "architecture_ko": UNKNOWN}
    )
    issue = _with_item(issue_w44, 6, model_info=mi)
    cards = _cards(render_html(issue, "구독자님"))
    assert "data-model-info=" not in cards[6]
    assert "🧩 모델 정보" not in cards[6]
    assert all("🧩 모델 정보" in c for i, c in enumerate(cards) if i != 6)
    txt = render_text(issue, "구독자님")
    assert txt.count("🧩 모델 정보") == 9


@pytest.mark.parametrize("full", [False, True])
def test_info_rows_hidden_never_show_needs_check(issue_w44, full):
    issue = _full_issue(issue_w44) if full else issue_w44
    cards = _cards(render_html(issue, "구독자님"))
    for it, card in zip(issue.items, cards, strict=True):
        box = _info_box(card) or ""
        assert UNKNOWN not in box, it.rank
        for label, value in _known_info(it):
            assert f">{label}<" in box and html_lib.escape(value, quote=False) in box


def test_info_rows_hidden_in_text_part(issue_w44):
    txt = render_text(issue_w44, "구독자님")
    assert UNKNOWN not in txt  # verdict badges are also hidden in W44
    for it in issue_w44.items:
        for label, value in _known_info(it):
            assert f"{label}: {value}" in txt, (it.rank, label)


# ---------------------------------- Task 3 size gate, text part and subject


def test_w44_html_under_byte_limit(issue_w44):
    n = len(render_html(issue_w44, "구독자님").encode("utf-8"))
    print(f"W44 email.html bytes={n}")
    assert MAX_EMAIL_BYTES == 90 * 1024
    assert n < MAX_EMAIL_BYTES


def test_oversized_html_raises_with_byte_count_only(issue_w44):
    pad = "아주 긴 요약 문장입니다. " * 600
    items = [it.model_copy(update={"summary_ko": pad}) for it in issue_w44.items]
    issue = issue_w44.model_copy(update={"items": items})
    with pytest.raises(RenderTooLarge) as exc:
        render_html(issue, "구독자님")
    assert re.fullmatch(r"bytes=\d+", str(exc.value))
    assert int(str(exc.value).split("=")[1]) >= 90 * 1024


def test_render_text_has_all_content_and_no_tags(issue_w44):
    issue = issue_w44
    txt = render_text(issue, "구독자님")
    assert "구독자님" in txt
    assert not re.search(r"<[a-zA-Z/][^>]*>", txt)
    for it in issue.items:
        for s in (it.title_ko, it.title_en, it.summary_ko):
            assert s in txt
        for line in it.summary_lines_ko:
            assert f"· {line}" in txt
        for _, value in _known_info(it):
            assert value in txt
        for url in (it.hf_url, it.arxiv_url, it.github_url, it.project_url):
            if url:
                assert url in txt


def test_subject_is_headline_in_send_and_preview(issue_w44):
    for mode in ("send", "preview"):
        assert build_subject(issue_w44, mode) == issue_w44.headline_ko


def test_subject_test_prefix_only_in_test_mode(issue_w44):
    assert build_subject(issue_w44, "test") == "[TEST] " + issue_w44.headline_ko
    for mode in ("send", "preview"):
        assert not build_subject(issue_w44, mode).startswith("[TEST]")


def test_subject_has_no_brand_prefix(issue_w44):
    for mode in ("test", "send", "preview"):
        assert "[모닥로그 AI 리포트]" not in build_subject(issue_w44, mode)


def test_subject_has_no_line_breaks(issue_w44):
    issue = issue_w44.model_copy(update={"headline_ko": "줄\r\n바꿈\n헤드라인"})
    for mode in ("test", "send", "preview"):
        s = build_subject(issue, mode)
        assert "\r" not in s and "\n" not in s
        assert "바꿈" in s and "헤드라인" in s


# ------------------- Task 3 guards: images, images-off, wording, worst case


AUTHORSHIP_PHRASES = (
    "자동으로 생성",
    "자동 생성",
    "자동으로 작성",
    "AI가 작성",
    "AI가 생성",
    "AI가 만든",
    "Claude가",
    "Claude로",
    "generated",
)
SECTION_TITLES = (
    "이번 주 바로 써볼 만한 것 ✨",
    "이번 주 흐름 한눈에 📈",
    "이것만 보면 끝! 이번 주 AI 모델 Top 3 ⚡️",
    "AI 기술 쉽게 보기 🔍",
    "놓치기 아까운 4위부터 10위까지 👀",
    "이번 주 리포트는 여기까지! 다음 주 월요일에 또 만나요 👋",
)
INFO_LABELS = ("유형", "구조", "크기", "학습 데이터", "공개 범위")


def _raw_image_url(rank: int) -> str:
    """A README image on raw.githubusercontent.com at the schema's 300-char cap."""
    head = f"https://raw.githubusercontent.com/some-organization/some-long-repo-{rank:02d}/main/"
    url = head + "f" * (IMAGE_URL_MAX - len(head) - len(".png")) + ".png"
    assert len(url) == IMAGE_URL_MAX == 300
    return url


def _raw_explainer_url() -> str:
    """The explainer's code-copied image at the 300-char cap, distinct from every card URL."""
    head = "https://raw.githubusercontent.com/some-organization/some-explainer-repo/main/"
    url = head + "e" * (IMAGE_URL_MAX - len(head) - len(".png")) + ".png"
    assert len(url) == IMAGE_URL_MAX == 300
    return url


def _license_url(rank: int) -> str:
    head = f"https://huggingface.co/some-organization/some-long-model-name-{rank:02d}/blob/main/"
    url = head + "L" * (EVIDENCE_LINK_MAX - len(head) - len(".md")) + ".md"
    assert len(url) == EVIDENCE_LINK_MAX == 200
    return url


def _longest_commercial() -> dict:
    """Commercial fields that produce the phrase with the most UTF-8 bytes."""
    lic = LicenseInfo(spdx_id="Apache-2.0")
    options = {
        COMMERCIAL_PHRASES["가능"]: {"verdict": "가능", "weights_license": lic},
        COMMERCIAL_CODE_ONLY_PHRASE: {"verdict": "가능", "code_license": lic},
        COMMERCIAL_PHRASES["조건부"]: {"verdict": "조건부", "weights_license": lic},
        COMMERCIAL_PHRASES["불가"]: {"verdict": "불가", "weights_license": lic},
    }
    return options[max(options, key=lambda p: len(p.encode("utf-8")))]


def _longest_claude_gpt() -> str:
    return max(CLAUDE_GPT_PHRASES, key=lambda v: len(CLAUDE_GPT_PHRASES[v].encode("utf-8")))


def _worst_verdicts(it, rank: int) -> dict:
    ev = [EvidenceLink(label="라이선스", url=_license_url(rank))]
    model = EvidenceLink(label=POC_GATED_LABEL, url=f"https://huggingface.co/org/m{rank}")
    return {
        "commercial": it.commercial.model_copy(update={**_longest_commercial(), "evidence": ev}),
        "poc": it.poc.model_copy(update={"verdict": "바로 가능", "evidence": [model]}),
        "hardware": it.hardware.model_copy(
            update={"est_vram_gb": 999.0, "local_run": "불가", "evidence": [model]}
        ),
        "claude_gpt": it.claude_gpt.model_copy(update={"verdict": _longest_claude_gpt()}),
    }


def _worst_case(issue):
    """v1.2 worst case (DSGN-08): 10 card images and no hero, every link, max-length fields,
    50-char ideas, 99,999 stars, all Phase 3 slots.

    Titles stay as in W44. Every 모델 정보 value is known, so all five rows render.
    Phase 2: every card carries all four verdicts at their longest phrase and a
    200-char license link.
    """
    ids = ", ".join(f"org-name/{'d' * 30}{n}" for n in range(3))  # 3 x 40 chars
    assert all(len(x) == 40 for x in ids.split(", "))
    items = []
    for it in issue.items:
        r = it.rank
        mi = it.model_info.model_copy(
            update={
                "kind_ko": "유" * 30,
                "architecture_ko": "구" * 60,
                "size": "123.4B 파라미터 (외 9개 모델)",
                "training_data": ids + " 외 99개",
                "release": "가중치(승인 필요) · GitHub · 데모",
            }
        )
        items.append(
            it.model_copy(
                update={
                    "image": ItemImage(url=_raw_image_url(r), width=576, height=260),
                    "use_idea_ko": "활" * 50,
                    "github_stars": 99999,
                    "github_url": f"https://github.com/some-organization/some-long-repository-name-{r}",
                    "project_url": f"https://some-organization.github.io/some-long-project-page-{r}/",
                    "summary_ko": "요" * 80,
                    "summary_lines_ko": ["줄" * 70, "새" * 70, "결" * 70],
                    "model_info": mi,
                    **_worst_verdicts(it, r),
                }
            )
        )
    return issue.model_copy(
        update={
            "items": items,
            "headline_ko": "🤖 " + "헤" * 40,
            "highlights": [
                Highlight(rank=r, tag="둘 다", why_ko="왜" * 120, how_ko="어" * 160)
                for r in (1, 2, 3)
            ],
            "trend_ko": "흐" * 300,
            "explainer": Explainer(
                topic="주" * 40,
                body_ko="본" * 800,
                related_ranks=[1, 2],
                point_ko="포" * 120,
                example_ko="예" * 200,
                image=ItemImage(url=_raw_explainer_url(), width=576, height=260),
            ),
        }
    )


def _check_imgs(out: str) -> list[dict]:
    imgs = _imgs(out)
    assert imgs
    for img in imgs:
        assert (img.get("alt") or "").strip(), img
        assert re.fullmatch(r"\d+", img.get("width") or ""), img
        assert re.fullmatch(r"\d+", img.get("height") or ""), img
        assert (img.get("src") or "").startswith("https://"), img
    assert "data:" not in "".join(img.get("src") or "" for img in imgs)
    return imgs


def _otters(imgs: list[dict]) -> set[str]:
    names = set()
    for img in imgs:
        src = img["src"]
        if "otter-" in src:
            assert src.startswith(ASSET_BASE_URL + "/"), src
            names.add(src.rsplit("/", 1)[1])
    return names


def test_w44_images_are_hosted_with_alt_and_size(issue_w44):
    imgs = _check_imgs(render_html(issue_w44, "구독자님"))
    assert _otters(imgs) == {
        "otter-banner.jpg",
        "otter-magnifier.png",
        "otter-wave.jpg",
        "otter-tool.png",  # D-01: the highlight section always renders
    }
    assert ASSET_BASE_URL.startswith("https://")


def test_worst_case_images_and_phase3_otters(issue_w44):
    imgs = _check_imgs(render_html(_worst_case(issue_w44), "구독자님"))
    assert _otters(imgs) == {
        "otter-banner.jpg",
        "otter-magnifier.png",
        "otter-wave.jpg",
        "otter-tool.png",
        "otter-chalkboard.png",
    }
    # 10 card images (D-08) + the explainer image (D-04), none in the hero (D-07)
    raw = [i for i in imgs if i["src"].startswith("https://raw.githubusercontent.com/")]
    assert len(raw) == 11
    assert all(len(i["src"]) == 300 for i in raw)
    out = render_html(_worst_case(issue_w44), "구독자님")
    assert "<img" not in out[_section_pos(out, "hero") : _section_pos(out, "greeting")]
    assert all(c.count("<img") == 1 for c in _cards(out))
    ex_imgs = _imgs(out[_section_pos(out, "explainer") : _section_pos(out, "rest")])
    assert [i["src"].rsplit("/", 1)[1] for i in ex_imgs if "otter-" in i["src"]] == [
        "otter-chalkboard.png"
    ]
    pics = [i for i in ex_imgs if "otter-" not in i["src"]]
    assert len(pics) == 1
    assert pics[0]["src"].startswith(EXPLAINER_IMAGE_HOSTS), pics[0]["src"]
    assert pics[0]["src"] == _raw_explainer_url()
    assert pics[0]["alt"] == "주" * 40 + " 관련 그림"
    assert (pics[0]["width"], pics[0]["height"]) == ("576", "260")


EXPLAINER_IMAGE_HOSTS = (
    "https://raw.githubusercontent.com/",
    "https://cdn-uploads.huggingface.co/",
    "https://arxiv.org/html/",
)


def test_explainer_without_image_has_only_the_otter(issue_w44):
    out = render_html(_full_issue(issue_w44), "구독자님")
    assert _full_issue(issue_w44).explainer.image is None
    block = out[_section_pos(out, "explainer") : _section_pos(out, "rest")]
    imgs = _imgs(block)
    assert [i for i in imgs if "otter-" not in i["src"]] == []
    assert [i["src"].rsplit("/", 1)[1] for i in imgs] == ["otter-chalkboard.png"]
    assert "관련 그림" not in block


def test_explainer_image_sits_after_body_before_example(issue_w44):
    full = _full_issue(issue_w44)
    url = _raw_explainer_url()
    ex = full.explainer.model_copy(update={"image": ItemImage(url=url, width=576, height=260)})
    out = render_html(full.model_copy(update={"explainer": ex}), "구독자님")
    block = out[_section_pos(out, "explainer") : _section_pos(out, "rest")]
    assert _ordered(block, ["전문가 혼합 설명", f'src="{url}"', "예를 들어"])
    assert 'alt="MoE 해설 관련 그림"' in block
    txt = render_text(full.model_copy(update={"explainer": ex}), "구독자님")
    assert "관련 그림" not in txt and url not in txt


def _strip_imgs(out: str) -> str:
    return html_lib.unescape(re.sub(r"<img\b[^>]*>", "", out))


@pytest.mark.parametrize("variant", ["w44", "full", "worst"])
def test_email_reads_with_images_blocked(issue_w44, variant):
    full = variant != "w44"
    issue = {"w44": issue_w44, "full": _full_issue(issue_w44), "worst": _worst_case(issue_w44)}[
        variant
    ]
    text = _strip_imgs(render_html(issue, "구독자님"))
    # W44 has no trend or explainer; the highlight section always renders (D-01).
    titles = SECTION_TITLES if full else (SECTION_TITLES[0], SECTION_TITLES[2], *SECTION_TITLES[4:])
    for t in titles:
        assert t in text, t
    assert issue.headline_ko in text
    for it in issue.items:
        for s in (it.title_ko, it.summary_ko, *it.summary_lines_ko, "💡 " + it.use_idea_ko):
            assert s in text, (it.rank, s)
        known = {label for label, _ in _known_info(it)}
        box = _info_box(text.split(f'data-card="{it.rank}"')[1]) or ""
        for label in INFO_LABELS:
            assert (f">{label}<" in box) == (label in known), (it.rank, label)


def _all_parts(issue) -> list[str]:
    return [
        render_html(issue, "구독자님"),
        render_text(issue, "구독자님"),
        *(build_subject(issue, m) for m in ("test", "send", "preview")),
    ]


def test_no_authorship_wording_anywhere(issue_w44):
    for issue in (issue_w44, _full_issue(issue_w44)):
        for part in _all_parts(issue):
            for phrase in AUTHORSHIP_PHRASES:
                assert phrase not in part, phrase


def test_claude_absent_while_claude_gpt_verdicts_unknown(issue_w44):
    # Pitfall 5: Phase 1.1 only. Phase 2 badges legitimately say Claude/GPT.
    assert all(it.claude_gpt.verdict == "확인 필요" for it in issue_w44.items)
    for part in _all_parts(issue_w44):
        assert "Claude" not in part


ISSUE_URL = "https://silber60.github.io/AI_news_log/issues/2026-W44/"
ARCHIVE_URL = "https://silber60.github.io/AI_news_log/#archive"


def test_site_urls_are_fixed():
    # D-02 and the 04-01 Task 1 owner choice (anchor): baked into every sent email.
    assert render_mod.issue_url(ISSUE_ID) == ISSUE_URL
    assert render_mod.archive_url() == ARCHIVE_URL


def test_email_footer_has_archive_link_and_keeps_reply_line(issue_w44):
    # Owner 2026-11-04: 웹에서 보기 removed from the email (header and footer).
    out = render_html(issue_w44, "구독자님")
    footer = out[_section_pos(out, "footer") :]
    assert "출처: Hugging Face Papers" in footer
    assert "수신거부" in footer
    assert re.search(rf'href="{re.escape(ARCHIVE_URL)}"[^>]*>지난 호 보기<', footer)
    assert "웹에서 보기" not in out and ISSUE_URL not in out
    txt = render_text(issue_w44, "구독자님")
    assert "출처: Hugging Face Papers" in txt and "수신거부" in txt
    assert "웹에서 보기" not in txt and ISSUE_URL not in txt
    assert f"지난 호 보기: {ARCHIVE_URL}" in txt


def test_web_issue_drops_reply_line_and_header_link(issue_w44):
    out = render_mod.render_web_issue(issue_w44)
    footer = out[_section_pos(out, "footer") :]
    assert "수신거부" not in out
    assert "구독 해지는 받으신 메일 아래쪽 링크에서 할 수 있어요." in footer
    assert re.search(rf'href="{re.escape(ARCHIVE_URL)}"[^>]*>지난 호 보기<', footer)
    assert "웹에서 보기" not in out
    assert "구독자님, 안녕하세요." in out


UNSUB_URL = "https://silber60.github.io/AI_news_log/unsubscribe/?t=" + "0123456789abcdef" * 2
# 04-04 Task 1 offered 32 or 64 hex; the size gate uses the longer one.
UNSUB_URL_MAX = "https://silber60.github.io/AI_news_log/unsubscribe/?t=" + "f" * 64


def test_email_footer_has_personal_unsubscribe_link(issue_w44):
    out = render_html(issue_w44, "구독자님", unsubscribe_url=UNSUB_URL)
    footer = out[_section_pos(out, "footer") :]
    assert len(re.findall(rf'<a href="{re.escape(UNSUB_URL)}"[^>]*>구독 해지</a>', footer)) == 1
    assert out.count(UNSUB_URL) == 1
    assert "수신거부" in footer  # D-14: the reply line stays as a fallback
    assert _ordered(footer, ["지난 호 보기", "구독 해지"])
    txt = render_text(issue_w44, "구독자님", unsubscribe_url=UNSUB_URL)
    assert f"구독 해지: {UNSUB_URL}" in txt
    assert "수신거부" in txt


def test_no_unsubscribe_link_without_url(issue_w44):
    out = render_html(issue_w44, "구독자님")
    assert "구독 해지" not in out and "unsubscribe/?t=" not in out
    txt = render_text(issue_w44, "구독자님")
    assert "구독 해지" not in txt and "unsubscribe/?t=" not in txt


def test_web_issue_has_no_unsubscribe_link(issue_w44):
    out = render_mod.render_web_issue(issue_w44)
    assert ">구독 해지<" not in out and "unsubscribe/?t=" not in out


def test_footer_has_no_contact_address(issue_w44):
    # D-15: brand name and send note only; the footer is also on the public web copy.
    for out in (
        render_html(issue_w44, "구독자님", unsubscribe_url=UNSUB_URL),
        render_mod.render_web_issue(issue_w44),
    ):
        assert "@" not in out[_section_pos(out, "footer") :]
    txt = render_text(issue_w44, "구독자님", unsubscribe_url=UNSUB_URL)
    assert "@" not in txt[txt.rindex("이번 주 리포트는 여기까지") :]


def test_worst_case_under_byte_limit(issue_w44):
    worst = _worst_case(issue_w44)
    assert all(len(it.use_idea_ko) == 50 and it.github_stars == 99999 for it in worst.items)
    out = render_html(worst, "구독자님", unsubscribe_url=UNSUB_URL_MAX)
    assert f'href="{UNSUB_URL_MAX}"' in out
    n = len(out.encode("utf-8"))
    print(f"worst-case email.html bytes={n} headroom={MAX_EMAIL_BYTES - n}")
    assert "★ 99,999" in out
    assert out.count("💡 " + "활" * 50) == 10
    for it, card in zip(worst.items, _cards(out), strict=True):
        line = " · ".join(verdict_line(it))
        assert len(verdict_line(it)) == 4, it.rank
        assert line in card, it.rank
        assert f'href="{_license_url(it.rank)}"' in card, it.rank
        assert ">라이선스</a>" in card, it.rank
    assert n < MAX_EMAIL_BYTES


@pytest.mark.parametrize("web", [False, True])
def test_color_scheme_is_light_only(issue_w44, web):
    """D-16, DSGN-05: ask clients to keep the light design; ship no dark-mode CSS."""
    if web:
        out = render_mod.render_web_issue(issue_w44)
    else:
        out = render_html(_worst_case(issue_w44), "구독자님", unsubscribe_url=UNSUB_URL_MAX)
    head = out[: out.index("</head>")]
    assert head.count('<meta name="color-scheme" content="light">') == 1
    assert head.count('<meta name="supported-color-schemes" content="light">') == 1
    assert "prefers-color-scheme" not in out
    assert "color-scheme: dark" not in out


def test_text_part_complete_and_asset_free(issue_w44):
    issue = issue_w44
    txt = render_text(issue, "구독자님")
    assert not re.search(r"<[a-zA-Z/][^>]*>", txt)
    assert "구독자님, 안녕하세요." in txt
    assert issue.headline_ko in txt
    for it in issue.items:
        for s in (it.title_ko, it.title_en, it.summary_ko):
            assert s in txt
        for line in it.summary_lines_ko:
            assert f"· {line}" in txt
        for label, value in _known_info(it):
            assert f"{label}: {value}" in txt
        assert it.hf_url in txt and it.arxiv_url in txt
    assert ASSET_BASE_URL not in txt
    assert "otter-" not in txt
    assert "cdn-uploads.huggingface.co" not in txt


def test_ibm_plex_font_first_and_web_font_link(issue_w44):
    from newsletter.stages.render import FONT_STACK, WEB_FONT_URL, render_html

    assert FONT_STACK.startswith("'IBM Plex Sans KR'")
    html = render_html(issue_w44, "구독자")
    assert f'<link rel="stylesheet" href="{WEB_FONT_URL}"' in html.replace("&amp;", "&")
    assert "<style" not in html  # css_inline still drops the style block


# --------------------------------------------- Phase 2 verdict line (D-01, D-02)

LIC = LicenseInfo(spdx_id="Apache-2.0")
HF_LIC = "https://huggingface.co/org/m/blob/main/LICENSE"


def _verdicts(it, *, commercial=None, poc=None, hardware=None, claude_gpt=None):
    update = {}
    for name, val in (
        ("commercial", commercial),
        ("poc", poc),
        ("hardware", hardware),
        ("claude_gpt", claude_gpt),
    ):
        if val is not None:
            update[name] = getattr(it, name).model_copy(update=val)
    return it.model_copy(update=update)


@pytest.mark.parametrize(
    ("fields", "phrase"),
    [
        ({"verdict": "가능", "code_license": LIC}, "💼 코드 상업 이용 가능"),  # D-09
        ({"verdict": "가능", "weights_license": LIC}, "💼 상업 이용 가능"),
        ({"verdict": "가능", "weights_license": LIC, "code_license": LIC}, "💼 상업 이용 가능"),
        ({"verdict": "조건부", "weights_license": LIC}, "💼 조건부 상업 이용"),
        ({"verdict": "불가", "weights_license": LIC}, "💼 상업 이용 불가"),
        ({"verdict": "확인 필요"}, None),
    ],
)
def test_verdict_line_commercial_phrases(issue_w44, fields, phrase):
    line = verdict_line(_verdicts(issue_w44.items[0], commercial=fields))
    assert line == ([phrase] if phrase else [])


@pytest.mark.parametrize(
    ("verdict", "phrase"),
    [
        ("직접 사용", "🤖 Claude/GPT에서 바로 써요"),
        ("기법 적용 가능", "🤖 Claude/GPT 기법 적용"),
        ("해당 없음", None),  # D-11: hidden in the email
        ("확인 필요", None),
    ],
)
def test_verdict_line_claude_gpt_phrases(issue_w44, verdict, phrase):
    line = verdict_line(_verdicts(issue_w44.items[0], claude_gpt={"verdict": verdict}))
    assert line == ([phrase] if phrase else [])


@pytest.mark.parametrize(
    ("hw", "phrase"),
    [
        ({"local_run": "가능", "est_vram_gb": 0.7}, "🖥️ 개인 GPU 약 1GB"),
        ({"local_run": "제한적", "est_vram_gb": 28.6}, "🖥️ 서버 GPU 약 29GB"),
        ({"local_run": "불가", "est_vram_gb": 174.5}, "🖥️ GPU 여러 장 필요 (약 175GB)"),
        ({"local_run": "확인 필요", "est_vram_gb": None}, None),
    ],
)
def test_verdict_line_gpu_phrases(issue_w44, hw, phrase):
    line = verdict_line(_verdicts(issue_w44.items[0], hardware=hw))
    assert line == ([phrase] if phrase else [])


def test_verdict_line_gated_poc_phrase(issue_w44):
    ev = [EvidenceLink(label=POC_GATED_LABEL, url="https://huggingface.co/org/m")]
    it = _verdicts(issue_w44.items[0], poc={"verdict": "바로 가능", "evidence": ev})
    assert verdict_line(it) == ["🧪 승인 받고 써볼 수 있어요"]


def _all_known(it, url=HF_LIC):
    return _verdicts(
        it,
        commercial={
            "verdict": "조건부",
            "weights_license": LIC,
            "evidence": [EvidenceLink(label="라이선스", url=url)],
        },
        poc={"verdict": "코드만"},
        hardware={"local_run": "가능", "est_vram_gb": 6.3},
        claude_gpt={"verdict": "기법 적용 가능"},
    )


def test_verdict_line_order_and_join(issue_w44):
    issue = _with_item(issue_w44, 1, **dict(_all_known(issue_w44.items[1])))
    line = (
        "💼 조건부 상업 이용 · 🧪 코드만 공개됐어요 · 🖥️ 개인 GPU 약 7GB · 🤖 Claude/GPT 기법 적용"
    )
    assert verdict_line(issue.items[1]) == line.split(" · ")
    card = _cards(render_html(issue, "구독자님"))[1]
    assert line in card
    assert _ordered(card, ["🧩 모델 정보", line, "논문 보기 →"])
    txt = render_text(issue, "구독자님")
    assert f"\n{line}\n라이선스: {HF_LIC}\n" in txt


def test_license_link_one_per_card_when_commercial_shown(issue_w44):
    it = _all_known(issue_w44.items[1])
    assert license_link(it) == HF_LIC
    issue = _with_item(issue_w44, 1, **dict(it))
    cards = _cards(render_html(issue, "구독자님"))
    assert cards[1].count(">라이선스</a>") == 1
    assert re.search(
        rf'· <a href="{re.escape(HF_LIC)}" style="[^"]*color: #A3A3A3;?[^"]*">라이선스</a>',
        cards[1],
    )
    assert all("라이선스" not in c for i, c in enumerate(cards) if i != 1)


def test_license_link_absent_without_commercial_phrase(issue_w44):
    it = _all_known(issue_w44.items[1])
    hidden = it.model_copy(
        update={"commercial": it.commercial.model_copy(update={"verdict": "확인 필요"})}
    )
    assert license_link(hidden) is None
    issue = _with_item(issue_w44, 1, **dict(hidden))
    assert all("라이선스" not in c for c in _cards(render_html(issue, "구독자님")))
    assert "라이선스:" not in render_text(issue, "구독자님")


def test_license_link_skips_long_or_foreign_urls(issue_w44):
    long_url = "https://huggingface.co/" + "x" * (EVIDENCE_LINK_MAX - 22)
    assert len(long_url) == EVIDENCE_LINK_MAX + 1
    it = _all_known(issue_w44.items[1], url=long_url)
    assert license_link(it) is None
    assert verdict_line(it)[0] == "💼 조건부 상업 이용"  # the phrase still shows
    ok = "https://github.com/" + "y" * (EVIDENCE_LINK_MAX - 19)
    assert license_link(_all_known(issue_w44.items[1], url=ok)) == ok
    assert license_link(_all_known(issue_w44.items[1], url="https://example.com/L")) is None


DISCLAIMER = (
    "상업적 사용 판정은 공개 라이선스 정보를 바탕으로 한 참고용이에요. "
    "실제 사용 전 원문을 확인해 주세요."
)


def test_footer_disclaimer_in_both_parts(issue_w44):
    out = render_html(issue_w44, "구독자님")
    assert out.count(DISCLAIMER) == 1
    assert out.index(DISCLAIMER) > _section_pos(out, "footer")
    assert _ordered(out[_section_pos(out, "footer") :], ["출처: Hugging Face Papers", DISCLAIMER])
    txt = render_text(issue_w44, "구독자님")
    assert txt.count(DISCLAIMER) == 1
    assert _ordered(txt, ["출처: Hugging Face Papers", DISCLAIMER])
    for phrase in AUTHORSHIP_PHRASES:
        assert phrase not in DISCLAIMER


def test_trend_order_sits_right_under_greeting(issue_w44):
    # D-13: greeting, trend, highlight in both parts.
    full = _full_issue(issue_w44)
    out = render_html(full, "구독자님")
    assert _sections(out)[3:6] == ["greeting", "trend", "highlight"]
    txt = render_text(full, "구독자님")
    assert _ordered(txt, ["안녕하세요.", "이번 주 흐름 한눈에 📈", "이번 주 바로 써볼 만한 것 ✨"])
