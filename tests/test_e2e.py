"""Offline end-to-end: W44 fixture -> run_build -> archive -> deliver --mode test."""

import json

import respx
from conftest import FakeAnthropic, mock_hf_week

from newsletter.schema import UNKNOWN, HfEntry, Issue
from newsletter.stages.analyze import strip_urls
from newsletter.stages.headline import fallback_headline
from newsletter.stages.render import build_subject
from newsletter.stages.select import sort_key

ISSUE_ID = "2026-W44"
WEEK_FILES = ("raw.json", "selected.json", "issue.json", "email.html", "email.txt")


def _build(hf_pages, fake: FakeAnthropic) -> Issue:
    from newsletter.pipeline import run_build

    with respx.mock(assert_all_mocked=True, assert_all_called=True) as router:
        routes = mock_hf_week(router, hf_pages, ISSUE_ID)
        issue = run_build(ISSUE_ID, claude_client=fake)
    assert all(r.call_count == 1 for r in routes)
    return issue


def test_run_build_writes_archive(hf_pages, archive_tmp):
    fake = FakeAnthropic()
    issue = _build(hf_pages, fake)

    week = archive_tmp / "archive" / ISSUE_ID
    for name in WEEK_FILES:
        assert (week / name).is_file(), name
    current = json.loads((archive_tmp / "archive" / "current.json").read_text(encoding="utf-8"))
    assert current == {"issue_id": ISSUE_ID}

    stored = Issue.model_validate_json((week / "issue.json").read_text(encoding="utf-8"))
    assert stored == issue
    assert [it.rank for it in stored.items] == list(range(1, 11))

    entries = [HfEntry.model_validate(d) for page in hf_pages for d in page]
    expected = [e.paper.id for e in sorted(entries, key=sort_key)[:10]]
    assert [it.paper_id for it in stored.items] == expected

    assert stored.explainer is None
    assert stored.highlights == []
    assert stored.trend_ko is None
    for it in stored.items:
        assert it.commercial.verdict == "확인 필요"
        assert it.poc.verdict == "확인 필요"
        assert it.claude_gpt.verdict == "확인 필요"
        assert it.hardware.local_run == "확인 필요"
        assert len(it.summary_lines_ko) == 3
        assert all(line.strip() for line in it.summary_lines_ko)
        assert it.poc.has_weights in (True, None)
        assert it.poc.has_code in (True, None)
        assert it.poc.has_demo in (True, None)
    # Facts come from the HF paper/model captures by code (D-07); unknown stays UNKNOWN.
    rank1, rank3 = stored.items[0], stored.items[2]
    assert (rank1.model_info.size, rank1.model_info.training_data, rank1.model_info.release) == (
        UNKNOWN,
        UNKNOWN,
        UNKNOWN,
    )
    assert rank3.model_info.training_data == "JusperLee/RealSSA-Real, JusperLee/RealSSA-Sim"
    assert rank3.model_info.release == "가중치 · GitHub · 데모"
    assert rank3.model_info.size == UNKNOWN
    assert stored.schema_version == 2
    name = stored.items[0].title_ko.split(":", 1)[0].strip()[:20]
    assert stored.headline_ko == "🤖 말하면 로봇이 움직인다? 이번 주 AI 모델 10"
    assert fallback_headline(stored.items) == f"🧠 {name} 등 이번 주 AI 모델 10"
    assert fallback_headline(stored.items[:1]) == f"🧠 {name} 이번 주 AI 모델 1"

    assert len(fake.calls) == 11  # 10 analysis calls + 1 headline call
    texts = fake.user_texts()
    for text in texts[:10]:
        assert "http" not in text
        assert text.startswith("<paper>")
    assert texts[10].startswith("<items>")
    assert "http" not in texts[10]

    raw_text = (week / "raw.json").read_text(encoding="utf-8")
    assert '"authors"' not in raw_text
    assert '"submittedBy"' not in raw_text
    raw = json.loads(raw_text)
    assert raw["count"] == len(raw["entries"]) == 214
    selected = json.loads((week / "selected.json").read_text(encoding="utf-8"))
    assert [s["paper_id"] for s in selected["items"]] == expected

    html = (week / "email.html").read_text(encoding="utf-8")
    assert "구독자님" in html
    assert "Apple SD Gothic Neo" in html
    assert "구독자님" in (week / "email.txt").read_text(encoding="utf-8")


def test_fixture_abstract_url_is_stripped(hf_pages):
    """Rank-3 W44 paper 2610.32749 embeds a URL in its abstract; strip_urls removes it."""
    by_id = {d["paper"]["id"]: d for page in hf_pages for d in page}
    summary = by_id["2610.32749"]["paper"]["summary"]
    assert "http" in summary
    assert "http" not in strip_urls(summary)
    assert strip_urls("see https://github.com/x/y and http://a.b/c now") == "see and now"


def test_claude_output_model_has_no_code_owned_fields():
    from newsletter.schema import ItemAnalysisLLM

    fields = set(ItemAnalysisLLM.model_fields)
    assert fields == {
        "title_ko",
        "ai_type",
        "summary_ko",
        "does_ko",
        "new_ko",
        "result_ko",
        "kind_ko",
        "architecture_ko",
    }
    for name in fields:
        assert "url" not in name and "rank" not in name and "verdict" not in name


def test_deliver_test_mode_sends_one_message(hf_pages, archive_tmp, fake_smtp, monkeypatch):
    from newsletter.__main__ import main

    stored = _build(hf_pages, FakeAnthropic())

    monkeypatch.setenv("SMTP_USER", "sender@example.com")
    monkeypatch.setenv("SMTP_PASSWORD", "abcd efgh ijkl mnop")
    monkeypatch.setenv("TEST_RECIPIENT", "owner@example.com")

    assert main(["deliver", "--mode", "test"]) == 0

    assert len(fake_smtp.instances) == 1
    smtp = fake_smtp.instances[0]
    assert (smtp.host, smtp.port) == ("smtp.gmail.com", 465)
    assert smtp.login_calls == [("sender@example.com", "abcdefghijklmnop")]
    assert len(smtp.sent) == 1
    msg = smtp.sent[0]
    assert msg.get_content_type() == "multipart/alternative"
    assert msg["To"] == "owner@example.com"
    assert str(msg["Subject"]) == "[TEST] " + build_subject(stored, "send")
    html = msg.get_body(preferencelist=("html",)).get_content()
    assert "구독자님" in html
