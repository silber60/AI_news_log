"""Offline end-to-end: W44 fixture -> run_build -> archive -> deliver --mode test."""

import json

import anthropic
import httpx2
import respx
from conftest import (
    DEFAULT_CLAUDE_GPT_REASON,
    DEFAULT_EXPLAINER_TOPIC,
    DEFAULT_HIGHLIGHT_HOW,
    DEFAULT_HIGHLIGHT_WHY,
    DEFAULT_SKILL_GPT_REASON,
    DEFAULT_TREND,
    FakeAnthropic,
    default_analysis,
    default_notes,
    default_response,
    make_parsed,
    mock_hf_week,
)

from newsletter.schema import UNKNOWN, HfEntry, Issue, TrendLLM
from newsletter.stages import highlight, notes
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
# D-03, D-09: stricter of the GitHub code license and the HF weights license.
STAR_COMMERCIAL = ["가능", "가능", "확인 필요", "가능", "조건부"] + ["가능"] * 5
STAR_POC = ["코드만", "바로 가능", "바로 가능", "코드만", "바로 가능"] + ["코드만"] * 5
WEEK_FILES = (
    "raw.json",
    "selected.json",
    "enriched.json",
    "issue.json",
    "email.html",
    "email.txt",
)


def _build(hf_pages, fake: FakeAnthropic) -> Issue:
    from newsletter.pipeline import run_build

    with respx.mock(assert_all_mocked=True, assert_all_called=True) as router:
        routes = mock_hf_week(router, hf_pages, ISSUE_ID)
        issue = run_build(ISSUE_ID, claude_client=fake)
    assert all(r.call_count == 1 for r in routes)
    return issue


