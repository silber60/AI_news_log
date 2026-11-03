"""이번 주 바로 써볼 만한 것 (HILT-01..03, D-01..D-03, D-11).

The per-paper analyze call labels each item's Skill/GPTs fit. This stage sends
only the items Claude labelled as fitting (no verdicts, no URLs) to one pick
call. Code keeps 1-3 unique picks whose rank is a candidate and copies the tag
from the item's own label; Claude never supplies it. No candidate means no call.
Any failure returns [], so the section shows its fallback line. Logs carry
attempt numbers, counts and reason codes only, never pick text or a title.
"""

import logging

import anthropic

from newsletter.schema import Highlight, HighlightPickLLM, HighlightsLLM, Item
from newsletter.stages import analyze, headline
from newsletter.store import PROMPTS_DIR

log = logging.getLogger(__name__)

MAX_PICKS = 3
NO_FIT = "해당 없음"


def highlight_system_prompt() -> str:
    """highlight.md + humanizer_ko.md as one text, sent as one cached block."""
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


def _keep(picks: list[HighlightPickLLM], ranks: set[int]) -> list[HighlightPickLLM]:
    """Candidate ranks only, first occurrence only, at most MAX_PICKS, in Claude's order."""
    kept: list[HighlightPickLLM] = []
    seen: set[int] = set()
    for p in picks:
        if p.rank in ranks and p.rank not in seen:
            seen.add(p.rank)
            kept.append(p)
    return kept[:MAX_PICKS]


def _to_highlights(picks: list[HighlightPickLLM], items: list[Item]) -> list[Highlight]:
    return [
        Highlight(
            rank=p.rank,
            tag=items[p.rank - 1].skill_gpt.fit,
            why_ko=analyze._one_line(p.why_ko),
            how_ko=analyze._one_line(p.how_ko),
        )
        for p in picks
    ]


def write_highlights(items: list[Item], client) -> list[Highlight]:
    """0-3 highlights from this week's candidates; [] on any failure."""
    cands = candidates(items)
    if not cands:
        log.info("highlight=none reason=no_candidate")
        return []
    ranks = {it.rank for it in cands}
    try:
        resp = analyze._request(
            client,
            items_block(cands),
            system=highlight_system_prompt(),
            output_format=HighlightsLLM,
        )
    except anthropic.APIError as e:
        log.warning("highlight=none reason=api_error status=%s", getattr(e, "status_code", None))
        return []
    except ValueError:
        log.warning("highlight=none reason=schema")
        return []
    out = resp.parsed_output
    if resp.stop_reason in ("refusal", "max_tokens") or not isinstance(out, HighlightsLLM):
        log.warning("highlight=none reason=no_output")
        return []
    picks = _keep(out.picks, ranks)
    log.info("highlight=claude picks=%d attempt=1", len(picks))
    return _to_highlights(picks, items)
