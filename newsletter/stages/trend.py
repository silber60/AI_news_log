"""이번 주 트렌드 총평 (ANLY-05, D-07): 2-3 해요체 sentences under the greeting.

One Claude call after the analysis reads every item's titles, type and summary
(no verdicts, no URLs) and writes a short paragraph. Code checks it, retries
once with problem codes, and returns None on any remaining failure, so the trend
section stays hidden. The trend never fails the build. Logs carry attempt
numbers and reason codes only, never the paragraph or any title.
"""

import logging

import anthropic

from newsletter.schema import Item, TrendLLM
from newsletter.stages import analyze, headline
from newsletter.store import PROMPTS_DIR

log = logging.getLogger(__name__)


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


def check_trend(text: str, items: list[Item]) -> list[tuple[str, str]]:
    """Code-enforced trend rules. Messages name the rule, never the model text."""
    errs: list[tuple[str, str]] = []
    if not text.strip():
        errs.append(("trend_empty", "trend_ko가 비어 있음"))
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
