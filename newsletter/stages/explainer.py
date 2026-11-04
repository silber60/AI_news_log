"""AI 기술 쉽게 보기 (EXPL-01/02, D-04, D-05, D-12).

One Claude call reads this week's items (titles, type, summaries, kind and
architecture; no verdicts, no URLs) and the past-topic list, and explains one
technique the items use. Code checks the result, retries once with problem
codes, and returns None on any remaining failure, so the section stays hidden.
Code copies the image from the first related item that has one; Claude never
supplies it. The explainer never fails the build. Logs carry attempt numbers
and reason codes only, never the topic or any body text.
"""

import logging

import anthropic

from newsletter.schema import Explainer, ExplainerLLM, Item
from newsletter.stages import analyze, headline
from newsletter.store import PROMPTS_DIR

log = logging.getLogger(__name__)

MAX_PAST_SHOWN = 52
MAX_RELATED = 3
_TEXT_FIELDS = ("topic", "point_ko", "body_ko", "example_ko")


def explainer_system_prompt() -> str:
    """explainer.md + humanizer_ko.md as one text, sent as one cached block (HUMN-01)."""
    head = (PROMPTS_DIR / "explainer.md").read_text(encoding="utf-8").strip()
    humanizer = (PROMPTS_DIR / "humanizer_ko.md").read_text(encoding="utf-8").strip()
    return head + "\n\n" + humanizer


def _fields(it: Item) -> list[tuple[str, str]]:
    lines = it.summary_lines_ko + [""] * (3 - len(it.summary_lines_ko))
    return [
        ("title_ko", headline._clean(it.title_ko)),
        ("title_en", headline._clean(it.title_en)),
        ("ai_type", it.ai_type),
        ("summary_ko", headline._clean(it.summary_ko)),
        ("does_ko", headline._clean(lines[0])),
        ("new_ko", headline._clean(lines[1])),
        ("result_ko", headline._clean(lines[2])),
        ("kind_ko", headline._clean(it.model_info.kind_ko)),
        ("architecture_ko", headline._clean(it.model_info.architecture_ko)),
    ]


def items_block(items: list[Item], past: list[str]) -> str:
    lines = ["<items>"]
    for it in items:
        lines.append(f"rank: {it.rank}")
        lines += [f"{key}: {value}" for key, value in _fields(it)]
        lines.append("")
    lines[-1] = "</items>"
    lines.append("")
    lines.append("<past_topics>")
    shown = [headline._clean(t) for t in past[:MAX_PAST_SHOWN]]
    lines += [t for t in shown if t] or ["(없음)"]
    lines.append("</past_topics>")
    return "\n".join(lines)


def _normalize(out: ExplainerLLM) -> ExplainerLLM:
    return out.model_copy(update={f: analyze._one_line(getattr(out, f)) for f in _TEXT_FIELDS})


def check_ranks(ranks: list[int], n: int) -> list[tuple[str, str]]:
    if not 1 <= len(ranks) <= MAX_RELATED:
        return [("ex_ranks", f"related_ranks가 {len(ranks)}개임 (1-{MAX_RELATED}개여야 함)")]
    if len(set(ranks)) != len(ranks):
        return [("ex_ranks", "related_ranks에 같은 rank가 두 번 있음")]
    if any(not 1 <= r <= n for r in ranks):
        return [("ex_ranks", f"related_ranks가 1-{n} 범위를 벗어남")]
    return []


def check(out: ExplainerLLM, items: list[Item]) -> list[tuple[str, str]]:
    """Result-level rules. Messages name the field and the rule, never the model text."""
    errs: list[tuple[str, str]] = []
    for f in _TEXT_FIELDS:
        if not getattr(out, f).strip():
            errs.append(("ex_empty", f"{f}가 비어 있음"))
    return errs + check_ranks(out.related_ranks, len(items))


def _to_explainer(out: ExplainerLLM, items: list[Item]) -> Explainer:
    # D-04: the image comes from the first related item that has one, never Claude.
    image = next((items[r - 1].image for r in out.related_ranks if items[r - 1].image), None)
    return Explainer(
        topic=out.topic,
        point_ko=out.point_ko,
        body_ko=out.body_ko,
        example_ko=out.example_ko,
        related_ranks=list(out.related_ranks),
        image=image,
    )


def _codes(problems: list[tuple[str, str]]) -> str:
    return "+".join(code for code, _ in problems) or "unknown"


def write_explainer(items: list[Item], past: list[str], client) -> Explainer | None:
    """One explainer for this week, at most two attempts, then None."""
    block = items_block(items, past)
    system = explainer_system_prompt()
    problems: list[tuple[str, str]] = []
    for attempt in (1, 2):
        try:
            resp = analyze._request(
                client,
                analyze._with_feedback(block, problems),
                system=system,
                output_format=ExplainerLLM,
            )
        except anthropic.APIError as e:
            log.warning(
                "explainer=none reason=api_error status=%s attempt=%d",
                getattr(e, "status_code", None),
                attempt,
            )
            return None
        except ValueError:  # client-side schema validation
            problems = [("schema", "출력이 스키마와 맞지 않음")]
            log.warning("explainer attempt=%d reason=schema", attempt)
            continue
        if resp.stop_reason in ("refusal", "max_tokens"):
            problems = [
                (f"stop_{resp.stop_reason}", f"응답이 stop_reason={resp.stop_reason}로 끝남")
            ]
            log.info("explainer attempt=%d reason=%s", attempt, _codes(problems))
            continue
        out = resp.parsed_output
        if not isinstance(out, ExplainerLLM):
            problems = [("no_output", "구조화된 출력이 비어 있음")]
            log.info("explainer attempt=%d reason=no_output", attempt)
            continue
        out = _normalize(out)
        problems = check(out, items)
        if not problems:
            log.info("explainer=claude attempt=%d", attempt)
            return _to_explainer(out, items)
        log.info("explainer attempt=%d reason=%s", attempt, _codes(problems))
    log.info("explainer=none reason=%s", _codes(problems))
    return None
