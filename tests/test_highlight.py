"""Highlight stage (HILT-01..03, D-01..D-03, D-11): candidates, one pick call, code guards."""

import anthropic
import httpx2
import pytest
from conftest import (
    DEFAULT_HIGHLIGHT_HOW,
    DEFAULT_HIGHLIGHT_WHY,
    FakeAnthropic,
    make_parsed,
)

from newsletter.schema import HighlightPickLLM, HighlightsLLM, Issue, SkillGptFitInfo
from newsletter.stages import analyze, headline, highlight
from newsletter.store import PROMPTS_DIR


@pytest.fixture(autouse=True)
def _clear_downgrade_registry():
    analyze._FALLBACKS_UNSUPPORTED.clear()
    yield
    analyze._FALLBACKS_UNSUPPORTED.clear()


FITS = ["Claude Skill", "GPTs", "둘 다", "해당 없음", "Claude Skill"] + ["해당 없음"] * 5
REASON = "요약 규칙을 지시문으로 정리해 둘 수 있어요."


def _items(issue: Issue, fits=FITS):
    return [
        it.model_copy(
            update={
                "skill_gpt": SkillGptFitInfo(
                    fit=fit, reason_ko=None if fit == "해당 없음" else REASON
                )
            }
        )
        for it, fit in zip(issue.items, fits, strict=True)
    ]


def _pick(rank: int) -> HighlightPickLLM:
    return HighlightPickLLM(rank=rank, why_ko=DEFAULT_HIGHLIGHT_WHY, how_ko=DEFAULT_HIGHLIGHT_HOW)


def _picks(*ranks: int):
    return make_parsed(HighlightsLLM(picks=[_pick(r) for r in ranks]))


def test_candidates_exclude_no_fit(issue_w44):
    items = _items(issue_w44)
    assert [it.rank for it in highlight.candidates(items)] == [1, 2, 3, 5]


def test_items_block_holds_candidates_only_and_no_verdicts(issue_w44):
    block = highlight.items_block(highlight.candidates(_items(issue_w44)))
    assert block.startswith("<items>") and block.endswith("</items>")
    assert [line for line in block.splitlines() if line.startswith("rank: ")] == [
        "rank: 1",
        "rank: 2",
        "rank: 3",
        "rank: 5",
    ]
    assert "skill_gpt_fit: 둘 다" in block
    assert f"skill_gpt_reason_ko: {REASON}" in block
    assert "http" not in block
    for word in ("commercial", "poc", "claude_gpt:", "verdict"):
        assert word not in block


def test_w44_happy_path_three_picks_with_copied_tags(issue_w44):
    items = _items(issue_w44)
    fake = FakeAnthropic()  # default: picks for the first three input ranks
    out = highlight.write_highlights(items, fake)

    assert len(fake.calls) == 1
    assert fake.calls[0]["kw"]["output_format"] is HighlightsLLM
    assert [h.rank for h in out] == [1, 2, 3]
    assert [h.tag for h in out] == ["Claude Skill", "GPTs", "둘 다"]
    assert all(h.why_ko == DEFAULT_HIGHLIGHT_WHY and h.how_ko == DEFAULT_HIGHLIGHT_HOW for h in out)
    # The result fits the frozen Issue contract.
    Issue.model_validate({**issue_w44.model_dump(), "items": items, "highlights": out})


def test_no_candidate_makes_no_call(issue_w44):
    fake = FakeAnthropic()
    assert highlight.write_highlights(_items(issue_w44, ["해당 없음"] * 10), fake) == []
    assert fake.calls == []


def test_rank_outside_candidates_and_duplicates_are_dropped(issue_w44):
    fake = FakeAnthropic([_picks(4, 2, 2, 11, 5)] * 2)  # the same answer after the retry
    out = highlight.write_highlights(_items(issue_w44), fake)
    assert len(fake.calls) == 2
    assert [h.rank for h in out] == [2, 5]
    assert [h.tag for h in out] == ["GPTs", "Claude Skill"]


def test_four_picks_are_cut_to_three_in_claude_order(issue_w44):
    fake = FakeAnthropic([_picks(5, 3, 1, 2)] * 2)  # the same answer after the retry
    out = highlight.write_highlights(_items(issue_w44), fake)
    assert len(fake.calls) == 2
    assert [h.rank for h in out] == [5, 3, 1]


def test_zero_picks_twice_returns_empty(issue_w44):
    fake = FakeAnthropic([_picks(), _picks()])
    assert highlight.write_highlights(_items(issue_w44), fake) == []


def test_api_error_returns_empty(issue_w44):
    req = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    fake = FakeAnthropic([anthropic.APIConnectionError(request=req)])
    assert highlight.write_highlights(_items(issue_w44), fake) == []


def test_system_prompt_is_highlight_plus_humanizer():
    system = highlight.highlight_system_prompt()
    head = (PROMPTS_DIR / "highlight.md").read_text(encoding="utf-8").strip()
    humanizer = (PROMPTS_DIR / "humanizer_ko.md").read_text(encoding="utf-8").strip()
    assert system == head + "\n\n" + humanizer


