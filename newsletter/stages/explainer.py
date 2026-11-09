"""AI 기술 쉽게 보기 (EXPL-01/02, D-04, D-05, D-12).

Rank order (owner request 2026-11-09, replaces the old one-retry repeat rule):
each call names a target rank, starting with #1, and Claude explains a technique
that item uses (related_ranks starts with that rank). When the topic matches a
past one (topics.is_repeat), the next rank is tried, then the next, up to
MAX_RANK_TRIES ranks. If every tried rank repeats, the first result is kept
and logged as explainer=repeat, so a repeat never empties the section.

Claude reads this week's items (titles, type, summaries, kind and architecture;
no verdicts, no URLs) and the past-topic list. Code checks every field (length,
sentence count, 해요체, URL, hype, authorship, unknown digit names, invented
numbers) and the related ranks; a failing result gets one retry with problem
codes for the same rank, and two failures return None, so the section stays
hidden. Code copies the image from the first related item that has one; Claude
never supplies it. The explainer never fails the build. Logs carry ranks,
attempt numbers and reason codes only, never the topic or any body text.
"""

import logging

import anthropic

from newsletter import topics
from newsletter.schema import Explainer, ExplainerLLM, Item
from newsletter.stages import analyze, headline, humanize, trend
from newsletter.store import PROMPTS_DIR

log = logging.getLogger(__name__)

MAX_PAST_SHOWN = 52
MAX_RELATED = 3
MAX_RANK_TRIES = 5  # ranks tried for a new topic; caps Claude calls on repeat weeks
_TEXT_FIELDS = ("topic", "point_ko", "body_ko", "example_ko")
# field -> (code, char limit, min sentences, max sentences); topic is a noun phrase.
_SHAPE = {
    "point_ko": ("ex_point", humanize.EXPLAINER_POINT_LIMIT, 1, 1),
    "body_ko": ("ex_body", humanize.EXPLAINER_BODY_LIMIT, 3, 4),
    "example_ko": ("ex_example", humanize.EXPLAINER_EXAMPLE_LIMIT, 1, 2),
}
# The analogy may use everyday numbers ("요리사 10명"); the other prose may not invent any.
_NUMBER_FIELDS = ("point_ko", "body_ko")


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


def items_block(items: list[Item], past: list[str], target: int | None = None) -> str:
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
    if target is not None:
        lines.append("")
        lines.append(f"<target_rank>{target}</target_rank>")
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


def _allowed_names(items: list[Item]) -> set[str]:
    """trend's allowed names plus the name tokens of the kind / architecture lines
    the explainer also sees."""
    allowed = trend._allowed_names(items)
    for it in items:
        for key, value in _fields(it):
            if key in ("kind_ko", "architecture_ko", "does_ko", "new_ko", "result_ko"):
                for tok in trend._NAME_RE.findall(value):
                    allowed.add(tok.casefold())
                    allowed.update(p.casefold() for p in trend._NAME_PART_RE.split(tok) if p)
    return allowed


def check_field(field: str, text: str, items: list[Item]) -> list[tuple[str, str]]:
    """D-04 rules for one explainer field. Public so the polish pass (03-06) can
    re-run it. Messages name the field and the rule, never the model text."""
    if not text.strip():
        return [("ex_empty", f"{field}가 비어 있음")]
    errs: list[tuple[str, str]] = []
    if field == "topic":
        limit = humanize.EXPLAINER_TOPIC_LIMIT
        if len(text) > limit or analyze.bad_info_prose(text):
            errs.append(("ex_topic", f"topic이 {limit}자 이내의 명사구가 아님"))
    else:
        code, limit, lo, hi = _SHAPE[field]
        n = len([s for s in analyze._SENT_SPLIT.split(text.strip()) if s.strip()])
        if len(text) > limit or not lo <= n <= hi:
            span = f"{lo}문장" if lo == hi else f"{lo}-{hi}문장"
            errs.append((code, f"{field}가 {n}문장, {len(text)}자임 ({span}, {limit}자 이내)"))
        if analyze.not_haeyo(text):
            errs.append(("ex_tone", f"{field}의 문장이 해요체(~요)로 끝나지 않음"))
    if headline._URL_RE.search(text):
        errs.append(("ex_url", f"{field}에 링크가 있음"))
    if any(w in text for w in headline.HYPE_WORDS):
        errs.append(("ex_hype", f"{field}에 과장 표현이 있음"))
    if headline.WRITTEN_BY_RE.search(text):
        errs.append(("ex_authorship", f"{field}가 뉴스레터 작성 방식을 언급함"))
    # Only digit-bearing names (GPT-5, Qwen3) must come from this week's items;
    # plain technique words (Transformer, attention, router) are fine.
    allowed = _allowed_names(items)
    names = [t for t in trend._NAME_RE.findall(text) if any(c.isdigit() for c in t)]
    unknown = [t for t in names if t.casefold() not in allowed]
    if unknown:
        errs.append(
            ("ex_unknown_name", f"{field}에 이번 주 항목에 없는 이름이 {len(unknown)}개 있음")
        )
    if field in _NUMBER_FIELDS:
        known = set(trend._NUMBER_RE.findall(items_block(items, [])))
        rest = trend._NAME_RE.sub(" ", text)
        if any(num not in known for num in trend._NUMBER_RE.findall(rest)):
            errs.append(("ex_number", f"{field}에 입력에 없는 숫자가 있음"))
    return errs


