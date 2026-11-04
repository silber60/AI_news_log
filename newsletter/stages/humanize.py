"""Humanizer lint (HUMN-02, D-07): find AI-writing tells in Claude-written text.

`collect_fields` lists every Claude free-text field of an `Issue` by its
`model_dump(mode="json")` leaf path. `lint` returns the banned-pattern codes found
in one text, and `lint_issue` maps each flagged sentence field to its codes. One
hard hit, or two or more weak hits in the same field, flags a field.

`polish_issue` (HUMN-03, D-08, D-13) runs once at the end of the build: it cleans
every collected field, and only when a sentence field is flagged it sends one
polish call with just the flagged fields. Each fix passes per-fix guards, then a
whole-dump diff guard rejects any change outside the accepted paths. At most two
calls; leftovers log a warning and never stop the build.

Never collected: headline_ko (own checks and code fallback), enums, URLs, numbers,
ranks and images. Reason fields equal to `notes.UNKNOWN_REASON` are code text and
are skipped. Name fields (title_ko, kind_ko, architecture_ko, explainer.topic) are
collected with kind "name": cleanup only, never polished. Logs carry counts and
codes only, never field text.
"""

import logging
import re
from dataclasses import dataclass
from typing import Literal

import anthropic
from pydantic import ValidationError

from newsletter.schema import Issue, PolishLLM
from newsletter.stages import analyze, notes, trend
from newsletter.store import PROMPTS_DIR

log = logging.getLogger(__name__)

HIGHLIGHT_LIMIT = 70
EXPLAINER_POINT_LIMIT = 40
EXPLAINER_BODY_LIMIT = 360
EXPLAINER_EXAMPLE_LIMIT = 140
EXPLAINER_TOPIC_LIMIT = 40
REASON_LIMIT = 60

Kind = Literal["sentence", "name"]


@dataclass(frozen=True)
class FieldRef:
    path: str
    kind: Kind
    limit: int | None
    text: str


# ---- hard codes: one hit flags the field (research §1) ----
_HARD_PATTERNS: dict[str, re.Pattern[str]] = {
    "dash": re.compile(r"[—–]|\s--\s"),
    "markdown": re.compile(r"\*\*|__|`|^#{1,6}\s|^\s*[-*]\s", re.MULTILINE),
    "hype": re.compile(
        r"혁신적|획기적|게임\s?체인저|판도를\s?바(?:꾸|꿀|꿔|꿨)|패러다임\s?(?:전환|변화|시프트)"
        r"|새로운\s?지평|놀라운|강력한|압도적|혁명적|차원이\s?다른|역대급"
    ),
    "not_x_but_y": re.compile(
        r"단순(?:히|한)\s?[^.?!]{0,30}?(?:이|가)?\s?아니(?:라|고|에요)"
        r"|(?:뿐|뿐만)\s?(?:아니라|아니고)|에\s?그치지\s?않(?:고|아요)"
    ),
    # "기존 기록을 넘어섰어요" and "100자를 넘어가면" are facts and do not match.
    "beyond": re.compile(r"[을를]\s?넘어(?:서)?(?=[\s,])(?!\s?섰)"),
    "significance": re.compile(
        r"중요성을\s?(?:보여|강조|일깨)|새(?:로운)?\s?기준을\s?(?:세웠|제시)"
        r"|앞으로(?:가|의)?\s?(?:더\s?)?기대|주목할\s?만한|눈여겨\s?볼|꼭\s?알아야\s?할"
        r"|이정표|한\s?획을|시사하는\s?바가|의미가\s?(?:커요|크다|있어요)"
    ),
    "chatbot": re.compile(
        r"도움이\s?되(?:셨|었)으면|궁금한\s?(?:점|게)\s?있으|물론이(?:죠|에요)|좋은\s?질문"
        r"|알려\s?드릴게요|살펴볼까요|알아볼까요|함께\s?보시죠"
    ),
    "authority": re.compile(
        r"전문가들(?:은|이)|업계에서는|많은\s?(?:연구자|전문가)들|평가를\s?받고\s?있"
    ),
    "run_up": re.compile(
        r"^(?:자,|그럼|결론부터\s?말하면|솔직히|사실,|핵심은|중요한\s?(?:건|것은))", re.MULTILINE
    ),
    "double_passive": re.compile(r"되어지|되어져|되어졌|보여지|보여져"),
}
# Sentence fields only. headline_ko is never collected (its emoji is an enum field).
_EMOJI_RE = re.compile("[\U0001f300-\U0001faff\u2600-\u27bf]")

