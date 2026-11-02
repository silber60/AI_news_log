"""Issue headline (D-12, DLVR-07): the subject and hero line, without `[TEST]`.

`fallback_headline` is built by code only from the rank-1 Korean title (already
one-line normalized by analyze). Plan 03 adds the Claude hook call here and
keeps this as the fallback.
"""

from newsletter.schema import AiType, HeadlineEmoji, Item

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


def fallback_headline(items: list[Item]) -> str:
    top = items[0]
    name = top.title_ko.split(":", 1)[0].strip()[:NAME_LIMIT].strip()
    n = len(items)
    more = " 등" if n > 1 else ""
    return f"{AI_TYPE_EMOJI[top.ai_type]} {name}{more} 이번 주 AI 모델 {n}"
