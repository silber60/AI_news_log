"""Phase 1 email render: card content, email-safe markup, size gate, text part, subject."""

import html as html_lib
import re
from html.parser import HTMLParser

import httpx
import pytest
import respx
from conftest import FakeAnthropic

from newsletter.errors import RenderTooLarge
from newsletter.schema import Explainer
from newsletter.stages.render import (
    AI_TYPE_COLORS,
    MAX_EMAIL_BYTES,
    SUBJECT_TITLE_MAX,
    build_subject,
    render_html,
    render_text,
)
from newsletter.week import week_label

ISSUE_ID = "2026-W44"


def _build(hf_pages):
    from newsletter.pipeline import run_build

    with respx.mock(assert_all_mocked=True, assert_all_called=True) as router:
        for i, page in enumerate(hf_pages):
            router.get(
                "https://huggingface.co/api/daily_papers",
                params={"week": ISSUE_ID, "limit": "100", "p": str(i)},
            ).mock(return_value=httpx.Response(200, json=page))
        return run_build(ISSUE_ID, claude_client=FakeAnthropic())


# ---------------------------------------------------------------- Task 1 tracer


def test_build_renders_full_card_email(hf_pages, archive_tmp):
    issue = _build(hf_pages)
    out = (archive_tmp / "archive" / ISSUE_ID / "email.html").read_text(encoding="utf-8")

    assert out.count("data-card=") == 10
    for it in issue.items:
        assert html_lib.escape(it.title_ko, quote=False) in out
        assert f"#{it.rank}<" in out
        assert f"▲ {it.upvotes}<" in out
    assert "구독자님" in out
    assert week_label(issue.week_start, issue.week_end) in out


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


def _with_item(issue, idx: int, **update):
    items = list(issue.items)
    items[idx] = items[idx].model_copy(update=update)
    return issue.model_copy(update={"items": items})


def test_no_style_block_and_tables_only(issue_w44):
    out = render_html(issue_w44, "구독자님")
    assert "<style" not in out
    assert "<div" not in out
    assert "<img" not in out
    assert "class=" not in out
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


def test_ai_type_badges_use_color_map(issue_w44):
    types = list(AI_TYPE_COLORS)
    assert len(types) == 7
    items = [
        it.model_copy(update={"ai_type": types[i % len(types)]}) for i, it in enumerate(issue_w44.items)
    ]
    issue = issue_w44.model_copy(update={"items": items})
    cells = _cells(render_html(issue, "구독자님")).cells
    for t in types:
        bg, fg = AI_TYPE_COLORS[t]
        badge = [c for c in cells if c["text"].strip() == t]
        assert badge, t
        for c in badge:
            assert f"background-color: {bg}" in c["style"]
            assert f"color: {fg}" in c["style"]


def test_absent_links_are_omitted_and_present_links_exact(issue_w44):
    issue = _with_item(issue_w44, 0, github_url=None, project_url=None)
    issue = _with_item(
        issue, 1, github_url="https://github.com/acme/repo", project_url="https://acme.example/p"
    )
    out = render_html(issue, "구독자님")
    cards = out.split("data-card=")[1:]
    assert len(cards) == 10
    assert ">GitHub<" not in cards[0] and ">Project<" not in cards[0]
    assert 'href="https://github.com/acme/repo"' in cards[1]
    assert 'href="https://acme.example/p"' in cards[1]
    assert ">GitHub<" in cards[1] and ">Project<" in cards[1]
    for card in cards:
        assert ">Hugging Face<" in card and ">arXiv<" in card


def test_affiliation_row_only_when_present(issue_w44):
    issue = _with_item(issue_w44, 0, affiliation=None)
    issue = _with_item(issue, 1, affiliation="Acme Research Lab")
    out = render_html(issue, "구독자님")
    assert out.count("Acme Research Lab") == 1


