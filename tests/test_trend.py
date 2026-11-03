"""이번 주 트렌드 총평: Claude text with code checks, one retry and None fallback (ANLY-05, D-07)."""

import re

import anthropic
import httpx2
import pytest
from conftest import DEFAULT_TREND, FakeAnthropic, make_parsed

from newsletter.schema import Item, TrendLLM
from newsletter.stages import analyze, trend
from newsletter.stages.render import render_html
from newsletter.store import PROMPTS_DIR

MESSAGES_URL = "https://api.anthropic.com/v1/messages"


@pytest.fixture(autouse=True)
def _clear_downgrade_registry():
    analyze._FALLBACKS_UNSUPPORTED.clear()
    yield
    analyze._FALLBACKS_UNSUPPORTED.clear()


@pytest.fixture
def items(issue_w44) -> list[Item]:
    return list(issue_w44.items)


def tr(text: str):
    return make_parsed(TrendLLM(trend_ko=text))


# ---------------------------------------------------------------- tracer


def test_trend_renders_under_greeting_slot(issue_w44, items):
    fake = FakeAnthropic()
    text = trend.write_trend(items, fake)
    assert text == DEFAULT_TREND
    assert len(fake.calls) == 1
    kw = fake.calls[0]["kw"]
    assert kw["output_format"] is TrendLLM
    system = kw["system"][0]["text"]
    humanizer = (PROMPTS_DIR / "humanizer_ko.md").read_text(encoding="utf-8").strip()
    assert system.endswith(humanizer)
    user = fake.user_texts()[0]
    assert user.startswith("<items>")
    assert "http" not in user

    html = render_html(issue_w44.model_copy(update={"trend_ko": text}), "구독자님")
    m = re.search(r'<tr data-section="trend">(.*?)(?=<tr data-section=|\Z)', html, re.DOTALL)
    assert m and text in m.group(1)


def test_items_block_has_every_item_and_no_verdicts(items):
    block = trend.items_block(items)
    assert block.count("rank: ") == len(items)
    for key in ("title_ko: ", "title_en: ", "ai_type: ", "summary_ko: "):
        assert block.count(key) == len(items)
    assert "commercial" not in block and "확인 필요" not in block
    assert block.endswith("</items>")


def test_prompt_version_line():
    first = (PROMPTS_DIR / "trend.md").read_text(encoding="utf-8").splitlines()[0]
    assert first == "<!-- prompt-version: 1 -->"


def test_api_error_falls_back_to_none(items):
    req = httpx2.Request("POST", MESSAGES_URL)
    fake = FakeAnthropic([anthropic.APIConnectionError(request=req)])
    assert trend.write_trend(items, fake) is None
    assert len(fake.calls) == 1


def test_empty_twice_falls_back_to_none(items):
    fake = FakeAnthropic([tr(""), tr("  ")])
    assert trend.write_trend(items, fake) is None
    assert len(fake.calls) == 2
