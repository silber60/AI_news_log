"""Offline end-to-end: W44 fixture -> run_build -> archive -> deliver --mode test."""

import json

import httpx
import respx
from conftest import FakeAnthropic

from newsletter.schema import HfEntry, Issue
from newsletter.stages.analyze import strip_urls
from newsletter.stages.select import sort_key

ISSUE_ID = "2026-W44"
WEEK_FILES = ("raw.json", "selected.json", "issue.json", "email.html", "email.txt")


def _mock_hf(router: respx.MockRouter, pages: list[list[dict]]) -> list[respx.Route]:
    routes = []
    for i, page in enumerate(pages):
        routes.append(
            router.get(
                "https://huggingface.co/api/daily_papers",
                params={"week": ISSUE_ID, "limit": "100", "p": str(i)},
            ).mock(return_value=httpx.Response(200, json=page))
        )
    return routes


def _build(hf_pages, fake: FakeAnthropic) -> Issue:
    from newsletter.pipeline import run_build

    with respx.mock(assert_all_mocked=True, assert_all_called=True) as router:
        routes = _mock_hf(router, hf_pages)
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

    assert len(fake.calls) == 10
    for text in fake.user_texts():
        assert "http" not in text
        assert text.startswith("<paper>")

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
    assert fields == {"title_ko", "ai_type", "summary_ko", "use_ideas_ko"}
    for name in fields:
        assert "url" not in name and "rank" not in name and "verdict" not in name


def test_deliver_test_mode_sends_one_message(hf_pages, archive_tmp, fake_smtp, monkeypatch):
    from newsletter.__main__ import main

    _build(hf_pages, FakeAnthropic())

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
    assert str(msg["Subject"]).startswith("[TEST] [AI 주간 모델 브리프]")
    html = msg.get_body(preferencelist=("html",)).get_content()
    assert "구독자님" in html
