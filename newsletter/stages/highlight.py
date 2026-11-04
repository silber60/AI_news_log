"""이번 주 바로 써볼 만한 것 (HILT-01..03, D-01..D-03, D-11).

The per-paper analyze call labels each item's Skill/GPTs fit. This stage sends
only the items Claude labelled as fitting (no verdicts, no URLs) to one pick
call. Code checks every pick: its rank must be a candidate and unique, there are
at most 3, and 왜 좋은지 / 어떻게 만들지 are 1-2 short 해요체 sentences with no
step list, URL, hype word or newsletter-authorship wording. A failing pick
triggers one retry whose feedback names problems only; after it, passing picks
are kept and failing ones dropped. Code copies the tag from the item's own
label; Claude never supplies it. No candidate means no call, and any failure
returns [], so the section shows its fallback line. Logs carry attempt numbers,
counts and reason codes only, never pick text or a title.
"""

import logging
import re

import anthropic

from newsletter.schema import Highlight, HighlightPickLLM, HighlightsLLM, Item
from newsletter.stages import analyze, headline
from newsletter.store import PROMPTS_DIR

log = logging.getLogger(__name__)

MAX_PICKS = 3
NO_FIT = "해당 없음"
TEXT_LIMIT = 70  # research §3 (A2): two lines at 14px minus the "왜 좋은지: " label
MIN_SENTENCES, MAX_SENTENCES = 1, 2
# D-03: a direction, never a step-by-step list.
_STEPS_RE = re.compile(r"(?:^|\s)(?:\d+[.)]|[①-⑩]|첫째|둘째)")


def highlight_system_prompt() -> str:
    """highlight.md + humanizer_ko.md as one text, sent as one cached block (HUMN-01)."""
    head = (PROMPTS_DIR / "highlight.md").read_text(encoding="utf-8").strip()
    humanizer = (PROMPTS_DIR / "humanizer_ko.md").read_text(encoding="utf-8").strip()
    return head + "\n\n" + humanizer


def candidates(items: list[Item]) -> list[Item]:
    """Items Claude labelled as a Claude Skill / GPTs fit (D-02, D-11)."""
    return [it for it in items if it.skill_gpt.fit != NO_FIT]


def items_block(cands: list[Item]) -> str:
    lines = ["<items>"]
    for it in cands:
        lines += [
            f"rank: {it.rank}",
            f"title_ko: {headline._clean(it.title_ko)}",
            f"ai_type: {it.ai_type}",
            f"summary_ko: {headline._clean(it.summary_ko)}",
            f"does_ko: {headline._clean(it.summary_lines_ko[0])}",
            f"skill_gpt_fit: {it.skill_gpt.fit}",
            f"skill_gpt_reason_ko: {headline._clean(it.skill_gpt.reason_ko or '')}",
            "",
        ]
    lines[-1] = "</items>"
    return "\n".join(lines)


def check_text(field: str, text: str) -> list[tuple[str, str]]:
    """D-03 rules for why_ko / how_ko. Messages name the field and the rule, never
    the model text."""
    if not text.strip():
        return [("hl_empty", f"{field}가 비어 있음")]
    errs: list[tuple[str, str]] = []
    if len(text) > TEXT_LIMIT:
        errs.append(("hl_len", f"{field}가 {len(text)}자로 {TEXT_LIMIT}자를 넘음"))
    sentences = [s for s in analyze._SENT_SPLIT.split(text.strip()) if s.strip()]
    if len(sentences) > MAX_SENTENCES:
        errs.append(("hl_sentences", f"{field}가 {len(sentences)}문장임 (1-2문장이어야 함)"))
    if analyze.not_haeyo(text):
        errs.append(("hl_tone", f"{field}의 문장이 해요체(~요)로 끝나지 않음"))
    if _STEPS_RE.search(text):
        errs.append(("hl_steps", f"{field}에 번호나 단계 목록이 있음"))
    if headline._URL_RE.search(text):
        errs.append(("hl_url", f"{field}에 링크가 있음"))
    if any(w in text for w in headline.HYPE_WORDS):
        errs.append(("hl_hype", f"{field}에 과장 표현이 있음"))
    if headline.WRITTEN_BY_RE.search(text):
        errs.append(("hl_authorship", f"{field}가 뉴스레터 작성 방식을 언급함"))
    return errs