# ------------------------------------------------- text checks (D-03, HILT-02)

GOOD = "Claude Skill로 정리해 두면 같은 형식으로 받을 수 있어요."


@pytest.mark.parametrize("field", ["why_ko", "how_ko"])
@pytest.mark.parametrize(
    "text",
    [
        GOOD,
        "회의록을 같은 틀로 받아요. GPTs에 예시 파일을 넣어 두면 돼요.",
        "가" * 69 + "요",
    ],
)
def test_check_text_passes_short_haeyo(field, text):
    assert highlight.check_text(field, text) == []


@pytest.mark.parametrize(
    ("text", "code"),
    [
        ("", "hl_empty"),
        ("   ", "hl_empty"),
        ("가" * 70 + "요", "hl_len"),
        ("정리해요. 넣어요. 써요.", "hl_sentences"),
        ("규칙을 지시문에 넣으면 된다.", "hl_tone"),
        ("1. 규칙을 지시문에 넣어 두면 돼요.", "hl_steps"),
        ("먼저 2) 예시를 넣어 두면 돼요.", "hl_steps"),
        ("① 규칙을 지시문에 넣어 두면 돼요.", "hl_steps"),
        ("첫째 규칙을 지시문에 넣어 두면 돼요.", "hl_steps"),
        ("예시는 https://example.com 에 있어요.", "hl_url"),
        ("혁신적인 방식으로 정리할 수 있어요.", "hl_hype"),
        ("이 뉴스레터처럼 정리해 둘 수 있어요.", "hl_authorship"),
        ("자동 생성 규칙을 넣어 두면 돼요.", "hl_authorship"),
        ("AI가 쓴 요약을 그대로 받아요.", "hl_authorship"),
    ],
)
def test_check_text_codes(text, code):
    codes = [c for c, _ in highlight.check_text("how_ko", text)]
    assert code in codes, codes


@pytest.mark.parametrize(
    "text",
    [
        "이메일 초안 규칙을 Skill로 정리해 둘 수 있어요.",
        "이번 호출 결과를 GPTs 지식 파일로 넣어 두면 돼요.",
        "자동으로 같은 형식을 받을 수 있어요.",
    ],
)
def test_written_by_re_allows_product_names_and_plain_words(text):
    assert headline.WRITTEN_BY_RE.search(text) is None
    assert highlight.check_text("how_ko", text) == []


def test_check_text_messages_carry_no_model_text():
    msgs = [m for _, m in highlight.check_text("why_ko", "비밀문장 1. 혁신적이다")]
    assert msgs and all("why_ko" in m and "비밀문장" not in m for m in msgs)


# ------------------------------------------------- pick checks and the retry


def _bad_pick(rank: int) -> HighlightPickLLM:
    return HighlightPickLLM(rank=rank, why_ko="1. 정리한다", how_ko=DEFAULT_HIGHLIGHT_HOW)


def _resp(*picks: HighlightPickLLM):
    return make_parsed(HighlightsLLM(picks=list(picks)))


def test_review_pick_level_codes():
    picks = [_pick(1), _pick(4), _pick(1), _pick(2), _pick(3)]
    kept, problems = highlight.review(picks, {1, 2, 3, 5})
    codes = [c for c, _ in problems]
    assert "hl_rank" in codes and "hl_duplicate" in codes and "hl_count" in codes
    assert [p.rank for p in kept] == [1, 2, 3]


def test_failing_pick_retries_once_with_problem_messages_only(issue_w44):
    fake = FakeAnthropic([_resp(_pick(1), _bad_pick(2)), _resp(_pick(1), _pick(2))])
    out = highlight.write_highlights(_items(issue_w44), fake)
    assert len(fake.calls) == 2
    retry = fake.user_texts()[1]
    assert "<previous_output_problems>" in retry
    problems = retry.split("<previous_output_problems>")[1]
    assert "정리한다" not in problems and DEFAULT_HIGHLIGHT_HOW not in problems
    assert "2번째 pick" in problems
    assert [h.rank for h in out] == [1, 2]


def test_after_second_attempt_failing_picks_are_dropped(issue_w44):
    fake = FakeAnthropic([_resp(_bad_pick(1), _pick(2)), _resp(_pick(3), _bad_pick(5))])
    out = highlight.write_highlights(_items(issue_w44), fake)
    assert len(fake.calls) == 2
    assert [h.rank for h in out] == [3]
    assert out[0].tag == "둘 다"


@pytest.mark.parametrize(
    "second",
    [
        make_parsed(None, stop_reason="refusal"),
        make_parsed(None, stop_reason="max_tokens"),
        make_parsed(None),
        ValueError("schema"),
    ],
)
def test_unusable_second_attempt_keeps_first_passing_picks(issue_w44, second):
    fake = FakeAnthropic([_resp(_pick(5), _bad_pick(1)), second])
    out = highlight.write_highlights(_items(issue_w44), fake)
    assert len(fake.calls) == 2
    assert [h.rank for h in out] == [5]


