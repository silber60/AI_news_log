"""Explainer stage (EXPL-01/02, D-04, D-05, D-12): one call, code guards, repeat rule."""

import logging

import anthropic
import httpx2
import pytest
from conftest import (
    DEFAULT_EXPLAINER_BODY,
    DEFAULT_EXPLAINER_EXAMPLE,
    DEFAULT_EXPLAINER_POINT,
    DEFAULT_EXPLAINER_TOPIC,
    FakeAnthropic,
    make_parsed,
)

from newsletter.schema import ExplainerLLM, ItemImage
from newsletter.stages import analyze, explainer


@pytest.fixture(autouse=True)
def _clear_downgrade_registry():
    analyze._FALLBACKS_UNSUPPORTED.clear()
    yield
    analyze._FALLBACKS_UNSUPPORTED.clear()


def _out(**update) -> ExplainerLLM:
    base = {
        "topic": DEFAULT_EXPLAINER_TOPIC,
        "point_ko": DEFAULT_EXPLAINER_POINT,
        "body_ko": DEFAULT_EXPLAINER_BODY,
        "example_ko": DEFAULT_EXPLAINER_EXAMPLE,
        "related_ranks": [1, 2],
    }
    return ExplainerLLM(**(base | update))


def _resp(**update):
    return make_parsed(_out(**update))


def _image() -> ItemImage:
    return ItemImage(url="https://cdn-uploads.huggingface.co/a.png", width=576, height=234)


# ------------------------------------------------------------------ input


def test_items_block_fences_items_and_past_topics(issue_w44):
    block = explainer.items_block(issue_w44.items, ["RAG: 찾아서 답하기"])
    assert block.startswith("<items>")
    assert block.endswith("</past_topics>")
    ranks = [line for line in block.splitlines() if line.startswith("rank: ")]
    assert ranks == [f"rank: {r}" for r in range(1, 11)]
    for key in ("title_en", "summary_ko", "does_ko", "kind_ko", "architecture_ko"):
        assert f"\n{key}: " in block
    assert "http" not in block
    assert "commercial" not in block and "verdict" not in block
    assert "<past_topics>\nRAG: 찾아서 답하기\n</past_topics>" in block


def test_items_block_without_past_says_none_and_caps_at_52(issue_w44):
    assert "<past_topics>\n(없음)\n</past_topics>" in explainer.items_block(issue_w44.items, [])
    past = [f"주제 {i}" for i in range(60)]
    block = explainer.items_block(issue_w44.items, past)
    shown = block.split("<past_topics>\n", 1)[1].split("\n</past_topics>")[0].splitlines()
    assert shown == past[:52]


# ------------------------------------------------------------------ happy path


def test_happy_path_stores_fields_and_copies_image(issue_w44):
    items = issue_w44.items
    assert items[0].image is not None
    fake = FakeAnthropic()
    ex = explainer.write_explainer(items, [], fake)
    assert len(fake.calls) == 1
    assert fake.calls[0]["kw"]["output_format"] is ExplainerLLM
    assert (ex.topic, ex.point_ko, ex.body_ko, ex.example_ko) == (
        DEFAULT_EXPLAINER_TOPIC,
        DEFAULT_EXPLAINER_POINT,
        DEFAULT_EXPLAINER_BODY,
        DEFAULT_EXPLAINER_EXAMPLE,
    )
    assert ex.related_ranks == [1, 2]
    assert ex.image == items[0].image


def test_image_from_first_related_item_with_one(issue_w44):
    items = [it.model_copy(update={"image": None}) for it in issue_w44.items]
    items[3] = items[3].model_copy(update={"image": _image()})
    ex = explainer.write_explainer(items, [], FakeAnthropic([_resp(related_ranks=[2, 4, 1])]))
    assert ex.image == _image()


def test_image_none_when_no_related_item_has_one(issue_w44):
    ex = explainer.write_explainer(
        issue_w44.items, [], FakeAnthropic([_resp(related_ranks=[2, 3])])
    )
    assert ex is not None and ex.image is None


def test_text_fields_are_one_line(issue_w44):
    body = DEFAULT_EXPLAINER_BODY.replace(" 그래서", "\n그래서")
    ex = explainer.write_explainer(issue_w44.items, [], FakeAnthropic([_resp(body_ko=body)]))
    assert ex.body_ko == DEFAULT_EXPLAINER_BODY


# ------------------------------------------------------------------ failures


@pytest.mark.parametrize("ranks", [[0], [11], [1, 1], [1, 2, 3, 4], []])
def test_invalid_related_ranks_give_none_after_retry(issue_w44, ranks, caplog):
    fake = FakeAnthropic([_resp(related_ranks=ranks), _resp(related_ranks=ranks)])
    with caplog.at_level(logging.INFO):
        assert explainer.write_explainer(issue_w44.items, [], fake) is None
    assert len(fake.calls) == 2
    assert "previous_output_problems" in fake.user_texts()[1]
    assert "explainer=none reason=ex_ranks" in caplog.text


def test_invalid_ranks_then_valid_retry_is_kept(issue_w44):
    fake = FakeAnthropic([_resp(related_ranks=[0]), _resp()])
    ex = explainer.write_explainer(issue_w44.items, [], fake)
    assert ex is not None and ex.related_ranks == [1, 2]
    assert len(fake.calls) == 2


def test_api_error_gives_none_without_retry(issue_w44, caplog):
    req = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    fake = FakeAnthropic([anthropic.APIConnectionError(request=req)])
    with caplog.at_level(logging.WARNING):
        assert explainer.write_explainer(issue_w44.items, [], fake) is None
    assert len(fake.calls) == 1
    assert "explainer=none reason=api_error" in caplog.text


def test_refusal_twice_gives_none(issue_w44):
    refusal = make_parsed(None, stop_reason="refusal")
    fake = FakeAnthropic([refusal, refusal])
    assert explainer.write_explainer(issue_w44.items, [], fake) is None
    assert len(fake.calls) == 2
