"""Claude analysis: one `messages.parse` call per paper.

Claude fills only `ItemAnalysisLLM`. Code merges it with HF facts (rank, URLs,
affiliation, verdict defaults) into `Item`. The request carries no URL, so
Claude cannot echo or alter links. Each paper gets at most two attempts
(retry once with feedback); server-side fallbacks are requested and dropped per
client if the API or SDK rejects them.
"""

import logging
import os
import re
import weakref

import anthropic
from pydantic import ValidationError

from newsletter.errors import AnalysisInvalid
from newsletter.schema import HfEntry, Item, ItemAnalysisLLM
from newsletter.store import PROMPTS_DIR

log = logging.getLogger(__name__)

DEFAULT_MODEL = "claude-sonnet-5-5"
_URL_RE = re.compile(r"https?://\S+")
_TAG_RE = re.compile(r"</?paper>", re.IGNORECASE)


def model_name() -> str:
    return os.environ.get("CLAUDE_MODEL", DEFAULT_MODEL)


def make_client() -> anthropic.Anthropic:
    return anthropic.Anthropic(max_retries=4, timeout=300)


def strip_urls(text: str | None) -> str:
    """Remove every http(s) URL and any <paper> tag from untrusted paper text."""
    if not text:
        return ""
    text = _TAG_RE.sub("", _URL_RE.sub("", text))
    return re.sub(r"[ \t]{2,}", " ", text).strip()


def system_prompt() -> str:
    return (PROMPTS_DIR / "analyze_paper.md").read_text(encoding="utf-8")


def paper_block(entry: HfEntry) -> str:
    p = entry.paper
    keywords = [k for k in (strip_urls(k) for k in (p.ai_keywords or [])) if k]
    affiliation = strip_urls(entry.organization.fullname if entry.organization else None)
    lines = [
        "<paper>",
        f"title: {strip_urls(p.title)}",
        f"abstract: {strip_urls(p.summary)}",
        f"hf_ai_summary: {strip_urls(p.ai_summary)}",
        f"hf_ai_keywords: {', '.join(keywords)}",
        f"affiliation: {affiliation or '없음'}",
        f"has_github: {_is_https(p.githubRepo)}",
        f"has_project_page: {_is_https(p.projectPage)}",
        "</paper>",
    ]
    return "\n".join(lines)


SUMMARY_LIMIT = 80  # ANLY-03, measured in Python len() characters
_WS_RE = re.compile(r"[\r\n\t]+")
_BOUNDARY_CHARS = " ,."


def _one_line(text: str) -> str:
    """CR/LF/tab -> single space. These fields feed the Subject header and plain text."""
    return re.sub(r" {2,}", " ", _WS_RE.sub(" ", text)).strip()


def normalize(a: ItemAnalysisLLM) -> ItemAnalysisLLM:
    return a.model_copy(
        update={
            "title_ko": _one_line(a.title_ko),
            "summary_ko": _one_line(a.summary_ko),
            "use_ideas_ko": [_one_line(i) for i in a.use_ideas_ko],
        }
    )


def check(a: ItemAnalysisLLM) -> list[tuple[str, str]]:
    """Code-enforced ANLY-03 / D-07 limits. Messages carry counts, never model text."""
    errs: list[tuple[str, str]] = []
    if not a.title_ko.strip():
        errs.append(("title_empty", "title_ko가 비어 있음"))
    if len(a.summary_ko) > SUMMARY_LIMIT:
        errs.append(
            ("summary_len", f"summary_ko가 {len(a.summary_ko)}자로 {SUMMARY_LIMIT}자를 넘음")
        )
    if len(a.use_ideas_ko) > 2:
        errs.append(("ideas_count", f"use_ideas_ko가 {len(a.use_ideas_ko)}개로 2개를 넘음"))
    if any(not i.strip() for i in a.use_ideas_ko):
        errs.append(("idea_empty", "use_ideas_ko에 빈 항목이 있음"))
    return errs


def trim_summary(s: str, limit: int = SUMMARY_LIMIT) -> str:
    """D-19: cut at the last phrase boundary (space, comma, period, 다.) within
    limit-1 characters and append an ellipsis. Hard cut if no usable boundary."""
    if len(s) <= limit:
        return s
    head = s[: limit - 1]
    cut = max(head.rfind(c) for c in _BOUNDARY_CHARS)
    if cut >= limit // 2:
        # keep a closing comma or period with the text, drop a space
        head = head[: cut + 1] if head[cut] in ",." else head[:cut]
    head = head.rstrip(" ,")
    return head + "…"


FALLBACK_BETA = "server-side-fallback-2026-07-01"

# Clients whose API or SDK rejected server-side fallbacks (Assumption A2). Keyed by
# client object so the downgrade never leaks between clients or tests.
_FALLBACKS_UNSUPPORTED: weakref.WeakKeyDictionary = weakref.WeakKeyDictionary()

_RETRY_NOTE = "위 문제를 고쳐 다시 출력하세요."


def _fallbacks_supported(client) -> bool:
    try:
        return not _FALLBACKS_UNSUPPORTED.get(client, False)
    except TypeError:  # client type cannot be weak-referenced
        return True