@pytest.mark.parametrize(
    "first",
    [
        make_parsed(None, stop_reason="refusal"),
        make_parsed(None, stop_reason="max_tokens"),
        ValueError("schema"),
    ],
)
def test_refusal_max_tokens_and_schema_use_the_retry(issue_w44, first):
    fake = FakeAnthropic([first, _resp(_pick(2))])
    out = highlight.write_highlights(_items(issue_w44), fake)
    assert len(fake.calls) == 2
    assert "<previous_output_problems>" in fake.user_texts()[1]
    assert [h.rank for h in out] == [2]


def test_two_failed_attempts_give_empty(issue_w44):
    fake = FakeAnthropic([_resp(_bad_pick(1)), _resp(_bad_pick(2))])
    assert highlight.write_highlights(_items(issue_w44), fake) == []


def test_zero_picks_with_candidates_retries_once(issue_w44):
    fake = FakeAnthropic([_picks(), _picks(2)])
    out = highlight.write_highlights(_items(issue_w44), fake)
    assert len(fake.calls) == 2
    assert [h.rank for h in out] == [2]
    assert "hl_none" in str(fake.calls[1]["kw"]) or "picks가 비어" in str(fake.calls[1]["kw"])


def test_logs_carry_counts_and_codes_only(issue_w44, caplog):
    items = _items(issue_w44)
    fake = FakeAnthropic([_resp(_pick(1), _bad_pick(2)), _resp(_pick(1), _bad_pick(3))])
    with caplog.at_level("INFO", logger="newsletter"):
        highlight.write_highlights(items, fake)
    msgs = [r.getMessage() for r in caplog.records if r.name.endswith("highlight")]
    assert "highlight attempt=1 reason=" in msgs[0]
    assert msgs[-1] == "highlight=claude picks=1 attempt=2"
    text = "\n".join(msgs)
    for secret in (DEFAULT_HIGHLIGHT_WHY, DEFAULT_HIGHLIGHT_HOW, "정리한다", REASON):
        assert secret not in text
    for it in items:
        assert it.title_ko not in text


def test_prompt_holds_the_d03_example_and_data_fence():
    text = (PROMPTS_DIR / "highlight.md").read_text(encoding="utf-8")
    assert "요약 규칙을 Skill로 정리해 두면 매번 같은 형식으로 받을 수 있어요" in text
    assert "<items>" in text and "데이터" in text
    assert "<previous_output_problems>" in text
    assert "70자" in text and "1-3개" in text
    assert "has_demo" in text and "claude_gpt_use" in text


# ------------------------------------- v4: Claude/GPT agents and demo pages


SPACE = "https://huggingface.co/spaces/org/demo"


def _with(it, *, verdict=None, space=False, project=None):
    from newsletter.schema import ClaudeGptUse, EvidenceLink, PocReadiness

    upd = {}
    if verdict:
        upd["claude_gpt"] = ClaudeGptUse(verdict=verdict)
    if space:
        upd["poc"] = PocReadiness(
            verdict="바로 가능", has_demo=True, evidence=[EvidenceLink(label="HF 데모", url=SPACE)]
        )
    if project:
        upd["project_url"] = project
    return it.model_copy(update=upd)


def test_agents_and_demos_become_candidates_demo_first(issue_w44):
    items = _items(issue_w44, ["해당 없음"] * 10)
    items[6] = _with(items[6], verdict="직접 사용")
    items[8] = _with(items[8], space=True)
    assert [it.rank for it in highlight.candidates(items)] == [9, 7]
    assert highlight.tag_for(items[6]) == "Claude/GPT 에이전트"
    assert highlight.tag_for(items[8]) == "데모"
    # 기법 적용 가능 alone and a project page alone are not candidates.
    items[0] = _with(items[0], verdict="기법 적용 가능", project="https://example.org/p")
    assert highlight.tag_for(items[0]) is None


def test_skill_fit_keeps_its_tag_and_gets_the_demo_link(issue_w44):
    items = _items(issue_w44)
    items[2] = _with(items[2], verdict="직접 사용", space=True)
    assert highlight.tag_for(items[2]) == "둘 다"
    assert [it.rank for it in highlight.candidates(items)] == [3, 1, 2, 5]
    out = highlight.write_highlights(items, FakeAnthropic())
    assert [(h.rank, h.tag, h.demo_url) for h in out] == [
        (3, "둘 다", SPACE),
        (1, "Claude Skill", items[0].project_url),
        (2, "GPTs", items[1].project_url),
    ]


def test_demo_url_falls_back_to_the_project_page(issue_w44):
    it = _with(issue_w44.items[0], verdict="직접 사용", project="https://example.org/p")
    assert highlight.space_url(it) is None
    assert highlight.demo_url(it) == "https://example.org/p"


def test_block_flags_demo_and_agent_without_urls(issue_w44):
    items = _items(issue_w44, ["해당 없음"] * 10)
    items[1] = _with(items[1], verdict="직접 사용", space=True)
    block = highlight.items_block(highlight.candidates(items))
    assert "tag: Claude/GPT 에이전트" in block
    assert "has_demo: yes" in block and "claude_gpt_use: yes" in block
    assert "http" not in block
