"""Verdict reasons (ANLY-04, D-14): one sentence per 상업적 사용 / PoC verdict.

Code decides every verdict. This stage only writes `CommercialUse.reason_ko` and
`PocReadiness.reason_ko`. A verdict at 확인 필요 gets the fixed code reason
`UNKNOWN_REASON` without a Claude call. The other verdicts go to Claude in one
batched call whose input holds code facts only (verdicts, license ids, yes/no
flags; no URL). Code checks each reason: length, 해요체, no URL or hype word, every
license word grounded in that item's input, and no contradiction of the verdict.
The call retries once with problem codes; after that, passing reasons are kept and
failing ones are stored as None. The stage never raises and never changes a
verdict. Logs carry attempt numbers, ranks and reason codes only.
"""

import logging
import re

import anthropic

from newsletter.schema import UNKNOWN, Item, LicenseInfo, VerdictNoteLLM, VerdictNotesLLM
from newsletter.stages import analyze, headline
from newsletter.store import PROMPTS_DIR

log = logging.getLogger(__name__)

UNKNOWN_REASON = "공개된 근거를 찾지 못해 확인이 필요해요."
NOTE_LIMIT = 60

# License words a reason may name only when that item's input names them too.
GROUNDING_TOKENS = (
    "MIT", "Apache", "BSD", "GPL", "LGPL", "AGPL", "MPL", "CC", "OpenRAIL", "RAIL",
    "Llama", "Gemma", "Qwen", "DeepSeek", "비상업", "연구용",
)  # fmt: skip


def _token_re(tok: str) -> re.Pattern:
    if tok.isascii():
        # "GPL" must not match inside "LGPL", nor "RAIL" inside "OpenRAIL".
        return re.compile(rf"(?<![A-Za-z]){re.escape(tok)}(?![a-z])", re.IGNORECASE)
    return re.compile(re.escape(tok))


_TOKEN_RES = {tok: _token_re(tok) for tok in GROUNDING_TOKENS}

# Phrases that contradict a code verdict (research §5 polarity table).
COMMERCIAL_FORBIDDEN = {
    "가능": ("불가", "쓸 수 없", "안 돼요", "금지"),
    "불가": ("쓸 수 있어요", "가능해요", "제한 없이"),
    "조건부": ("제한 없이", "자유롭게"),
    "확인 필요": ("제한 없이", "자유롭게"),
}
POC_FORBIDDEN = {
    "논문만": ("바로 써", "데모"),
    "코드만": ("데모", "바로 써"),
}


def notes_system_prompt() -> str:
    """verdict_notes.md + humanizer_ko.md as one text, sent as one cached block."""
    head = (PROMPTS_DIR / "verdict_notes.md").read_text(encoding="utf-8").strip()
    humanizer = (PROMPTS_DIR / "humanizer_ko.md").read_text(encoding="utf-8").strip()
    return head + "\n\n" + humanizer


def _license(info: LicenseInfo | None) -> str:
    if info is None:
        return "없음"
    parts = [headline._clean(p) for p in (info.spdx_id, info.name) if p]
    parts = list(dict.fromkeys(p for p in parts if p))
    return " / ".join(parts) or "없음"


def _yn(flag: bool | None) -> str:
    return "yes" if flag else "no"


def item_lines(it: Item) -> list[str]:
    """One item's code facts for the `<items>` block (no URL, no Claude text)."""
    return [
        f"rank: {it.rank}",
        f"commercial: {it.commercial.verdict}",
        f"code_license: {_license(it.commercial.code_license)}",
        f"weights_license: {_license(it.commercial.weights_license)}",
        f"poc: {it.poc.verdict}",
        f"has_weights: {_yn(it.poc.has_weights)}",
        f"has_code: {_yn(it.poc.has_code)}",
        f"has_demo: {_yn(it.poc.has_demo)}",
    ]


def items_block(items: list[Item]) -> str:
    lines = ["<items>"]
    for it in items:
        lines += [*item_lines(it), ""]
    lines[-1] = "</items>"
    return "\n".join(lines)


def _needs_claude(it: Item) -> bool:
    return it.commercial.verdict != UNKNOWN or it.poc.verdict != UNKNOWN


def _field_errors(field: str, text: str, forbidden: tuple[str, ...], grounding: str, rank: int):
    errs: list[tuple[str, str]] = []
    where = f"rank {rank} {field}"
    if not text.strip():
        return [("note_empty", f"{where}가 비어 있음")]
    if len(text) > NOTE_LIMIT:
        errs.append(("note_len", f"{where}가 {len(text)}자로 {NOTE_LIMIT}자를 넘음"))
    if analyze.not_haeyo(text):
        errs.append(("note_tone", f"{where}가 해요체(~요)로 끝나지 않음"))
    if headline._URL_RE.search(text):
        errs.append(("note_url", f"{where}에 링크가 있음"))
    if any(w in text for w in headline.HYPE_WORDS):
        errs.append(("note_hype", f"{where}에 과장 표현이 있음"))
    if any(r.search(text) and not r.search(grounding) for r in _TOKEN_RES.values()):
        errs.append(("note_ungrounded", f"{where}가 입력에 없는 라이선스를 언급함"))
    if any(p in text for p in forbidden):
        errs.append(("note_polarity", f"{where}가 코드 판정과 맞지 않는 표현을 씀"))
    return errs