# ---- weak codes: two or more hits in one field flag it (counted per match) ----
_WEAK_PATTERNS: dict[str, re.Pattern[str]] = {
    # High false-positive risk alone: "사람이 아니라 로봇이…" is informative.
    "not_x_plain": re.compile(r"(?:이|가)\s아니라\s"),
    "saying": re.compile(r"본질적으로|근본적으로|결국\s?(?:핵심|중요한)|진정한|그\s?자체"),
    "role_verb": re.compile(r"역할을\s?(?:해요|한다|합니다|하는)|자리매김|로서\s?기능"),
    "rider": re.compile(
        r"(?:을|를)\s?보여\s?(?:줘요|주며|준다|주고)|(?:을|를)\s?시사(?:해요|한다|하며)"
        r"|(?:을|를)\s?강조(?:해요|한다|하며)"
    ),
    "ai_words": re.compile(
        r"다양한|효과적으로|원활(?:한|하게)|극대화|최적화된|심층(?:적)?|면밀(?:히|한)|핵심적인"
    ),
    # Real lists ("역량, 최적화, 평가 방법") hit this, so it is weak only.
    "triad": re.compile(r"(?:[^\s,]{1,12},\s){2}(?:그리고\s)?[^\s,]{1,12}"),
    "hedge_stack": re.compile(r"수도\s?있을\s?(?:것|수)|일\s?수도\s?있|어쩌면|아마도"),
    "subject_repeat": re.compile(
        r"^(?:이\s?논문은|본\s?연구는|이\s?연구는|이\s?모델은)", re.MULTILINE
    ),
}
CLOSER_MAX = 18  # a last sentence this short, with no digit, restates instead of adding
_DIGIT_RE = re.compile(r"\d")

HARD_CODES: tuple[str, ...] = (*_HARD_PATTERNS, "emoji", "haeyo")
WEAK_CODES: tuple[str, ...] = (*_WEAK_PATTERNS, "closer", "same_opening")

_BOLD_RE = re.compile(r"\*\*|__|`")
_LEAD_MARK_RE = re.compile(r"^(?:\s*(?:#{1,6}|[-*])\s+)+")
_QUOTES = str.maketrans({"“": '"', "”": '"', "‘": "'", "’": "'"})
_DASH_RE = re.compile(r"\s*[—–]\s*|\s--\s")


def _field(path: str, kind: Kind, limit: int | None, text: str | None) -> FieldRef | None:
    if text is None:
        return None
    return FieldRef(path=path, kind=kind, limit=limit, text=text)