def test_run_build_writes_archive(hf_pages, archive_tmp, monkeypatch):
    from newsletter import topics

    monkeypatch.delenv("NEWSLETTER_TOPICS_PATH", raising=False)
    topics_before = topics.topics_path().read_bytes()
    fake = FakeAnthropic()
    issue = _build(hf_pages, fake)
    # D-06: the build only reads the committed topic record.
    assert topics.topics_path().read_bytes() == topics_before

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

    # EXPL-01, D-04: one explainer tied to this week's items.
    assert stored.explainer is not None
    assert stored.explainer.topic == DEFAULT_EXPLAINER_TOPIC
    assert stored.explainer.related_ranks == [1, 2]
    # HILT-01..03, schema v4: demo items lead the candidates; tag and link are code's.
    cands = highlight.candidates(stored.items)
    assert [h.rank for h in stored.highlights] == [it.rank for it in cands[:3]]
    assert [h.rank for h in stored.highlights] == [2, 3, 5]
    assert all(highlight.space_url(stored.items[h.rank - 1]) for h in stored.highlights)
    for h in stored.highlights:
        it = stored.items[h.rank - 1]
        assert h.tag == highlight.tag_for(it)
        assert h.demo_url == highlight.demo_url(it)
    assert all(
        (h.why_ko, h.how_ko) == (DEFAULT_HIGHLIGHT_WHY, DEFAULT_HIGHLIGHT_HOW)
        for h in stored.highlights
    )
    # ANLY-05, D-07: the trend call's default text.
    assert stored.trend_ko == DEFAULT_TREND
    # EVID-03: PoC decided by code from the HF paper capture.
    assert [it.poc.verdict for it in stored.items] == STAR_POC
    assert [it.commercial.verdict for it in stored.items] == STAR_COMMERCIAL
    # Both sides are stored separately (EVID-02).
    c1, c3, c5 = (stored.items[i].commercial for i in (0, 2, 4))
    assert (c1.code_license.spdx_id, c1.weights_license) == ("Apache-2.0", None)
    assert c3.code_license.spdx_id is None and c3.weights_license.spdx_id == "apache-2.0"
    assert (c5.code_license.spdx_id, c5.weights_license.spdx_id) == ("Apache-2.0", "gemma")
    for it in stored.items:
        assert it.poc.evidence
        # ANLY-02, D-06: Claude's label and reason from the analyze call.
        assert it.claude_gpt.verdict == "기법 적용 가능"
        assert it.claude_gpt.reason_ko == DEFAULT_CLAUDE_GPT_REASON
        assert it.skill_gpt.fit == "Claude Skill"
        assert it.skill_gpt.reason_ko == DEFAULT_SKILL_GPT_REASON
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
    assert stored.schema_version == 4
    name = stored.items[0].title_ko.split(":", 1)[0].strip()[:20]
    assert stored.headline_ko == "🤖 말하면 로봇이 움직인다? 이번 주 AI 모델 10"
    assert fallback_headline(stored.items) == f"🧠 {name} 등 이번 주 AI 모델 10"
    assert fallback_headline(stored.items[:1]) == f"🧠 {name} 이번 주 AI 모델 1"

    # 10 analysis calls, then notes, trend, highlight, explainer and headline (one call each).
    assert len(fake.calls) == 15
    texts = fake.user_texts()
    for text in texts[:10]:
        assert "http" not in text
        assert text.startswith("<paper>")
    assert "skill_gpt_fit: Claude Skill" in texts[12]
    for text in texts[10:15]:
        assert text.startswith("<items>")
        assert "http" not in text
    assert "<past_topics>" in texts[13]
    # HUMN-03, D-13: every default text is lint-clean, so no polish call is made.
    assert not any("<fields>" in t for t in texts)

    # ANLY-04, D-14: Claude reasons for known verdicts, the code reason otherwise.
    note = default_notes({"messages": [{"content": "rank: 1"}]}).notes[0]
    commercial_reasons = [it.commercial.reason_ko for it in stored.items]
    assert commercial_reasons == [
        notes.UNKNOWN_REASON if v == UNKNOWN else note.commercial_reason_ko for v in STAR_COMMERCIAL
    ]
    assert commercial_reasons.count(note.commercial_reason_ko) == 9
    assert commercial_reasons.count(notes.UNKNOWN_REASON) == 1
    assert [it.poc.reason_ko for it in stored.items] == [note.poc_reason_ko] * 10

    raw_text = (week / "raw.json").read_text(encoding="utf-8")
    assert '"authors"' not in raw_text
    assert '"submittedBy"' not in raw_text
    raw = json.loads(raw_text)
    assert raw["count"] == len(raw["entries"]) == 214
    selected = json.loads((week / "selected.json").read_text(encoding="utf-8"))
    assert [s["paper_id"] for s in selected["items"]] == expected
    assert [s["basis"] for s in selected["items"]] == ["stars"] * 10
    assert selected["items"][0]["github_stars"] == 5221

    # EVID-01: the raw license evidence behind each verdict is archived.
    enriched_text = (week / "enriched.json").read_text(encoding="utf-8")
    assert '"authors"' not in enriched_text and "_ko" not in enriched_text
    enriched = json.loads(enriched_text)
    assert (enriched["issue_id"], enriched["count"]) == (ISSUE_ID, 10)
    assert [r["paper_id"] for r in enriched["items"]] == expected
    r3 = enriched["items"][2]
    assert r3["github_license"]["status"] == "ok"
    assert r3["github_license"]["spdx_id"] in (None, "NOASSERTION")
    assert r3["weights_license"]["license"] == "apache-2.0"

    html = (week / "email.html").read_text(encoding="utf-8")
    assert "구독자님" in html
    # D-13: the trend sits right under the greeting, above the top 3.
    greeting, trend_pos, top3 = (
        html.index(f'data-section="{n}"') for n in ("greeting", "trend", "top3")
    )
    assert greeting < trend_pos < top3
    assert greeting < html.index(DEFAULT_TREND) < top3
    # D-01, HILT-02: the highlight section sits below the trend and above the top 3.
    hl = html.index('data-section="highlight"')
    assert trend_pos < hl < top3
    hl_html = html[hl:top3]
    for h in stored.highlights:
        assert stored.items[h.rank - 1].title_ko in hl_html
    assert hl_html.count(DEFAULT_HIGHLIGHT_WHY) == 3
    assert "이번 주는 해당 항목 없음" not in html
    # D-04: the explainer sits between the top 3 and the rest.
    ex_pos = html.index('data-section="explainer"')
    assert top3 < ex_pos < html.index('data-section="rest"')
    assert DEFAULT_EXPLAINER_TOPIC in html[ex_pos:]
    assert "IBM Plex Sans KR" in html
    cards = html.split("data-card=")[1:]
    assert "🧪 코드만 공개됐어요" in cards[0]
    assert "💼 코드 상업 이용 가능" in cards[0]
    assert 'href="https://github.com/InternLM/xtuner/blob/main/LICENSE"' in cards[0]
    assert "💼 상업 이용 가능" in cards[1]
    assert "💼" not in cards[2]
    assert "💼 조건부 상업 이용" in cards[4]
    assert "🧪 바로 써볼 수 있어요" in cards[1]
    assert "🖥️ 개인 GPU 약 1GB" in cards[4]
    assert sum("🖥️" in c for c in cards) == 1
    assert len(cards) == 10
    assert all("🤖 Claude/GPT 기법 적용" in c for c in cards)
    assert "구독자님" in (week / "email.txt").read_text(encoding="utf-8")


