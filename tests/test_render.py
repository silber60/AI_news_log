"""Figma v2 email render (Phase 1.1): sections, cards, email-safe markup, size, text, subject."""

import html as html_lib
import re
from html.parser import HTMLParser

import pytest
import respx
from conftest import FakeAnthropic, mock_hf_week

from newsletter.errors import RenderTooLarge
from newsletter.schema import IMAGE_URL_MAX, UNKNOWN, Explainer, Highlight, ItemImage
from newsletter.stages import render as render_mod
from newsletter.stages.render import (
    ASSET_BASE_URL,
    MAX_EMAIL_BYTES,
    build_subject,
    render_html,
    render_text,
)

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
    "highlight",
    "trend",
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
    out = render_html(issue_w44, "구독자님")
    assert _sections(out) == [
        "banner",
        "header",
        "hero",
        "greeting",
        "top3",
        "rest",
        "closing",
        "footer",
    ]


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
    assert "AI 주간 해달 브리프" in out
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
    """Collect every <td>'s style and its own visible text (nested tables excluded)."""

    def __init__(self):
        super().__init__()
        self.stack: list[dict] = []
        self.cells: list[dict] = []
        self.tags: set[str] = set()

    def handle_starttag(self, tag, attrs):
        self.tags.add(tag)
        if tag == "td":
            self.stack.append({"style": dict(attrs).get("style") or "", "text": ""})

    def handle_endtag(self, tag):
        if tag == "td" and self.stack:
            self.cells.append(self.stack.pop())

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


def test_every_text_cell_has_korean_font_stack(issue_w44):
    p = _cells(render_html(issue_w44, "구독자님"))
    text_cells = [c for c in p.cells if c["text"].strip()]
    assert len(text_cells) > 40
    for c in text_cells:
        assert "Apple SD Gothic Neo" in c["style"], c["text"][:40]
        assert "Malgun Gothic" in c["style"], c["text"][:40]


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


def test_badge_row_hidden_while_all_verdicts_unknown(issue_w44):
    out = render_html(issue_w44, "구독자님")
    for word in ("상업적 사용", "PoC", "Claude/GPT"):
        assert word not in out


def test_badge_row_shows_when_only_poc_known(issue_w44):
    it = issue_w44.items[4]
    issue = _with_item(issue_w44, 4, poc=it.poc.model_copy(update={"verdict": "바로 가능"}))
    cards = _cards(render_html(issue, "구독자님"))
    assert "상업적 사용 확인 필요" in cards[4]
    assert "PoC 바로 가능" in cards[4]
    assert "Claude/GPT 확인 필요" in cards[4]
    assert _ordered(cards[4], ["🧩 모델 정보", "PoC 바로 가능", "논문 보기 →"])
    for i, card in enumerate(cards):
        if i != 4:
            assert "PoC" not in card


def test_highlight_pick_content(issue_w44):
    out = render_html(_full_issue(issue_w44), "구독자님")
    block = out[_section_pos(out, "highlight") : _section_pos(out, "trend")]
    assert "이번 주 바로 써볼 만한 것 ✨" in block
    assert ">Claude Skill<" in block
    assert html_lib.escape(issue_w44.items[1].title_ko, quote=False) in block
    assert "왜 좋은지: 왜 좋은지 문장" in block
    assert "어떻게 만들지: 만드는 법 문장" in block
    assert "otter-tool.png" in block


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
        "어떻게 만들지: 만드는 법 문장",
        "이번 주 흐름 한눈에 📈",
        "이번 주 트렌드 문장",
        "AI 기술 쉽게 보기 🔍",
        "오늘의 포인트",
        "핵심 한 줄",
        "예를 들어",
        "예시 문장",
    ):
        assert s in txt, s
    assert _ordered(txt, ["바로 써볼 만한", "흐름 한눈에", "Top 3", "AI 기술 쉽게", "4위부터"])


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
        assert "[AI 주간 해달 브리프]" not in build_subject(issue_w44, mode)


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
    "이번 주 브리프는 여기까지! 다음 주 월요일에 또 만나요 👋",
)
INFO_LABELS = ("유형", "구조", "크기", "학습 데이터", "공개 범위")


