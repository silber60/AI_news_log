"""이번 주 트렌드 총평 (ANLY-05, D-07): 2-3 해요체 sentences under the greeting.

One Claude call after the analysis reads every item's titles, type and summary
(no verdicts, no URLs) and writes a short paragraph. Code checks it, retries
once with problem codes, and returns None on any remaining failure, so the trend
section stays hidden. The trend never fails the build. Logs carry attempt
numbers and reason codes only, never the paragraph or any title.
"""

import logging
import re

import anthropic

from newsletter.schema import Item, TrendLLM
from newsletter.stages import analyze, headline
from newsletter.store import PROMPTS_DIR

log = logging.getLogger(__name__)

TREND_LIMIT = 300
MIN_SENTENCES, MAX_SENTENCES = 2, 3
# Research §6 name pattern, widened to accept a leading digit ("3D") so a generic
# term is never read as a stray capital "D".
_NAME_RE = re.compile(r"(?<![A-Za-z0-9])[A-Za-z0-9]*[A-Za-z][A-Za-z0-9]*(?:[-.+][A-Za-z0-9]+)*")
_NAME_PART_RE = re.compile(r"[-.+]")
_NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")
_RANK_RE = re.compile(r"(\d+)\s*위")
# Generic AI terms a trend may use without naming a model (casefolded on use).
GENERIC_TERMS = frozenset(
    t.casefold()
    for t in (
        "AI", "LLM", "LLMs", "VLM", "VLMs", "VLA", "MoE", "RAG", "GPU", "CPU", "API",
        "3D", "2D", "4D", "TTS", "ASR", "OCR", "NLP", "RL", "RLHF", "SFT", "LoRA",
        "CoT", "VQA", "ViT", "VAE", "GAN",
    )
)  # fmt: skip


def trend_system_prompt() -> str:
    """trend.md + humanizer_ko.md as one text, sent as one cached block."""
    head = (PROMPTS_DIR / "trend.md").read_text(encoding="utf-8").strip()
    humanizer = (PROMPTS_DIR / "humanizer_ko.md").read_text(encoding="utf-8").strip()
    return head + "\n\n" + humanizer


def _fields(it: Item) -> list[tuple[str, str]]:
    return [
        ("title_ko", headline._clean(it.title_ko)),
        ("title_en", headline._clean(it.title_en)),
        ("ai_type", it.ai_type),
        ("summary_ko", headline._clean(it.summary_ko)),
    ]


def items_block(items: list[Item]) -> str:
    lines = ["<items>"]
    for it in items:
        lines.append(f"rank: {it.rank}")
        lines += [f"{key}: {value}" for key, value in _fields(it)]
        lines.append("")
    lines[-1] = "</items>"
    return "\n".join(lines)


def _allowed_names(items: list[Item]) -> set[str]:
    """Casefolded name tokens (and their -/./+ parts) from this week's cleaned
    title_en / title_ko / summary_ko, plus GENERIC_TERMS."""
    allowed = set(GENERIC_TERMS)
    for it in items:
        for key, value in _fields(it):
            if key == "ai_type":
                continue
            for tok in _NAME_RE.findall(value):
                allowed.add(tok.casefold())
                allowed.update(p.casefold() for p in _NAME_PART_RE.split(tok) if p)
    return allowed


def _is_name_like(tok: str) -> bool:
    return any(c.isupper() or c.isdigit() for c in tok)


def check_trend(text: str, items: list[Item]) -> list[tuple[str, str]]:
    """Code-enforced trend rules (research §6). Messages name the rule, never the
    model text."""
    errs: list[tuple[str, str]] = []
    if not text.strip():
        return [("trend_empty", "trend_ko가 비어 있음")]
    sentences = [s for s in analyze._SENT_SPLIT.split(text.strip()) if s.strip()]
    if not MIN_SENTENCES <= len(sentences) <= MAX_SENTENCES:
        errs.append(("trend_sentences", f"trend_ko가 {len(sentences)}문장임 (2-3문장이어야 함)"))
    if len(text) > TREND_LIMIT:
        errs.append(("trend_len", f"trend_ko가 {len(text)}자로 {TREND_LIMIT}자를 넘음"))
    if analyze.not_haeyo(text):
        errs.append(("trend_tone", "trend_ko의 문장이 해요체(~요)로 끝나지 않음"))
    if headline._URL_RE.search(text):
        errs.append(("trend_url", "trend_ko에 링크가 있음"))
    if any(w in text for w in headline.HYPE_WORDS):
        errs.append(("trend_hype", "trend_ko에 과장 표현이 있음"))
    if headline.AUTHORSHIP_RE.search(text):
        errs.append(("trend_authorship", "trend_ko가 뉴스레터 작성 방식을 언급함"))
    allowed = _allowed_names(items)
    names = _NAME_RE.findall(text)
    unknown = [t for t in names if _is_name_like(t) and t.casefold() not in allowed]
    if unknown:
        errs.append(
            ("trend_unknown_name", f"trend_ko에 이번 주 항목에 없는 이름이 {len(unknown)}개 있음")
        )
    n = len(items)
    if any(not 1 <= int(r) <= n for r in _RANK_RE.findall(text)):
        errs.append(("trend_rank", f"trend_ko의 순위가 1-{n} 범위를 벗어남"))
    # Numbers outside name tokens ("3D", "GPT-5") and rank mentions must appear in
    # the input text; otherwise they are invented statistics.
    rest = _RANK_RE.sub(" ", _NAME_RE.sub(" ", text))
    known = set(_NUMBER_RE.findall(items_block(items)))
    if any(num not in known for num in _NUMBER_RE.findall(rest)):
        errs.append(("trend_number", "trend_ko에 입력에 없는 숫자가 있음"))
    return errs


def write_trend(items: list[Item], client) -> str | None:
    """Claude trend paragraph, at most two attempts, then None."""
    block = items_block(items)
    system = trend_system_prompt()
    problems: list[tuple[str, str]] = []
    for attempt in (1, 2):
        try:
            resp = analyze._request(
                client,
                analyze._with_feedback(block, problems),
                system=system,
                output_format=TrendLLM,
            )
        except anthropic.APIError as e:
            log.warning("trend=none reason=api_error status=%s", getattr(e, "status_code", None))
            return None
        except ValueError:  # client-side schema validation
            problems = [("schema", "출력이 스키마와 맞지 않음")]
            log.warning("trend attempt=%d reason=schema", attempt)
            continue
        if resp.stop_reason in ("refusal", "max_tokens"):
            problems = [
                (f"stop_{resp.stop_reason}", f"응답이 stop_reason={resp.stop_reason}로 끝남")
            ]
            continue
        out = resp.parsed_output
        if not isinstance(out, TrendLLM):
            problems = [("no_output", "구조화된 출력이 비어 있음")]
            continue
        text = analyze._one_line(out.trend_ko)
        problems = check_trend(text, items)
        if not problems:
            log.info("trend=claude attempt=%d", attempt)
            return text
        log.info("trend attempt=%d reason=%s", attempt, "+".join(code for code, _ in problems))
    reason = "+".join(code for code, _ in problems) or "unknown"
    log.info("trend=none reason=%s", reason)
    return None