def _commercial_errors(note: VerdictNoteLLM, it: Item) -> list[tuple[str, str]]:
    if it.commercial.verdict == UNKNOWN:
        return []
    return _field_errors(
        "commercial_reason_ko",
        analyze._one_line(note.commercial_reason_ko),
        COMMERCIAL_FORBIDDEN.get(it.commercial.verdict, ()),
        "\n".join(item_lines(it)),
        it.rank,
    )


def _poc_errors(note: VerdictNoteLLM, it: Item) -> list[tuple[str, str]]:
    if it.poc.verdict == UNKNOWN:
        return []
    return _field_errors(
        "poc_reason_ko",
        analyze._one_line(note.poc_reason_ko),
        POC_FORBIDDEN.get(it.poc.verdict, ()),
        "\n".join(item_lines(it)),
        it.rank,
    )


def check_note(note: VerdictNoteLLM, item: Item) -> list[tuple[str, str]]:
    """Code-enforced reason rules for one item. Only fields whose verdict is known
    are checked. Messages name rank, field and rule, never the model text."""
    return _commercial_errors(note, item) + _poc_errors(note, item)


def _rank_errors(out: VerdictNotesLLM, targets: list[Item]) -> list[tuple[str, str]]:
    got = [n.rank for n in out.notes]
    want = sorted(it.rank for it in targets)
    if sorted(got) != want:
        return [("note_ranks", f"notes의 rank가 입력 rank {want}와 다르거나 중복됨")]
    return []


def _apply(items: list[Item], targets: list[Item], out: VerdictNotesLLM | None) -> list[Item]:
    """Write reason_ko only. Known verdicts take a passing Claude reason or None;
    unknown verdicts keep UNKNOWN_REASON."""
    by_rank: dict[int, VerdictNoteLLM] = {}
    if out is not None:
        seen: dict[int, int] = {}
        for n in out.notes:
            seen[n.rank] = seen.get(n.rank, 0) + 1
        by_rank = {n.rank: n for n in out.notes if seen[n.rank] == 1}
    target_ranks = {it.rank for it in targets}
    kept = dropped = 0
    result = []
    for it in items:
        commercial = UNKNOWN_REASON if it.commercial.verdict == UNKNOWN else None
        poc = UNKNOWN_REASON if it.poc.verdict == UNKNOWN else None
        note = by_rank.get(it.rank) if it.rank in target_ranks else None
        if note is not None:
            if commercial is None and not _commercial_errors(note, it):
                commercial = analyze._one_line(note.commercial_reason_ko)
            if poc is None and not _poc_errors(note, it):
                poc = analyze._one_line(note.poc_reason_ko)
        for verdict, reason in ((it.commercial.verdict, commercial), (it.poc.verdict, poc)):
            if verdict != UNKNOWN:
                kept, dropped = (kept + 1, dropped) if reason else (kept, dropped + 1)
        result.append(
            it.model_copy(
                update={
                    "commercial": it.commercial.model_copy(update={"reason_ko": commercial}),
                    "poc": it.poc.model_copy(update={"reason_ko": poc}),
                }
            )
        )
    log.info("notes kept=%d dropped=%d", kept, dropped)
    return result


def write_notes(items: list[Item], client) -> list[Item]:
    """Fixed reasons for 확인 필요, one batched Claude call for the rest, at most
    two attempts. Returns copies of the items with reason_ko filled; verdicts are
    never changed and the call never raises."""
    targets = [it for it in items if _needs_claude(it)]
    if not targets:
        log.info("notes=code_only")
        return _apply(items, [], None)
    block = items_block(targets)
    system = notes_system_prompt()
    problems: list[tuple[str, str]] = []
    last: VerdictNotesLLM | None = None
    for attempt in (1, 2):
        try:
            resp = analyze._request(
                client,
                analyze._with_feedback(block, problems),
                system=system,
                output_format=VerdictNotesLLM,
            )
        except anthropic.APIError as e:
            log.warning("notes=none reason=api_error status=%s", getattr(e, "status_code", None))
            return _apply(items, targets, None)
        except ValueError:  # client-side schema validation
            problems = [("schema", "출력이 스키마와 맞지 않음")]
            log.warning("notes attempt=%d reason=schema", attempt)
            continue
        if resp.stop_reason in ("refusal", "max_tokens"):
            problems = [
                (f"stop_{resp.stop_reason}", f"응답이 stop_reason={resp.stop_reason}로 끝남")
            ]
            log.warning("notes attempt=%d reason=stop_%s", attempt, resp.stop_reason)
            continue
        out = resp.parsed_output
        if not isinstance(out, VerdictNotesLLM):
            problems = [("no_output", "구조화된 출력이 비어 있음")]
            continue
        last = out
        by_rank = {it.rank: it for it in targets}
        problems = _rank_errors(out, targets)
        for note in out.notes:
            if note.rank in by_rank:
                problems += check_note(note, by_rank[note.rank])
        if not problems:
            log.info("notes=claude attempt=%d", attempt)
            break
        log.info("notes attempt=%d reason=%s", attempt, "+".join(sorted({c for c, _ in problems})))
    return _apply(items, targets, last)
