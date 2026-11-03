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


# ---------------------------------------------------------------- check_trend

GOOD = "이번 주에는 PDRVLA 같은 VLA 연구가 눈에 띄어요. diffusion VLM과 agent 연구도 있었어요."


def _codes(text: str, items: list[Item]) -> set[str]:
    return {code for code, _ in trend.check_trend(text, items)}


def test_check_good_trend_passes(items):
    assert trend.check_trend(GOOD, items) == []
    # three sentences, a 1위 mention and a generic digit term pass too
    three = "1위는 PDRVLA예요. 3D 장면과 video agent 연구가 많아요. TAO는 LLM 서비스를 다뤄요."
    assert trend.check_trend(three, items) == []


@pytest.mark.parametrize(
    ("text", "code"),
    [
        ("로봇 연구가 많았어요.", "trend_sentences"),
        ("하나예요. 둘이에요. 셋이에요. 넷이에요.", "trend_sentences"),
        ("가" * 150 + "요. " + "나" * 148 + "요.", "trend_len"),
        ("로봇 연구가 많았어요. 영상 연구도 많았다.", "trend_tone"),
        ("로봇 연구가 많았어요. 자세한 내용은 https://x.y 에 있어요.", "trend_url"),
        ("로봇 연구가 많았어요. 자세한 내용은 www.example 에 있어요.", "trend_url"),
        ("로봇 연구가 많았어요. 혁신적 영상 연구도 있었어요.", "trend_hype"),
        ("Claude가 이번 주를 정리했어요. 로봇 연구가 많았어요.", "trend_authorship"),
        ("AI가 고른 연구예요. 로봇 연구가 많았어요.", "trend_authorship"),
        ("자동으로 모은 연구예요. 로봇 연구가 많았어요.", "trend_authorship"),
    ],
)
def test_check_flags_rule(items, text, code):
    assert code in _codes(text, items)


def test_check_unknown_name_is_flagged(items):
    assert "trend_unknown_name" in _codes("GPT-5 같은 연구가 많았어요. 로봇 연구도 있어요.", items)
    assert "trend_unknown_name" in _codes("Sora와 닮은 영상 연구예요. 로봇 연구도 있어요.", items)


def test_check_name_from_items_and_lowercase_terms_pass(items):
    text = "OmniShowcase와 StreamVibe가 영상을 다뤄요. diffusion과 fine-tuning 이야기도 있어요."
    assert "trend_unknown_name" not in _codes(text, items)


def test_check_rank_out_of_range(items):
    assert "trend_rank" in _codes("11위 연구는 로봇을 다뤄요. 영상 연구도 있어요.", items)
    assert "trend_rank" not in _codes("10위 연구는 benchmark예요. 영상 연구도 있어요.", items)
    assert "trend_rank" in _codes("2위 연구가 영상을 다뤄요. 로봇 연구도 있어요.", items[:1])


def test_check_number_not_in_input(items):
    assert "trend_number" in _codes("정확도가 87% 올랐어요. 로봇 연구도 있어요.", items)
    assert "trend_number" in _codes("2.5배 빨라졌어요. 로봇 연구도 있어요.", items)


def test_check_messages_never_carry_model_text(items):
    text = "GPT-5와 Sora가 87% 혁신적이에요."
    for _, msg in trend.check_trend(text, items):
        assert "GPT" not in msg and "Sora" not in msg and "87" not in msg


# ---------------------------------------------------------------- retry / fallback


def test_retry_bad_then_good_uses_second(items):
    fake = FakeAnthropic([tr("GPT-5 연구가 많았어요."), tr(GOOD)])
    assert trend.write_trend(items, fake) == GOOD
    assert len(fake.calls) == 2
    retry = fake.user_texts()[1]
    assert "<previous_output_problems>" in retry
    assert "이번 주 항목에 없는 이름" in retry and "문장임" in retry
    assert "GPT-5" not in retry


def test_fallback_both_bad_returns_none_and_logs_codes_only(items, caplog):
    bad = "Sora 연구가 혁신적이에요."
    fake = FakeAnthropic([tr(bad), tr(bad)])
    with caplog.at_level("DEBUG", logger="newsletter"):
        assert trend.write_trend(items, fake) is None
    assert len(fake.calls) == 2
    assert "trend=none reason=" in caplog.text
    assert "trend_unknown_name" in caplog.text and "trend_hype" in caplog.text
    assert "Sora" not in caplog.text and "혁신적" not in caplog.text
    for it in items:
        assert it.title_ko not in caplog.text


def test_fallback_on_refusal_and_schema_error(items):
    try:
        TrendLLM.model_validate({"trend_ko": "x", "extra": 1})
    except ValueError as e:
        err = e
    fake = FakeAnthropic([err, make_parsed(None, stop_reason="refusal")])
    assert trend.write_trend(items, fake) is None
    assert len(fake.calls) == 2


def test_fallback_on_non_trend_output(items):
    fake = FakeAnthropic([make_parsed(None), make_parsed("not a model")])
    assert trend.write_trend(items, fake) is None
