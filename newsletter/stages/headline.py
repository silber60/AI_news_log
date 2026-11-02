"""Issue headline (D-12, DLVR-07): the subject and hero line, without `[TEST]`.

One extra Claude call after the analysis writes a short hook and picks an emoji
from a closed list. Code checks the hook, retries once with problem codes and
assembles the line. Any failure (still invalid, refusal, parse error, API error)
switches to `fallback_headline`, which is built by code only from the rank-1
Korean title. The headline never fails the build. Logs carry attempt numbers and
reason codes only, never the hook or any title.
"""

import logging
import re

import anthropic

from newsletter.schema import AiType, HeadlineEmoji, HeadlineLLM, Item
from newsletter.stages import analyze
from newsletter.store import PROMPTS_DIR

log = logging.getLogger(__name__)

AI_TYPE_EMOJI: dict[AiType, HeadlineEmoji] = {
    "LLM": "💬",
    "비전": "👀",
    "멀티모달": "🧠",
    "음성": "🎙️",
    "에이전트": "🤖",
    "이미지/비디오 생성": "🎬",
    "기타": "🔍",
}

NAME_LIMIT = 20
HOOK_LIMIT = 24
INPUT_RANKS = 3

# Emoji and joiners only. Hangul (U+AC00..) sits above U+2600, so a plain
# ">= U+2600" rule would reject every Korean hook.
_EMOJI_RE = re.compile("[☀-➿\U0001f000-\U0001faff️‍]")
_URL_RE = re.compile(r"https?://|www\.", re.IGNORECASE)
_ITEMS_TAG_RE = re.compile(r"</?items>", re.IGNORECASE)
HYPE_WORDS = ("혁신적", "획기적", "게임 체인저", "놀라운", "강력한", "압도적")
CLICKBAIT_WORDS = ("충격", "역대급", "최초", "최고")
AUTHORSHIP_RE = re.compile(r"AI가|자동|claude", re.IGNORECASE)


def fallback_headline(items: list[Item]) -> str:
    top = items[0]
    name = top.title_ko.split(":", 1)[0].strip()[:NAME_LIMIT].strip()
    n = len(items)
    more = " 등" if n > 1 else ""
    return f"{AI_TYPE_EMOJI[top.ai_type]} {name}{more} 이번 주 AI 모델 {n}"


def headline_system_prompt() -> str:
    """headline.md + humanizer_ko.md as one text, sent as one cached block."""
    head = (PROMPTS_DIR / "headline.md").read_text(encoding="utf-8").strip()
    humanizer = (PROMPTS_DIR / "humanizer_ko.md").read_text(encoding="utf-8").strip()
    return head + "\n\n" + humanizer


def _clean(text: str) -> str:
    return analyze._one_line(_ITEMS_TAG_RE.sub("", analyze.strip_urls(text)))


def items_block(items: list[Item]) -> str:
    lines = ["<items>"]
    for it in items[:INPUT_RANKS]:
        lines += [
            f"rank: {it.rank}",
            f"title_ko: {_clean(it.title_ko)}",
            f"ai_type: {it.ai_type}",
            f"summary_ko: {_clean(it.summary_ko)}",
            f"does_ko: {_clean(it.summary_lines_ko[0])}",
            "",
        ]
    lines[-1] = "</items>"
    return "\n".join(lines)


def check_hook(hook: str, input_text: str) -> list[tuple[str, str]]:
    """Code-enforced hook rules. Messages name the rule, never the model text."""
    errs: list[tuple[str, str]] = []
    if not hook.strip():
        errs.append(("hook_empty", "hook_ko가 비어 있음"))
    elif len(hook) > HOOK_LIMIT:
        errs.append(("hook_len", f"hook_ko가 {len(hook)}자로 {HOOK_LIMIT}자를 넘음"))
    if _EMOJI_RE.search(hook):
        errs.append(("hook_emoji", "hook_ko에 이모지가 있음 (이모지는 emoji 필드로만)"))
    if _URL_RE.search(hook):
        errs.append(("hook_url", "hook_ko에 링크가 있음"))
    if "\r" in hook or "\n" in hook:
        errs.append(("hook_newline", "hook_ko에 줄바꿈이 있음"))
    if any(w in hook for w in HYPE_WORDS):
        errs.append(("hook_hype", "hook_ko에 과장 표현이 있음"))
    if any(w in hook and w not in input_text for w in CLICKBAIT_WORDS):
        errs.append(("hook_clickbait", "hook_ko에 입력에 없는 낚시성 표현이 있음"))
    if AUTHORSHIP_RE.search(hook):
        errs.append(("hook_authorship", "hook_ko가 뉴스레터 작성 방식을 언급함"))
    return errs


def write_headline(items: list[Item], client) -> str:
    """Claude hook + code assembly, at most two attempts, then the code fallback."""
    block = items_block(items)
    system = headline_system_prompt()
    n = len(items)
    problems: list[tuple[str, str]] = []
    for attempt in (1, 2):
        try:
            resp = analyze._request(
                client,
                analyze._with_feedback(block, problems),
                system=system,
                output_format=HeadlineLLM,
            )
        except anthropic.APIError as e:
            log.warning(
                "headline=fallback reason=api_error status=%s", getattr(e, "status_code", None)
            )
            return fallback_headline(items)
        except ValueError:  # client-side schema validation
            problems = [("schema", "출력이 스키마와 맞지 않음")]
            log.warning("headline attempt=%d reason=schema", attempt)
            continue
        if resp.stop_reason in ("refusal", "max_tokens"):
            problems = [
                (f"stop_{resp.stop_reason}", f"응답이 stop_reason={resp.stop_reason}로 끝남")
            ]
            continue
        out = resp.parsed_output
        if not isinstance(out, HeadlineLLM):
            problems = [("no_output", "구조화된 출력이 비어 있음")]
            continue
        hook = analyze._one_line(out.hook_ko)
        problems = check_hook(hook, block)
        if not problems:
            log.info("headline=claude attempt=%d", attempt)
            return f"{out.emoji} {hook} 이번 주 AI 모델 {n}"
    reason = "+".join(code for code, _ in problems) or "unknown"
    log.info("headline=fallback reason=%s", reason)
    return fallback_headline(items)