def test_empty_ideas_row_omitted(issue_w44):
    issue = _with_item(issue_w44, 0, use_ideas_ko=[])
    issue = _with_item(issue, 1, use_ideas_ko=["첫째 아이디어", "둘째 아이디어"])
    cards = render_html(issue, "구독자님").split("data-card=")[1:]
    assert ">· " not in cards[0]
    assert "· 첫째 아이디어<br>· 둘째 아이디어" in cards[1]


def test_greeting_is_escaped(issue_w44):
    out = render_html(issue_w44, "<b>x</b>님")
    assert "<b>x</b>" not in out
    assert "&lt;b&gt;x&lt;/b&gt;님" in out


def test_title_script_is_escaped(issue_w44):
    issue = _with_item(issue_w44, 2, title_ko='<script>alert("x")</script> 제목')
    out = render_html(issue, "구독자님")
    assert "<script" not in out
    assert "&lt;script&gt;" in out


def test_explainer_set_is_not_rendered_in_phase1(issue_w44):
    issue = issue_w44.model_copy(
        update={"explainer": Explainer(topic="MoE 해설", body_ko="전문가 혼합 설명", related_ranks=[1])}
    )
    out = render_html(issue, "구독자님")
    assert "MoE 해설" not in out
    assert "전문가 혼합 설명" not in out
    assert out.count("data-card=") == 10


def test_later_phase_fields_not_rendered(issue_w44):
    issue = issue_w44.model_copy(update={"trend_ko": "이번 주 트렌드 문장"})
    out = render_html(issue, "구독자님")
    assert "이번 주 트렌드 문장" not in out
    assert "확인 필요" not in out


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
    issue = _with_item(issue_w44, 1, use_ideas_ko=["첫째 아이디어", "둘째 아이디어"])
    txt = render_text(issue, "구독자님")
    assert "구독자님" in txt
    assert not re.search(r"<[a-zA-Z/][^>]*>", txt)
    for it in issue.items:
        for s in (it.title_ko, it.title_en, it.summary_ko, *it.use_ideas_ko):
            assert s in txt
        for url in (it.hf_url, it.arxiv_url, it.github_url, it.project_url):
            if url:
                assert url in txt
        if it.affiliation:
            assert it.affiliation in txt


def test_subject_short_title(issue_w44):
    issue = _with_item(issue_w44, 0, title_ko="Qwen3-VL: long-context 멀티모달 추론")
    title = issue.items[0].title_ko
    assert len(title) <= SUBJECT_TITLE_MAX
    assert build_subject(issue, "send") == f"[AI 주간 모델 브리프] 이번 주 1위: {title} 외 9건"


def test_subject_long_title_is_capped(issue_w44):
    title = "가" * 31 + " " + "나" * 18  # 50 chars, char 32 is a space
    assert len(title) == 50
    issue = _with_item(issue_w44, 0, title_ko=title)
    subject = build_subject(issue, "send")
    assert subject == f"[AI 주간 모델 브리프] 이번 주 1위: {'가' * 31}… 외 9건"
    title2 = "다" * 50
    subject2 = build_subject(_with_item(issue_w44, 0, title_ko=title2), "send")
    assert f"1위: {'다' * 32}… 외 9건" in subject2


def test_subject_single_item_has_no_count_tail(issue_w44):
    one = issue_w44.items[0].model_copy(update={"title_ko": "단일 논문 제목"})
    issue = issue_w44.model_copy(update={"items": [one]})
    assert build_subject(issue, "send") == "[AI 주간 모델 브리프] 이번 주 1위: 단일 논문 제목"


def test_subject_test_prefix_only_in_test_mode(issue_w44):
    assert build_subject(issue_w44, "test").startswith("[TEST] [AI 주간 모델 브리프]")
    for mode in ("send", "preview"):
        assert build_subject(issue_w44, mode).startswith("[AI 주간 모델 브리프]")


def test_subject_has_no_line_breaks(issue_w44):
    issue = _with_item(issue_w44, 0, title_ko="줄\r\n바꿈\n제목")
    for mode in ("test", "send", "preview"):
        s = build_subject(issue, mode)
        assert "\r" not in s and "\n" not in s
