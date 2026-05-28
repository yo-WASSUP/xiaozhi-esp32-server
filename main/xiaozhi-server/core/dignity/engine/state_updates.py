from __future__ import annotations

import re
from copy import deepcopy
from typing import Any, Dict, List


DEFAULT_DIGNITY_MEMORY: Dict[str, List[Any]] = {
    "life_story_materials": [],
    "important_relationships": [],
    "values_and_strengths": [],
    "messages_to_family": [],
}

DEFAULT_EMOTION_STATE: Dict[str, Any] = {
    "mood": "calm",
    "engagement": "medium",
}


def initial_dignity_memory() -> Dict[str, List[Any]]:
    return deepcopy(DEFAULT_DIGNITY_MEMORY)


def initial_emotion_state() -> Dict[str, Any]:
    return deepcopy(DEFAULT_EMOTION_STATE)


def normalize_emotion_state(value: Any) -> Dict[str, Any]:
    if not isinstance(value, dict):
        return initial_emotion_state()
    mood = str(value.get("mood") or "calm").strip()
    engagement = str(value.get("engagement") or "medium").strip()
    if mood not in {"calm", "happy", "sad", "anxious", "angry", "tired", "nostalgic", "grateful", "lonely"}:
        mood = "calm"
    if engagement not in {"high", "medium", "low"}:
        engagement = "medium"
    return {"mood": mood, "engagement": engagement}


def merge_dignity_memory(
    current: Dict[str, List[Any]],
    update: Dict[str, List[Any]],
) -> Dict[str, List[Any]]:
    merged = initial_dignity_memory()
    merged.update(merge_list_state(current or {}, update or {}))
    return {
        key: list(value)[-80:] if isinstance(value, list) else []
        for key, value in merged.items()
        if key in DEFAULT_DIGNITY_MEMORY
    }


def merge_list_state(current: Dict[str, List[Any]], update: Dict[str, List[Any]]) -> Dict[str, List[Any]]:
    merged: Dict[str, List[Any]] = {}
    for key, items in (current or {}).items():
        if isinstance(items, list):
            merged[str(key)] = _dedupe_memory_items(items)

    for key, items in (update or {}).items():
        if not isinstance(items, list):
            continue
        bucket = merged.setdefault(str(key), [])
        for item in items:
            _append_memory_item(bucket, item)
    return merged


def _dedupe_memory_items(items: List[Any]) -> List[Any]:
    bucket: List[Any] = []
    for item in items:
        _append_memory_item(bucket, item)
    return bucket


def _append_memory_item(bucket: List[Any], item: Any) -> None:
    item_text = _memory_item_text(item)
    if not item_text:
        return
    item_key = _memory_item_key(item_text)
    for index, existing in enumerate(bucket):
        existing_text = _memory_item_text(existing)
        existing_key = _memory_item_key(existing_text)
        if item_key == existing_key:
            bucket[index] = _prefer_memory_item(existing, item)
            return
        if _is_near_duplicate(existing_key, item_key):
            bucket[index] = _prefer_memory_item(existing, item)
            return
    bucket.append(item)


def _prefer_memory_item(existing: Any, incoming: Any) -> Any:
    existing_text = _memory_item_text(existing)
    incoming_text = _memory_item_text(incoming)
    if len(incoming_text) > len(existing_text):
        return incoming
    return existing


def _memory_item_text(item: Any) -> str:
    if isinstance(item, str):
        return item.strip()
    if isinstance(item, dict):
        return " ".join(
            str(value).strip()
            for _, value in sorted(item.items())
            if value is not None and str(value).strip()
        )
    return str(item or "").strip()


def _memory_item_key(text: str) -> str:
    return re.sub(r"[\s，。；：、（）()《》“”\"'‘’！？!?,.：:;；-]+", "", text)


def _is_near_duplicate(existing_key: str, item_key: str) -> bool:
    if not existing_key or not item_key:
        return False
    shorter, longer = sorted((existing_key, item_key), key=len)
    if len(shorter) < 4:
        return shorter == longer
    if shorter in longer:
        return True
    shorter_chars = set(shorter)
    longer_chars = set(longer)
    overlap = len(shorter_chars & longer_chars) / max(1, len(shorter_chars))
    return overlap >= 0.92 and abs(len(longer) - len(shorter)) <= 8