def _raw_image_url(rank: int) -> str:
    """A README image on raw.githubusercontent.com at the schema's 300-char cap."""
    head = f"https://raw.githubusercontent.com/some-organization/some-long-repo-{rank:02d}/main/"
    url = head + "f" * (IMAGE_URL_MAX - len(head) - len(".png")) + ".png"
    assert len(url) == IMAGE_URL_MAX == 300
    return url


def _worst_case(issue):
    """v1.2 worst case (DSGN-08): 10 card images and no hero, every link, max-length fields,
    50-char ideas, 99,999 stars, all Phase 3 slots.

    Titles stay as in W44 and verdicts stay 확인 필요 (no badge row) as in Phase 1.1.
    Every 모델 정보 value is known, so all five rows render.
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
    assert _otters(imgs) == {"otter-banner.jpg", "otter-magnifier.png", "otter-wave.jpg"}
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
    # 10 card images (D-08) and none in the hero (D-07)
    raw = [i for i in imgs if i["src"].startswith("https://raw.githubusercontent.com/")]
    assert len(raw) == 10
    assert all(len(i["src"]) == 300 for i in raw)
    out = render_html(_worst_case(issue_w44), "구독자님")
    assert "<img" not in out[_section_pos(out, "hero") : _section_pos(out, "greeting")]
    assert all(c.count("<img") == 1 for c in _cards(out))


def _strip_imgs(out: str) -> str:
    return html_lib.unescape(re.sub(r"<img\b[^>]*>", "", out))


@pytest.mark.parametrize("variant", ["w44", "full", "worst"])
def test_email_reads_with_images_blocked(issue_w44, variant):
    full = variant != "w44"
    issue = {"w44": issue_w44, "full": _full_issue(issue_w44), "worst": _worst_case(issue_w44)}[
        variant
    ]
    text = _strip_imgs(render_html(issue, "구독자님"))
    titles = SECTION_TITLES if full else SECTION_TITLES[2:3] + SECTION_TITLES[4:]
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


def test_footer_source_and_unsubscribe_without_web_links(issue_w44):
    assert render_mod.WEB_URL is None
    out = render_html(issue_w44, "구독자님")
    footer = out[_section_pos(out, "footer") :]
    assert "출처: Hugging Face Papers" in footer
    assert "수신거부" in footer
    txt = render_text(issue_w44, "구독자님")
    for part in (out, txt):
        assert "웹에서 보기" not in part
        assert "지난 호 보기" not in part
    assert "출처: Hugging Face Papers" in txt and "수신거부" in txt


def test_web_links_appear_once_web_url_is_set(issue_w44, monkeypatch):
    monkeypatch.setattr(render_mod, "WEB_URL", "https://example.github.io/archive/")
    out = render_html(issue_w44, "구독자님")
    footer = out[_section_pos(out, "footer") :]
    assert "웹에서 보기" in footer and "지난 호 보기" in footer
    header = out[_section_pos(out, "header") : _section_pos(out, "hero")]
    assert "웹에서 보기" in header
    assert 'href="https://example.github.io/archive/"' in out
    txt = render_text(issue_w44, "구독자님")
    assert "웹에서 보기" in txt and "지난 호 보기" in txt


def test_worst_case_under_byte_limit(issue_w44):
    worst = _worst_case(issue_w44)
    assert all(len(it.use_idea_ko) == 50 and it.github_stars == 99999 for it in worst.items)
    out = render_html(worst, "구독자님")
    n = len(out.encode("utf-8"))
    print(f"worst-case email.html bytes={n} headroom={MAX_EMAIL_BYTES - n}")
    assert "★ 99,999" in out
    assert out.count("💡 " + "활" * 50) == 10
    assert n < MAX_EMAIL_BYTES


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
