"""Phase 1 email render: card content, email-safe markup, size gate, text part, subject."""

import html as html_lib
from html.parser import HTMLParser

import httpx
import respx
from conftest import FakeAnthropic

from newsletter.schema import Explainer
from newsletter.stages.render import AI_TYPE_COLORS, render_html
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
