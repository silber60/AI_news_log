"""Offline end-to-end: W44 fixture -> run_build -> archive -> deliver --mode test."""

import json

import respx
from conftest import FakeAnthropic, mock_hf_week

from newsletter.schema import UNKNOWN, HfEntry, Issue
from newsletter.stages.analyze import strip_urls
from newsletter.stages.headline import fallback_headline
from newsletter.stages.render import build_subject
from newsletter.stages.select import select_top

ISSUE_ID = "2026-W44"
# D-02, D-03: the W44 fixtures' 10 most-starred repo papers, in star order.
STAR_TOP10 = [
    "2610.35518",
    "2610.40599",
    "2610.36729",
    "2610.31635",
    "2610.30006",
    "2610.32253",
    "2610.33106",
    "2610.14018",
    "2610.33005",
    "2610.33845",
]
STAR_POC = ["코드만", "바로 가능", "바로 가능", "코드만", "바로 가능"] + ["코드만"] * 5
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
    expected = [e.paper.id for e in select_top(entries)]
    assert expected == STAR_TOP10
    assert [it.paper_id for it in stored.items] == expected
    assert stored.items[0].github_stars == 5221
    assert all(it.github_stars is not None for it in stored.items)
    assert all(it.use_idea_ko for it in stored.items)

    assert stored.explainer is None
    assert stored.highlights == []
    assert stored.trend_ko is None
    # EVID-03: PoC decided by code from the HF paper capture.
    assert [it.poc.verdict for it in stored.items] == STAR_POC
    for it in stored.items:
        assert it.commercial.verdict == "확인 필요"
        assert it.poc.evidence
        assert it.claude_gpt.verdict == "확인 필요"
        assert len(it.summary_lines_ko) == 3
        assert all(line.strip() for line in it.summary_lines_ko)
        assert it.poc.has_weights in (True, None)
        assert it.poc.has_code in (True, None)
        assert it.poc.has_demo in (True, None)
    # Facts come from the HF paper/model captures by code (D-07); unknown stays UNKNOWN.
    facts = [
        (it.model_info.size, it.model_info.training_data, it.model_info.release)
        for it in stored.items
    ]
    assert facts == [
        (UNKNOWN, UNKNOWN, "GitHub"),  # 1 xtuner: no linked model or space
        (UNKNOWN, UNKNOWN, "가중치 · GitHub · 데모"),  # 2 HairDeck: no safetensors
        (UNKNOWN, UNKNOWN, "가중치 · GitHub · 데모"),  # 3 Hy-Nomas: no cardData datasets
        (UNKNOWN, UNKNOWN, "GitHub"),
        ("302M 파라미터 (외 2개 모델)", UNKNOWN, "가중치 · GitHub · 데모"),  # 5 detectorscope
        (UNKNOWN, UNKNOWN, "GitHub"),
        (UNKNOWN, UNKNOWN, "GitHub"),
        (UNKNOWN, UNKNOWN, "GitHub"),  # 8 linkedDatasets on the paper are not training data
        (UNKNOWN, UNKNOWN, "GitHub"),
        (UNKNOWN, UNKNOWN, "GitHub"),
    ]
    assert stored.items[4].hardware.param_count == 302130176
    # EVID-04, D-10: only detector-scope has a usable safetensors total.
    hw = stored.items[4].hardware
    assert (hw.est_vram_gb, hw.local_run) == (0.7, "가능")
    assert [it.hardware.local_run for i, it in enumerate(stored.items) if i != 4] == [UNKNOWN] * 9
    assert [it.hardware.param_count for i, it in enumerate(stored.items) if i != 4] == [None] * 9
    assert [it.poc.has_weights for it in stored.items] == [None, True, True, None, True] + [
        None
    ] * 5
    assert all(it.poc.has_code for it in stored.items)
    assert stored.schema_version == 3
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
    assert [s["basis"] for s in selected["items"]] == ["stars"] * 10
    assert selected["items"][0]["github_stars"] == 5221

    html = (week / "email.html").read_text(encoding="utf-8")
    assert "구독자님" in html
    assert "IBM Plex Sans KR" in html
    cards = html.split("data-card=")[1:]
    assert "🧪 코드만 공개됐어요" in cards[0]
    assert "🧪 바로 써볼 수 있어요" in cards[1]
    assert "🖥️ 개인 GPU 약 1GB" in cards[4]
    assert sum("🖥️" in c for c in cards) == 1
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
        "use_idea_ko",
    }
    for name in fields:
        assert "url" not in name and "rank" not in name and "verdict" not in name
        assert "star" not in name


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
