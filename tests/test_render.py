"""Figma v2 email render (Phase 1.1): sections, cards, email-safe markup, size, text, subject."""

import html as html_lib
import re
from html.parser import HTMLParser

import pytest
import respx
from conftest import FakeAnthropic, mock_hf_week

from newsletter.errors import RenderTooLarge
from newsletter.schema import Explainer, Highlight
from newsletter.stages.render import (
    MAX_EMAIL_BYTES,
    build_subject,
    render_html,
    render_text,
)

ISSUE_ID = "2026-W44"


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
        assert f"{it.rank}위 ㅣ {it.ai_type} ㅣ ▲ {it.upvotes}" in out
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
    assert out.count("Hugging Face 추천 수 기준") == 2


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
    assert "AI 주간 모델 브리프" in out
    assert "매주 월요일, 실무에 바로 쓸 AI 모델만 골라 드려요" in out


def test_hero_shows_headline_and_rank1_image(issue_w44):
    out = render_html(issue_w44, "구독자님")
    hero = out[_section_pos(out, "hero") : _section_pos(out, "greeting")]
    assert html_lib.escape(issue_w44.headline_ko, quote=False) in hero
    assert issue_w44.items[0].image.url in hero


def test_greeting_line(issue_w44):
    out = render_html(issue_w44, "구독자님")
    assert (
        "구독자님, 안녕하세요. 지난주 Hugging Face Papers에서 "
        "추천을 많이 받은 AI 모델 10개를 골랐어요." in out
    )


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
            f"{it.rank}위 ㅣ {it.ai_type} ㅣ ▲ {it.upvotes}",
            f">{esc(it.title_ko)}<",
            f">{esc(it.title_en)}<",
            f">{esc(it.summary_ko)}<",
            "· " + esc(it.summary_lines_ko[0]),
            "🧩 모델 정보",
            "논문 보기 →",
        ],
    )
    assert "활용 아이디어" not in "".join(cards)


def test_card1_drops_image_when_hero_shows_it(issue_w44):
    assert issue_w44.items[0].image is not None
    issue = _with_item(issue_w44, 1, image=issue_w44.items[0].image)
    out = render_html(issue, "구독자님")
    cards = _cards(out)
    assert "<img" not in cards[0]
    assert "<img" in cards[1]
    hero = out[_section_pos(out, "hero") : _section_pos(out, "greeting")]
    assert out.count(issue_w44.items[0].image.url) == 2  # hero + card 2
    assert issue_w44.items[0].image.url in hero


def test_card_without_image_has_no_img(issue_w44):
    cards = _cards(render_html(issue_w44, "구독자님"))
    for it, card in zip(issue_w44.items, cards, strict=True):
        if it.rank > 1 and it.image is None:
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
        assert f"{it.rank}위 ㅣ {it.ai_type} ㅣ ▲ {it.upvotes}" in txt
        assert f"논문: {it.hf_url}" in txt
        assert f"arXiv: {it.arxiv_url}" in txt
    assert "코드: https://github.com/acme/repo" in txt
    assert "프로젝트: https://acme.example/p" in txt


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
        assert f"· {a}<br>· {b}<br>· {c}" in card
        assert "🧩 모델 정보" in card
        for label in ("유형", "구조", "크기", "학습 데이터", "공개 범위"):
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


def test_unknown_facts_render_as_needs_check(issue_w44):
    out = render_html(issue_w44, "구독자님")
    # D-07: unknown model facts must show as 확인 필요 on the card.
    cards = out.split("data-card=")[1:]
    for it, card in zip(issue_w44.items, cards, strict=True):
        mi = it.model_info
        if "확인 필요" in (mi.architecture_ko, mi.size, mi.training_data, mi.release):
            assert "확인 필요" in card, it.rank


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
        mi = it.model_info
        for s in (it.title_ko, it.title_en, it.summary_ko):
            assert s in txt
        for line in it.summary_lines_ko:
            assert f"· {line}" in txt
        for s in (mi.kind_ko, mi.architecture_ko, mi.size, mi.training_data, mi.release):
            assert s in txt
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
        assert "[AI 주간 모델 브리프]" not in build_subject(issue_w44, mode)


def test_subject_has_no_line_breaks(issue_w44):
    issue = issue_w44.model_copy(update={"headline_ko": "줄\r\n바꿈\n헤드라인"})
    for mode in ("test", "send", "preview"):
        s = build_subject(issue, mode)
        assert "\r" not in s and "\n" not in s
        assert "바꿈" in s and "헤드라인" in s
