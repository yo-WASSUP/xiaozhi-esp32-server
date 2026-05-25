from __future__ import annotations

import json
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
        merged[str(key)] = list(items) if isinstance(items, list) else []

    for key, items in (update or {}).items():
        if not isinstance(items, list):
            continue
        bucket = merged.setdefault(str(key), [])
        seen = {_stable_key(item) for item in bucket}
        for item in items:
            item_key = _stable_key(item)
            if item_key in seen:
                continue
            bucket.append(item)
            seen.add(item_key)
    return merged


def _stable_key(item: Any) -> str:
    return json.dumps(item, ensure_ascii=False, sort_keys=True)
