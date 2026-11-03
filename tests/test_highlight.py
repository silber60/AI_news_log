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
from newsletter.stages import analyze, highlight
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
    fake = FakeAnthropic([_picks(4, 2, 2, 11, 5)])
    out = highlight.write_highlights(_items(issue_w44), fake)
    assert [h.rank for h in out] == [2, 5]
    assert [h.tag for h in out] == ["GPTs", "Claude Skill"]


def test_four_picks_are_cut_to_three_in_claude_order(issue_w44):
    fake = FakeAnthropic([_picks(5, 3, 1, 2)])
    out = highlight.write_highlights(_items(issue_w44), fake)
    assert [h.rank for h in out] == [5, 3, 1]


def test_zero_picks_is_valid(issue_w44):
    fake = FakeAnthropic([_picks()])
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
