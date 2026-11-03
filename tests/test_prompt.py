"""System prompt and user block content (D-04, D-05, D-07, D-18, T-01-09)."""

from conftest import FakeAnthropic

from newsletter.schema import HfEntry
from newsletter.stages import analyze
from newsletter.store import PROMPTS_DIR

AI_TYPES = ["LLM", "비전", "멀티모달", "음성", "에이전트", "이미지/비디오 생성", "기타"]
URL_PAPER = "2610.32749"  # rank 3 in W44; its live abstract embeds a URL


def _entries(hf_pages) -> dict[str, HfEntry]:
    return {d["paper"]["id"]: HfEntry.model_validate(d) for page in hf_pages for d in page}


def _call(hf_pages, paper_id=URL_PAPER):
    fake = FakeAnthropic()
    analyze.analyze_one(fake, _entries(hf_pages)[paper_id], rank=1)
    assert len(fake.calls) == 1
    return fake.calls[0]["kw"]


def _first_heading(text: str) -> str:
    return next(line for line in text.splitlines() if line.startswith("# "))


def test_system_is_one_cached_block_with_both_files(hf_pages):
    system = _call(hf_pages)["system"]
    assert isinstance(system, list) and len(system) == 1
    block = system[0]
    assert block["type"] == "text"
    assert block["cache_control"] == {"type": "ephemeral"}

    text = block["text"]
    humanizer = (PROMPTS_DIR / "humanizer_ko.md").read_text(encoding="utf-8")
    paper = (PROMPTS_DIR / "analyze_paper.md").read_text(encoding="utf-8")
    assert _first_heading(humanizer) in text
    assert paper.strip() in text
    assert humanizer.strip() in text
    assert text.index(paper.strip()) < text.index(humanizer.strip())
    assert len(text) >= 1500


def test_system_carries_rules_and_ai_types(hf_pages):
    text = _call(hf_pages)["system"][0]["text"]
    for label in AI_TYPES:
        assert f"`{label}`" in text, label
    # D-04/D-05 language rule with the CONTEXT example
    assert "Qwen3-VL: long-context 멀티모달 추론 개선" in text
    for term in ("fine-tuning", "RAG", "diffusion", "MoE"):
        assert term in text
    # D-07 grounding (unknown -> 확인 필요), injection fence, humanizer core subset
    assert "정확히 `확인 필요`" in text
    assert "<paper>" in text
    for word in ("혁신적", "획기적", "게임 체인저", "단순히", "—"):
        assert word in text
    assert text.splitlines()[0] == "<!-- prompt-version: 5 -->"


def test_prompt_claude_gpt_section(hf_pages):
    """ANLY-02, D-06: four labels, base rate, self-hosted weights never 직접 사용."""
    text = _call(hf_pages)["system"][0]["text"]
    paper = (PROMPTS_DIR / "analyze_paper.md").read_text(encoding="utf-8")
    assert "### `claude_gpt`" in paper and "### `claude_gpt_reason_ko`" in paper
    for label in ("직접 사용", "기법 적용 가능", "해당 없음", "확인 필요"):
        assert f"`{label}`" in text, label
    assert "대부분의 논문은 `기법 적용 가능` 또는 `해당 없음`이에요." in text
    assert "직접 호스팅해야 하는 가중치는 `직접 사용`이 아닙니다" in text
    for term in ("MCP server", "plugin", "Skill", "API"):
        assert term in text, term
    assert "60자" in paper
    assert "열한 필드" in paper and "`claude_gpt_reason_ko`)" in paper


def test_tone_rule_is_haeyo_in_both_prompts():
    """D-11 / D-20: no instruction left that asks for 하다체 endings."""
    humanizer = (PROMPTS_DIR / "humanizer_ko.md").read_text(encoding="utf-8")
    paper = (PROMPTS_DIR / "analyze_paper.md").read_text(encoding="utf-8")
    assert "해요체" in humanizer
    assert "해요체" in paper and "## 말투" in paper
    for old in ("~한다", '~할 수 있다"처럼', "~이다/~한다", "짧게 끝나는 평서문"):
        assert old not in humanizer, old
        assert old not in paper, old
    # D-12: non-specialist reader, English terms kept
    assert "AI 연구자가 아닙니다" in paper
    assert "영어 그대로" in paper


def test_system_names_v3_fields_and_one_idea(hf_pages):
    text = _call(hf_pages)["system"][0]["text"]
    for field in (
        "does_ko",
        "new_ko",
        "result_ko",
        "kind_ko",
        "architecture_ko",
        "use_idea_ko",
        "확인 필요",
    ):
        assert field in text, field
    # D-13: exactly one idea line, never the old two-idea list
    assert "use_ideas" not in text
    assert "### `use_idea_ko`" in text
    assert "아홉 필드" in text and "여덟 필드" not in text
    for two in ("두 개", "2개", "두 가지", "0..2"):
        assert two not in text, two
    # T-01.2-07: facts stay code-owned
    section = text.split("### `use_idea_ko`")[1]
    for word in ("라이선스", "무료", "50자"):
        assert word in section, word


def test_empty_brackets_are_stripped_from_paper_input():
    assert analyze.strip_urls("Code at (https://github.com/x/y) here.") == "Code at here."
    assert analyze.strip_urls("demo [http://a.b/c] and （ ） end") == "demo and end"
    assert analyze.strip_urls("keep (RAG) here") == "keep (RAG) here"


def test_user_block_is_fenced_and_url_free(hf_pages):
    entry = _entries(hf_pages)[URL_PAPER]
    assert "http" in entry.paper.summary
    content = _call(hf_pages)["messages"][0]["content"]

    assert content.startswith("<paper>\n")
    assert content.rstrip().endswith("</paper>")
    assert "http" not in content
    # the rest of the abstract survives URL stripping
    kept = analyze.strip_urls(entry.paper.summary)
    assert kept and kept in content
    assert len(kept) > len(entry.paper.summary) // 2
    has_gh = "yes" if (entry.paper.githubRepo or "").startswith("https://") else "no"
    assert f"has_github: {has_gh}" in content
    assert "has_project_page: yes" in content or "has_project_page: no" in content


def test_synthetic_urls_are_stripped_everywhere(hf_pages):
    entry = _entries(hf_pages)[URL_PAPER]
    paper = entry.paper.model_copy(
        update={
            "title": "Model X http://a.b/c release",
            "summary": "Code at https://github.com/x/y and demo http://a.b/c here.",
            "ai_summary": "See https://github.com/x/y.",
            "ai_keywords": ["RAG", "https://github.com/x/y", "MoE http://a.b/c"],
        }
    )
    fake = FakeAnthropic()
    analyze.analyze_one(fake, entry.model_copy(update={"paper": paper}), rank=1)
    content = fake.user_texts()[0]
    assert "http" not in content
    assert "Code at and demo here." in content
    assert "hf_ai_keywords: RAG, MoE" in content


def test_flags_are_yes_no(hf_pages):
    entry = next(iter(_entries(hf_pages).values()))
    paper = entry.paper.model_copy(
        update={"githubRepo": "https://github.com/x/y", "projectPage": None}
    )
    block = analyze.paper_block(entry.model_copy(update={"paper": paper}))
    assert "has_github: yes" in block
    assert "has_project_page: no" in block