def collect_fields(issue: Issue) -> list[FieldRef]:
    """Every Claude-written field in a fixed order (research §2 table)."""
    refs: list[FieldRef | None] = []
    for i, it in enumerate(issue.items):
        p = f"items.{i}"
        refs.append(_field(f"{p}.title_ko", "name", None, it.title_ko))
        refs.append(_field(f"{p}.summary_ko", "sentence", analyze.SUMMARY_LIMIT, it.summary_ko))
        for k, line in enumerate(it.summary_lines_ko):
            refs.append(_field(f"{p}.summary_lines_ko.{k}", "sentence", analyze.LINE_LIMIT, line))
        refs.append(_field(f"{p}.use_idea_ko", "sentence", analyze.IDEA_LIMIT, it.use_idea_ko))
        refs.append(
            _field(f"{p}.model_info.kind_ko", "name", analyze.KIND_LIMIT, it.model_info.kind_ko)
        )
        refs.append(
            _field(
                f"{p}.model_info.architecture_ko",
                "name",
                analyze.ARCH_LIMIT,
                it.model_info.architecture_ko,
            )
        )
        refs.append(
            _field(
                f"{p}.claude_gpt.reason_ko",
                "sentence",
                analyze.CLAUDE_GPT_REASON_LIMIT,
                it.claude_gpt.reason_ko,
            )
        )
        for name, reason in (
            ("commercial", it.commercial.reason_ko),
            ("poc", it.poc.reason_ko),
        ):
            if reason != notes.UNKNOWN_REASON:
                refs.append(_field(f"{p}.{name}.reason_ko", "sentence", REASON_LIMIT, reason))
        refs.append(
            _field(f"{p}.skill_gpt.reason_ko", "sentence", REASON_LIMIT, it.skill_gpt.reason_ko)
        )
    refs.append(_field("trend_ko", "sentence", trend.TREND_LIMIT, issue.trend_ko))
    for j, h in enumerate(issue.highlights):
        refs.append(_field(f"highlights.{j}.why_ko", "sentence", HIGHLIGHT_LIMIT, h.why_ko))
        refs.append(_field(f"highlights.{j}.how_ko", "sentence", HIGHLIGHT_LIMIT, h.how_ko))
    ex = issue.explainer
    if ex is not None:
        refs.append(_field("explainer.topic", "name", EXPLAINER_TOPIC_LIMIT, ex.topic))
        refs.append(_field("explainer.point_ko", "sentence", EXPLAINER_POINT_LIMIT, ex.point_ko))
        refs.append(_field("explainer.body_ko", "sentence", EXPLAINER_BODY_LIMIT, ex.body_ko))
        refs.append(
            _field("explainer.example_ko", "sentence", EXPLAINER_EXAMPLE_LIMIT, ex.example_ko)
        )
    return [r for r in refs if r is not None and r.text.strip()]


def _sentences(text: str) -> list[str]:
    return [t for t in (x.strip() for x in analyze._SENT_SPLIT.split(text.strip())) if t]


def lint(text: str, *, kind: Kind = "sentence") -> list[str]:
    """Codes found in text, one entry per match (research §1).

    `emoji` and `haeyo` apply to sentence fields only; names keep their own form.
    """
    codes: list[str] = []
    for patterns in (_HARD_PATTERNS, _WEAK_PATTERNS):
        for code, pattern in patterns.items():
            codes += [code] * len(pattern.findall(text))
    if kind == "sentence":
        codes += ["emoji"] * len(_EMOJI_RE.findall(text))
        if analyze.not_haeyo(text):
            codes.append("haeyo")
    sents = _sentences(text)
    if len(sents) >= 3:
        last = sents[-1]
        if len(last) <= CLOSER_MAX and not _DIGIT_RE.search(last):
            codes.append("closer")
        firsts = [s.split()[0] for s in sents]
        if max(firsts.count(f) for f in firsts) >= 3:
            codes.append("same_opening")
    return codes


def needs_polish(codes: list[str]) -> bool:
    """One hard hit, or two or more weak hits."""
    if any(c in HARD_CODES for c in codes):
        return True
    return sum(1 for c in codes if c in WEAK_CODES) >= 2


def lint_issue(issue: Issue) -> dict[str, list[str]]:
    """Flagged sentence-field paths mapped to their sorted unique codes."""
    fields = [f for f in collect_fields(issue) if f.kind == "sentence"]
    flagged: dict[str, list[str]] = {}
    for f in fields:
        codes = lint(f.text, kind=f.kind)
        if needs_polish(codes):
            flagged[f.path] = sorted(set(codes))
    all_codes = sorted({c for codes in flagged.values() for c in codes})
    log.info(
        "humanizer=lint fields=%d flagged=%d codes=%s",
        len(fields),
        len(flagged),
        ",".join(all_codes) or "-",
    )
    return flagged


def cleanup(text: str) -> str:
    """Research cleanup steps 1-3: drop bold/markdown markers, straighten curly
    quotes, collapse whitespace. Idempotent. Length caps stay with each stage."""
    text = _BOLD_RE.sub("", text).translate(_QUOTES)
    text = analyze._one_line(text)
    return _LEAD_MARK_RE.sub("", text).strip()


def dash_fallback(text: str) -> str:
    """Research cleanup step 4 (after polish only): connector dashes become ", ".
    English hyphens ("Vision-Language-Action", "GPT-5") are left alone."""
    return _DASH_RE.sub(", ", text)


