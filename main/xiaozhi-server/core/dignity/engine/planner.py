from __future__ import annotations

import re
from typing import Any, List

from core.dignity.engine.types import DignityState


def append_asked_question(state: DignityState) -> DignityState:
    reply = (state.get("reply") or "").strip()
    question = extract_question(reply)
    if not question:
        return state
    next_state = dict(state)
    next_state["asked_questions"] = merge_unique_strings(
        next_state.get("asked_questions", []),
        [question],
        max_items=20,
    )
    return next_state


def extract_question(reply: str) -> str:
    match = re.search(r"[^。！？!?]*[？?]", reply or "")
    return match.group(0).strip() if match else ""


def merge_unique_strings(current: List[Any], incoming: Any, max_items: int = 40) -> List[str]:
    merged: List[str] = []
    seen = set()
    for item in list(current or []) + _normalize_string_list(incoming):
        text = str(item).strip()
        if not text or text in seen:
            continue
        merged.append(text)
        seen.add(text)
    return merged[-max_items:]


def _normalize_string_list(value: Any) -> List[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value]
    return []