def review(
    picks: list[HighlightPickLLM], ranks: set[int]
) -> tuple[list[HighlightPickLLM], list[tuple[str, str]]]:
    """Passing picks (normalized, Claude's order, at most MAX_PICKS) and the
    problems of the others. Messages carry pick positions and rules only."""
    kept: list[HighlightPickLLM] = []
    problems: list[tuple[str, str]] = []
    seen: set[int] = set()
    for i, p in enumerate(picks, 1):
        pick = p.model_copy(
            update={"why_ko": analyze._one_line(p.why_ko), "how_ko": analyze._one_line(p.how_ko)}
        )
        errs: list[tuple[str, str]] = []
        if pick.rank not in ranks:
            errs.append(("hl_rank", "후보 목록에 없는 rank를 고름"))
        elif pick.rank in seen:
            errs.append(("hl_duplicate", "같은 rank를 두 번 고름"))
        errs += check_text("why_ko", pick.why_ko) + check_text("how_ko", pick.how_ko)
        if errs:
            problems += [(code, f"{i}번째 pick: {msg}") for code, msg in errs]
            continue
        seen.add(pick.rank)
        kept.append(pick)
    if len(picks) > MAX_PICKS:
        problems.append(("hl_count", f"picks가 {len(picks)}개로 {MAX_PICKS}개를 넘음"))
    return kept[:MAX_PICKS], problems


def _to_highlights(picks: list[HighlightPickLLM], items: list[Item]) -> list[Highlight]:
    # The tag is copied from the item's own label; candidates exclude 해당 없음.
    return [
        Highlight(
            rank=p.rank, tag=items[p.rank - 1].skill_gpt.fit, why_ko=p.why_ko, how_ko=p.how_ko
        )
        for p in picks
    ]


def _codes(problems: list[tuple[str, str]]) -> str:
    return "+".join(code for code, _ in problems) or "unknown"


def write_highlights(items: list[Item], client) -> list[Highlight]:
    """0-3 highlights from this week's candidates, at most two attempts; [] on failure."""
    cands = candidates(items)
    if not cands:
        log.info("highlight=none reason=no_candidate")
        return []
    ranks = {it.rank for it in cands}
    block = items_block(cands)
    system = highlight_system_prompt()
    problems: list[tuple[str, str]] = []
    best: list[HighlightPickLLM] = []  # passing picks of the latest usable attempt
    best_attempt = 0
    for attempt in (1, 2):
        try:
            resp = analyze._request(
                client,
                analyze._with_feedback(block, problems),
                system=system,
                output_format=HighlightsLLM,
            )
        except anthropic.APIError as e:
            log.warning(
                "highlight=none reason=api_error status=%s attempt=%d",
                getattr(e, "status_code", None),
                attempt,
            )
            break
        except ValueError:  # client-side schema validation
            problems = [("schema", "출력이 스키마와 맞지 않음")]
            log.warning("highlight attempt=%d reason=schema", attempt)
            continue
        if resp.stop_reason in ("refusal", "max_tokens"):
            problems = [
                (f"stop_{resp.stop_reason}", f"응답이 stop_reason={resp.stop_reason}로 끝남")
            ]
            log.info("highlight attempt=%d reason=%s", attempt, _codes(problems))
            continue
        out = resp.parsed_output
        if not isinstance(out, HighlightsLLM):
            problems = [("no_output", "구조화된 출력이 비어 있음")]
            log.info("highlight attempt=%d reason=no_output", attempt)
            continue
        best, problems = review(out.picks, ranks)
        best_attempt = attempt
        if not problems:
            break
        log.info("highlight attempt=%d reason=%s", attempt, _codes(problems))
    if best:
        log.info("highlight=claude picks=%d attempt=%d", len(best), best_attempt)
        return _to_highlights(best, items)
    if best_attempt and not problems:  # Claude found nothing that fits: valid
        log.info("highlight=claude picks=0 attempt=%d", best_attempt)
    elif problems:
        log.info("highlight=none reason=%s", _codes(problems))
    return []