# ---- polish pass (HUMN-03, D-08, D-13; research §2) ----

MAX_POLISH_ATTEMPTS = 2


def polish_system_prompt() -> str:
    """polish.md + humanizer_ko.md as one text, sent as one cached block."""
    head = (PROMPTS_DIR / "polish.md").read_text(encoding="utf-8").strip()
    humanizer = (PROMPTS_DIR / "humanizer_ko.md").read_text(encoding="utf-8").strip()
    return head + "\n\n" + humanizer


def _leaves(d, prefix: str = ""):
    if isinstance(d, dict):
        for k, v in d.items():
            yield from _leaves(v, f"{prefix}{k}.")
    elif isinstance(d, list):
        for i, v in enumerate(d):
            yield from _leaves(v, f"{prefix}{i}.")
    else:
        yield prefix.rstrip("."), d


def unchanged_outside(before: dict, after: dict, allowed: set[str]) -> bool:
    """True when every leaf outside `allowed` is equal and the key sets match."""
    a, b = dict(_leaves(before)), dict(_leaves(after))
    return a.keys() == b.keys() and all(a[k] == b[k] for k in a if k not in allowed)


def _set_path(data: dict, path: str, text: str) -> None:
    keys = path.split(".")
    node = data
    for k in keys[:-1]:
        node = node[int(k)] if isinstance(node, list) else node[k]
    last = keys[-1]
    if isinstance(node, list):
        node[int(last)] = text
    else:
        node[last] = text


def set_texts(issue: Issue, texts: dict[str, str]) -> Issue:
    """A copy of issue with each path set to its text, rebuilt through
    Issue.model_validate so the contract checks run again."""
    data = issue.model_dump(mode="json")
    for path, text in texts.items():
        _set_path(data, path, text)
    return Issue.model_validate(data)


def _hard(codes: list[str]) -> int:
    return sum(1 for c in codes if c in HARD_CODES)


def _weak(codes: list[str]) -> int:
    return sum(1 for c in codes if c in WEAK_CODES)


def _clean_field(text: str) -> str:
    # Data fence: a text can never close the <fields> block or carry a link.
    return analyze._one_line(_FIELDS_TAG_RE.sub("", text))


_FIELDS_TAG_RE = re.compile(r"</?fields>", re.IGNORECASE)


def fields_block(refs: list[FieldRef], flagged: dict[str, list[str]]) -> str:
    lines = ["<fields>"]
    for f in refs:
        lines += [
            f"id: {f.path}",
            "kind: 문장",
            f"limit: {f.limit}",
            f"problems: {', '.join(flagged[f.path])}",
            f"text: {_clean_field(f.text)}",
            "",
        ]
    lines[-1] = "</fields>"
    return "\n".join(lines)


def fix_errors(ref: FieldRef, text: str, issue: Issue) -> list[tuple[str, str]]:
    """Guards for one rewritten field. Messages name the id and the rule, never text."""
    where = ref.path
    if not text.strip():
        return [("fix_empty", f"{where}의 text가 비어 있음")]
    errs: list[tuple[str, str]] = []
    if ref.limit is not None and len(text) > ref.limit:
        errs.append(("fix_len", f"{where}가 {len(text)}자로 {ref.limit}자를 넘음"))
    if analyze.not_haeyo(text):
        errs.append(("fix_tone", f"{where}의 문장이 해요체(~요)로 끝나지 않음"))
    before, after = lint(ref.text), lint(text)
    if _hard(after) >= _hard(before):
        errs.append(("fix_lint", f"{where}에 고칠 문제가 그대로 남음"))
    return errs


def _codes(problems: list[tuple[str, str]]) -> str:
    return "+".join(sorted({code for code, _ in problems})) or "unknown"


