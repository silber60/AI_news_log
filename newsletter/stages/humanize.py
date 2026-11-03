"""Humanizer lint (HUMN-02, D-07): find AI-writing tells in Claude-written text.

`collect_fields` lists every Claude free-text field of an `Issue` by its
`model_dump(mode="json")` leaf path. `lint` returns the banned-pattern codes found
in one text, and `lint_issue` maps each flagged sentence field to its codes. One
hard hit, or two or more weak hits in the same field, flags a field. The polish
call that acts on the result lives in a later plan (03-06); this module makes no
Claude call.

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

from newsletter.schema import Issue
from newsletter.stages import analyze, notes, trend

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
}
_SENTENCE_ONLY_HARD = ("haeyo",)

HARD_CODES: tuple[str, ...] = (*_HARD_PATTERNS, *_SENTENCE_ONLY_HARD)
WEAK_CODES: tuple[str, ...] = ()


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


def lint(text: str, *, kind: Kind = "sentence") -> list[str]:
    """Codes found in text, one entry per match."""
    codes: list[str] = []
    for code, pattern in _HARD_PATTERNS.items():
        codes += [code] * len(pattern.findall(text))
    if kind == "sentence" and analyze.not_haeyo(text):
        codes.append("haeyo")
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