def check(out: ExplainerLLM, items: list[Item], target: int | None = None) -> list[tuple[str, str]]:
    """Field and rank rules for one result (the repeat rule is in write_explainer)."""
    errs: list[tuple[str, str]] = []
    for f in _TEXT_FIELDS:
        errs += check_field(f, getattr(out, f), items)
    errs += check_ranks(out.related_ranks, len(items))
    if target is not None and out.related_ranks[:1] != [target]:
        errs.append(("ex_target", f"related_ranks가 target_rank {target}로 시작하지 않음"))
    return errs


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


def _for_rank(
    items: list[Item], past: list[str], target: int, client, system: str
) -> tuple[ExplainerLLM | None, str]:
    """One valid explainer about item `target` (at most two attempts), or (None, codes).
    The codes are "api_error" when the API failed, so the caller stops trying ranks."""
    block = items_block(items, past, target)
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
            status = getattr(e, "status_code", None)
            log.warning("explainer rank=%d attempt=%d api_error status=%s", target, attempt, status)
            return None, "api_error"
        except ValueError:  # client-side schema validation
            problems = [("schema", "출력이 스키마와 맞지 않음")]
            log.warning("explainer rank=%d attempt=%d reason=schema", target, attempt)
            continue
        if resp.stop_reason in ("refusal", "max_tokens"):
            problems = [
                (f"stop_{resp.stop_reason}", f"응답이 stop_reason={resp.stop_reason}로 끝남")
            ]
            log.info("explainer rank=%d attempt=%d reason=%s", target, attempt, _codes(problems))
            continue
        out = resp.parsed_output
        if not isinstance(out, ExplainerLLM):
            problems = [("no_output", "구조화된 출력이 비어 있음")]
            log.info("explainer rank=%d attempt=%d reason=no_output", target, attempt)
            continue
        out = _normalize(out)
        problems = check(out, items, target)
        if not problems:
            return out, ""
        log.info("explainer rank=%d attempt=%d reason=%s", target, attempt, _codes(problems))
    return None, _codes(problems)


def write_explainer(items: list[Item], past: list[str], client) -> Explainer | None:
    """One explainer for this week: rank #1 first, the next rank when the topic
    repeats a past one, up to MAX_RANK_TRIES ranks."""
    system = explainer_system_prompt()
    first_repeat: ExplainerLLM | None = None
    reason = "no_rank"
    for target in [it.rank for it in items][:MAX_RANK_TRIES]:
        out, reason = _for_rank(items, past, target, client, system)
        if out is None:
            break  # a format or API failure: stop here instead of paying for more ranks
        if not topics.is_repeat(out.topic, past):
            log.info("explainer=claude rank=%d repeat=no", target)
            return _to_explainer(out, items)
        log.info("explainer rank=%d reason=repeat", target)
        if first_repeat is None:
            first_repeat = out
    if first_repeat is not None:
        log.warning("explainer=repeat rank=%d", first_repeat.related_ranks[0])
        return _to_explainer(first_repeat, items)
    if reason == "api_error":
        log.warning("explainer=none reason=api_error")
    else:
        log.info("explainer=none reason=%s", reason)
    return None