def _request_fixes(
    client, refs: list[FieldRef], flagged: dict[str, list[str]], issue: Issue
) -> dict[str, str]:
    """One or two polish calls. Returns accepted path -> text; never raises."""
    by_path = {f.path: f for f in refs}
    pending = [f.path for f in refs]
    accepted: dict[str, str] = {}
    problems: list[tuple[str, str]] = []
    system = polish_system_prompt()
    for attempt in range(1, MAX_POLISH_ATTEMPTS + 1):
        block = fields_block([by_path[p] for p in pending], flagged)
        try:
            resp = analyze._request(
                client,
                analyze._with_feedback(block, problems),
                system=system,
                output_format=PolishLLM,
            )
        except anthropic.APIError as e:
            log.warning("polish=none reason=api_error status=%s", getattr(e, "status_code", None))
            break
        except ValueError:  # client-side schema validation
            problems = [("schema", "출력이 스키마와 맞지 않음")]
            log.warning("polish attempt=%d reason=schema", attempt)
            continue
        if resp.stop_reason in ("refusal", "max_tokens"):
            problems = [
                (f"stop_{resp.stop_reason}", f"응답이 stop_reason={resp.stop_reason}로 끝남")
            ]
            log.warning("polish attempt=%d reason=stop_%s", attempt, resp.stop_reason)
            continue
        out = resp.parsed_output
        if not isinstance(out, PolishLLM):
            problems = [("no_output", "구조화된 출력이 비어 있음")]
            continue
        counts: dict[str, int] = {}
        for fix in out.fixes:
            counts[fix.id] = counts.get(fix.id, 0) + 1
        problems = []
        failed: list[str] = []
        for path in pending:
            n = counts.get(path, 0)
            if n != 1:
                code = "fix_missing" if n == 0 else "fix_repeat"
                problems.append((code, f"{path}의 fix가 {n}개임 (1개여야 함)"))
                failed.append(path)
                continue
            text = cleanup(next(f.text for f in out.fixes if f.id == path))
            errs = fix_errors(by_path[path], text, issue)
            if errs:
                problems += errs
                failed.append(path)
            else:
                accepted[path] = text
        extra = len(set(counts) - set(pending))
        log.info(
            "polish attempt=%d requested=%d accepted=%d ignored=%d reason=%s",
            attempt,
            len(pending),
            len(pending) - len(failed),
            extra,
            _codes(problems) if problems else "-",
        )
        pending = failed
        if not pending:
            break
    return accepted


def polish_issue(issue: Issue, client) -> Issue:
    """Clean every Claude field, lint the sentence fields, send only the flagged ones
    to one guarded polish call (two at most), apply the fixes that pass, and apply
    the dash fallback. Never raises; any doubt keeps the cleaned originals."""
    original = issue.model_dump(mode="json")
    refs = collect_fields(issue)
    collected = {f.path for f in refs}
    try:
        cleaned = set_texts(issue, {f.path: cleanup(f.text) for f in refs})
    except ValidationError:
        log.warning("cleanup=skipped reason=validation")
        cleaned = issue

    flagged = lint_issue(cleaned)
    polished = cleaned
    if flagged:
        sentence = [f for f in collect_fields(cleaned) if f.path in flagged]
        accepted = _request_fixes(client, sentence, flagged, cleaned)
        if accepted:
            try:
                candidate = set_texts(cleaned, accepted)
            except ValidationError:
                candidate = None
            before = cleaned.model_dump(mode="json")
            if candidate is not None and unchanged_outside(
                before, candidate.model_dump(mode="json"), set(accepted)
            ):
                polished = candidate
                log.info("polish=applied fields=%d", len(accepted))
            else:
                log.warning("polish=discarded reason=diff fields=%d", len(accepted))
        left = lint_issue(polished) if accepted else flagged
        if left:
            codes = sorted({c for cs in left.values() for c in cs})
            log.warning("humanizer=unfixed fields=%d codes=%s", len(left), ",".join(codes))

    dashed = {
        f.path: dash_fallback(f.text)
        for f in collect_fields(polished)
        if dash_fallback(f.text) != f.text
    }
    if dashed:
        try:
            polished = set_texts(polished, dashed)
            log.info("cleanup=dash fields=%d", len(dashed))
        except ValidationError:
            log.warning("cleanup=dash_skipped reason=validation")
    if not unchanged_outside(original, polished.model_dump(mode="json"), collected):
        log.warning("polish=discarded reason=final_diff")
        return issue
    return polished
