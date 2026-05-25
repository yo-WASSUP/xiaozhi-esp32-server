from __future__ import annotations

from core.dignity.engine.config import BAD_REPLY_PATTERNS, STAGES
from core.dignity.engine.types import DignityState


def sanitize_reply(state: DignityState, reply: str) -> str:
    text = " ".join((reply or "").split())
    if not text:
        return concrete_fallback_reply(state)
    if any(pattern in text for pattern in BAD_REPLY_PATTERNS):
        return concrete_fallback_reply(state)
    if _question_count(text) > 1:
        return trim_to_single_question(text)
    if len(text) > 110:
        return trim_long_reply(text, state)
    return text


def concrete_fallback_reply(state: DignityState) -> str:
    stage_index = int(state.get("stage_index", 0))
    if 0 <= stage_index < len(STAGES):
        return STAGES[stage_index].default_question
    return "我先记下您刚才说的内容。接下来您想从哪一点继续说？"


def trim_to_single_question(reply: str) -> str:
    indexes = [index for index in [reply.find("？"), reply.find("?")] if index >= 0]
    if not indexes:
        return reply
    return reply[: min(indexes) + 1]


def trim_long_reply(reply: str, state: DignityState) -> str:
    fallback = concrete_fallback_reply(state)
    prefix = reply.split("。")[0].strip()
    if prefix and len(prefix) < 45:
        return f"{prefix}。{fallback}"
    return fallback


def _question_count(text: str) -> int:
    return text.count("？") + text.count("?")
