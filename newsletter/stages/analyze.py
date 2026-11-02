"""Claude analysis: one `messages.parse` call per paper.

Claude fills only `ItemAnalysisLLM`. Code merges it with HF facts (rank, URLs,
affiliation, verdict defaults) into `Item`. The request carries no URL, so
Claude cannot echo or alter links. Plan 03 adds retry-once, fallbacks and
length handling behind the same signatures.
"""

import logging
import os
import re

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


def analyze_one(client, entry: HfEntry) -> ItemAnalysisLLM:
    resp = client.messages.parse(
        model=model_name(),
        max_tokens=16000,
        system=[{"type": "text", "text": system_prompt(), "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": paper_block(entry)}],
        output_format=ItemAnalysisLLM,
    )
    if resp.stop_reason in ("refusal", "max_tokens") or resp.parsed_output is None:
        log.warning("analysis invalid stop_reason=%s", resp.stop_reason)
        raise AnalysisInvalid(f"stop_reason={resp.stop_reason}")
    return resp.parsed_output


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
    items = []
    for i, entry in enumerate(entries):
        items.append(to_item(i + 1, entry, analyze_one(client, entry)))
    log.info("analyzed=%d", len(items))
    return items