def _mark_fallbacks_unsupported(client) -> None:
    try:
        _FALLBACKS_UNSUPPORTED[client] = True
    except TypeError:
        pass
    log.warning("fallbacks=unsupported")


def _request(client, content: str):
    kwargs = {
        "model": model_name(),
        "max_tokens": 16000,
        "system": [
            {"type": "text", "text": system_prompt(), "cache_control": {"type": "ephemeral"}}
        ],
        "messages": [{"role": "user", "content": content}],
        "output_format": ItemAnalysisLLM,
    }
    if _fallbacks_supported(client):
        try:
            return client.beta.messages.parse(**kwargs, betas=[FALLBACK_BETA], fallbacks="default")
        except anthropic.BadRequestError, TypeError:
            # The server (400) or the SDK (unknown keyword) rejects the combination.
            # Downgrade this client for good and re-issue the same attempt.
            _mark_fallbacks_unsupported(client)
    return client.messages.parse(**kwargs)


def _log_call(rank: int, attempt: int, resp) -> None:
    usage = getattr(resp, "usage", None)
    details = getattr(resp, "stop_details", None)
    log.info(
        "rank=%d attempt=%d stop_reason=%s category=%s input_tokens=%s output_tokens=%s "
        "cache_read_input_tokens=%s",
        rank,
        attempt,
        getattr(resp, "stop_reason", None),
        getattr(details, "category", None),
        getattr(usage, "input_tokens", None),
        getattr(usage, "output_tokens", None),
        getattr(usage, "cache_read_input_tokens", None),
    )


def _with_feedback(block: str, problems: list[tuple[str, str]]) -> str:
    if not problems:
        return block
    lines = "\n".join(f"- {msg}" for _, msg in problems)
    return f"{block}\n\n<previous_output_problems>\n{lines}\n</previous_output_problems>\n{_RETRY_NOTE}"


def analyze_one(client, entry: HfEntry, *, rank: int = 0) -> ItemAnalysisLLM:
    """One paper -> validated analysis. At most two attempts (ANLY-06, D-15).

    Feedback for the retry names only the problem (stop reason, error counts), never
    model text. Logs carry rank, attempt, stop_reason, category and token counts only.
    """
    block = paper_block(entry)
    problems: list[tuple[str, str]] = []
    for attempt in (1, 2):
        last: ItemAnalysisLLM | None = None
        try:
            resp = _request(client, _with_feedback(block, problems))
        except ValueError as e:  # pydantic.ValidationError from client-side validation (A4)
            n = e.error_count() if isinstance(e, ValidationError) else 1
            problems = [("schema", f"출력이 스키마와 맞지 않음 (오류 {n}건)")]
            log.warning("rank=%d attempt=%d schema_errors=%d", rank, attempt, n)
            continue
        _log_call(rank, attempt, resp)
        if resp.stop_reason in ("refusal", "max_tokens"):
            problems = [
                (f"stop_{resp.stop_reason}", f"응답이 stop_reason={resp.stop_reason}로 끝남")
            ]
            continue
        if resp.parsed_output is None:
            problems = [("no_output", "구조화된 출력이 비어 있음")]
            continue
        last = normalize(resp.parsed_output)
        problems = check(last)
        if not problems:
            return last
    if last is not None and [code for code, _ in problems] == ["summary_len"]:
        # D-19: a pure length overrun after the retry is repaired, not fatal.
        log.info("trimmed=summary rank=%d", rank)
        return last.model_copy(update={"summary_ko": trim_summary(last.summary_ko)})
    reason = "+".join(code for code, _ in problems) or "unknown"
    raise AnalysisInvalid(f"rank={rank} reason={reason}")


def _is_https(url: str | None) -> bool:
    return bool(url) and url.startswith("https://")


def to_item(rank: int, entry: HfEntry, analysis: ItemAnalysisLLM) -> Item:
    p = entry.paper
    try:
        return Item(
            rank=rank,
            paper_id=p.id,
            title_en=p.title,
            upvotes=p.upvotes,
            num_comments=entry.numComments,
            submitted_on_daily_at=p.submittedOnDailyAt.date(),
            affiliation=(entry.organization.fullname if entry.organization else None) or None,
            hf_url=f"https://huggingface.co/papers/{p.id}",
            arxiv_url=f"https://arxiv.org/abs/{p.id}",
            github_url=p.githubRepo if _is_https(p.githubRepo) else None,
            project_url=p.projectPage if _is_https(p.projectPage) else None,
            title_ko=analysis.title_ko,
            ai_type=analysis.ai_type,
            summary_ko=analysis.summary_ko,
            use_ideas_ko=analysis.use_ideas_ko,
        )
    except ValidationError as e:
        raise AnalysisInvalid(f"item {rank}: {e.error_count()} validation errors") from e


def analyze_items(entries: list[HfEntry], client) -> list[Item]:
    """Analyze in rank order, one call at a time so the cached system prompt stays
    warm (5-minute TTL). The first paper still invalid after its retry stops the
    run before any issue.json exists (D-15)."""
    items = []
    for i, entry in enumerate(entries):
        rank = i + 1
        items.append(to_item(rank, entry, analyze_one(client, entry, rank=rank)))
    log.info("analyzed=%d", len(items))
    return items
