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


# ------------------------------------------------------------------ check_field (D-04)


def _codes(field, text, items):
    return {code for code, _ in explainer.check_field(field, text, items)}


def test_default_fields_pass(issue_w44):
    items = issue_w44.items
    for field, text in (
        ("topic", DEFAULT_EXPLAINER_TOPIC),
        ("point_ko", DEFAULT_EXPLAINER_POINT),
        ("body_ko", DEFAULT_EXPLAINER_BODY),
        ("example_ko", DEFAULT_EXPLAINER_EXAMPLE),
    ):
        assert explainer.check_field(field, text, items) == [], field


def test_topic_too_long_or_a_sentence(issue_w44):
    items = issue_w44.items
    assert "ex_topic" in _codes("topic", "Mixture of Experts: " + "가" * 21, items)
    assert "ex_topic" in _codes("topic", "전문가를 골라 쓰는 구조입니다.", items)
    assert "ex_topic" in _codes("topic", "전문가를 골라 쓴다", items)


def test_point_must_be_one_short_sentence(issue_w44):
    items = issue_w44.items
    assert "ex_point" in _codes("point_ko", "골라서 계산해요. 그래서 가벼워요.", items)
    assert "ex_point" in _codes("point_ko", "가" * 40 + "요.", items)


def test_body_must_be_three_or_four_sentences(issue_w44):
    items = issue_w44.items
    assert "ex_body" in _codes("body_ko", "하나예요. 둘이에요.", items)
    five = " ".join(["router가 입력마다 몇 개만 골라 써요."] * 5)
    assert "ex_body" in _codes("body_ko", five, items)
    long = " ".join(["가" * 120 + "요."] * 3)
    assert "ex_body" in _codes("body_ko", long, items)


def test_example_must_be_one_or_two_short_sentences(issue_w44):
    items = issue_w44.items
    assert "ex_example" in _codes("example_ko", "하나예요. 둘이에요. 셋이에요.", items)
    assert "ex_example" in _codes("example_ko", "가" * 140 + "요.", items)


@pytest.mark.parametrize("field", ["point_ko", "body_ko", "example_ko"])
def test_prose_fields_need_haeyo(issue_w44, field):
    text = {
        "point_ko": "필요한 부분만 골라 계산한다.",
        "body_ko": "큰 모델은 계산이 많다. 그래서 일부만 쓴다. 비용이 줄어든다.",
        "example_ko": "그 과목 선생님만 답하는 학교와 비슷하다.",
    }[field]
    assert "ex_tone" in _codes(field, text, issue_w44.items)


def test_url_hype_and_authorship(issue_w44):
    items = issue_w44.items
    assert "ex_url" in _codes("point_ko", "https://x.io 에서 볼 수 있어요.", items)
    assert "ex_hype" in _codes("point_ko", "혁신적인 방법으로 계산을 줄여요.", items)
    assert "ex_authorship" in _codes("point_ko", "이 뉴스레터가 고른 기술이에요.", items)
    assert "ex_url" in _codes("topic", "www.example.com: 설명", items)


def test_unknown_digit_names_are_rejected(issue_w44):
    items = issue_w44.items
    assert "ex_unknown_name" in _codes("point_ko", "GPT-5도 이 구조를 써요.", items)
    assert "ex_unknown_name" in _codes("topic", "Qwen3: 전문가 혼합", items)
    assert "ex_unknown_name" not in _codes("point_ko", "PDRVLA도 이 구조를 써요.", items)
    ok = "Transformer의 attention 뒤에 router를 둬요."
    assert _codes("point_ko", ok, items) == set()


def test_numbers_must_come_from_the_items_except_in_the_example(issue_w44):
    items = issue_w44.items
    assert "ex_number" in _codes("point_ko", "계산이 9876배 줄어요.", items)
    body = "계산이 많아요. 그래서 일부만 골라 써요. 비용이 4321배 줄어요."
    assert "ex_number" in _codes("body_ko", body, items)
    assert "ex_number" not in _codes("example_ko", "요리사 10명 중 둘만 요리해요.", items)


# ------------------------------------------------------------------ repeat rule (D-05, D-12)

PAST = ["MoE: 전문가 혼합 구조"]


def test_repeat_fallback_rank1_is_accepted_without_retry(issue_w44, caplog):
    fake = FakeAnthropic([_resp(related_ranks=[1])])
    with caplog.at_level(logging.INFO):
        ex = explainer.write_explainer(issue_w44.items, PAST, fake)
    assert ex is not None and ex.related_ranks == [1]
    assert len(fake.calls) == 1


def test_repeat_with_other_ranks_triggers_one_retry(issue_w44):
    fresh = "LoRA: 가볍게 고쳐 쓰는 방법"
    fake = FakeAnthropic([_resp(related_ranks=[1, 2]), _resp(topic=fresh)])
    ex = explainer.write_explainer(issue_w44.items, PAST, fake)
    assert ex is not None and ex.topic == fresh
    assert len(fake.calls) == 2
    retry = fake.user_texts()[1]
    assert "previous_output_problems" in retry
    assert "past_topics" in retry.split("<previous_output_problems>", 1)[1]


def test_repeat_on_attempt_two_is_accepted_and_logged(issue_w44, caplog):
    fake = FakeAnthropic([_resp(related_ranks=[2, 3]), _resp(related_ranks=[2, 3])])
    with caplog.at_level(logging.INFO):
        ex = explainer.write_explainer(issue_w44.items, PAST, fake)
    assert ex is not None and ex.topic == DEFAULT_EXPLAINER_TOPIC
    assert len(fake.calls) == 2
    assert "explainer=repeat" in caplog.text
    assert "ex_repeat" in caplog.text  # attempt 1 reason


def test_repeat_plus_other_problem_on_attempt_two_gives_none(issue_w44, caplog):
    bad = _resp(related_ranks=[2], point_ko="계산이 9876배 줄어요.")
    fake = FakeAnthropic([bad, bad])
    with caplog.at_level(logging.INFO):
        assert explainer.write_explainer(issue_w44.items, PAST, fake) is None
    assert "explainer=none reason=ex_number" in caplog.text
    assert "ex_repeat" not in caplog.text.split("explainer=none", 1)[1]


def test_field_failure_twice_gives_none_and_logs_codes_only(issue_w44, caplog):
    bad = _resp(body_ko="하나예요. 둘이에요.")
    fake = FakeAnthropic([bad, bad])
    with caplog.at_level(logging.DEBUG):
        assert explainer.write_explainer(issue_w44.items, [], fake) is None
    assert "explainer=none reason=ex_body" in caplog.text
    for text in (DEFAULT_EXPLAINER_TOPIC, DEFAULT_EXPLAINER_POINT, "하나예요", "전문가"):
        assert text not in caplog.text
    assert "하나예요" not in fake.user_texts()[1]