DIRTY_LINE = "혁신적인 이전 방법과 다른 점이에요."


def _dirty_rank2(kw):
    a = default_analysis(kw)
    return make_parsed(a.model_copy(update={"new_ko": DIRTY_LINE}))


def _dump(issue: Issue) -> dict:
    data = issue.model_dump(mode="json")
    data.pop("generated_at")
    return data


def test_flagged_line_gets_one_polish_call(hf_pages, archive_tmp):
    """HUMN-03, D-08, D-13: one AI-tell sentence is rewritten by a 16th call before
    anything is written; every other leaf equals the clean build."""
    clean = _build(hf_pages, FakeAnthropic())

    fake = FakeAnthropic([default_response, _dirty_rank2])
    issue = _build(hf_pages, fake)
    assert len(fake.calls) == 16
    last = fake.user_texts()[-1]
    assert last.startswith("<fields>")
    assert last.count("id: ") == 1
    assert "id: items.1.summary_lines_ko.1\n" in last
    assert "혁신적인" in last

    week = archive_tmp / "archive" / ISSUE_ID
    stored = Issue.model_validate_json((week / "issue.json").read_text(encoding="utf-8"))
    assert stored == issue
    assert stored.items[1].summary_lines_ko[1] == "이전 방법과 다른 점이에요."
    assert _dump(stored) == _dump(clean)
    for name in ("email.html", "email.txt"):
        assert "혁신적인" not in (week / name).read_text(encoding="utf-8")


def test_trend_api_error_keeps_the_build(hf_pages, archive_tmp):
    """A failed trend call is non-fatal: no trend_ko and no trend section."""
    req = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")

    class TrendDown(FakeAnthropic):
        def _handle(self, ns, kw):
            if kw.get("output_format") is TrendLLM:
                self.calls.append({"ns": ns, "kw": kw})
                raise anthropic.APIConnectionError(request=req)
            return super()._handle(ns, kw)

    fake = TrendDown()
    issue = _build(hf_pages, fake)

    week = archive_tmp / "archive" / ISSUE_ID
    stored = Issue.model_validate_json((week / "issue.json").read_text(encoding="utf-8"))
    assert stored == issue
    assert stored.trend_ko is None
    assert stored.headline_ko == "🤖 말하면 로봇이 움직인다? 이번 주 AI 모델 10"
    assert len(stored.items) == 10
    html = (week / "email.html").read_text(encoding="utf-8")
    assert 'data-section="trend"' not in html
    assert DEFAULT_TREND not in html


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
        "claude_gpt",
        "claude_gpt_reason_ko",
        "skill_gpt_fit",
        "skill_gpt_reason_ko",
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
    # Phase 4.2: Resend SMTP on the owner's domain; the Gmail secret is the Reply-To.
    assert (smtp.host, smtp.port) == ("smtp.resend.com", 465)
    assert smtp.login_calls == [("resend", "abcdefghijklmnop")]
    assert len(smtp.sent) == 1
    msg = smtp.sent[0]
    assert msg.get_content_type() == "multipart/alternative"
    assert msg["To"] == "owner@example.com"
    assert msg["From"].addresses[0].addr_spec == "newsletter@modaklog.characterplanner.co.kr"
    assert msg["Reply-To"] == "sender@example.com"
    assert "<mailto:sender@example.com?subject=unsubscribe>" in msg["List-Unsubscribe"]
    assert str(msg["Subject"]) == "[TEST] " + build_subject(stored, "send")
    html = msg.get_body(preferencelist=("html",)).get_content()
    assert "구독자님" in html
