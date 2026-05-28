from __future__ import annotations

import re
from typing import Any, Dict, List

from core.dignity.video.schemas import StoryboardScene, VideoAsset


MAX_SCENES = 12
MIN_SCENES = 3


def build_storyboard(
    document: str,
    memory: Dict[str, List[Any]] | None = None,
    assets: List[VideoAsset] | None = None,
) -> List[StoryboardScene]:
    paragraphs = _document_paragraphs(document)
    memory_lines = _memory_lines(memory or {})
    source_lines = paragraphs or memory_lines
    if not source_lines:
        source_lines = ["这是根据访谈记忆整理的一段生命回顾。"]

    scenes = [_scene_from_text(text) for text in source_lines[:MAX_SCENES]]
    if len(scenes) < MIN_SCENES and memory_lines:
        for text in memory_lines:
            if len(scenes) >= MIN_SCENES:
                break
            if text not in [scene["text"] for scene in scenes]:
                scenes.append(_scene_from_text(text))

    _assign_media(scenes, assets or [])
    return scenes


def _document_paragraphs(document: str) -> List[str]:
    lines = []
    for raw in (document or "").splitlines():
        text = raw.strip()
        if not text or text.startswith("#"):
            continue
        if re.fullmatch(r"\d{4}年\d{1,2}月\d{1,2}日星期[一二三四五六日天]", text):
            continue
        lines.append(text)
    paragraphs = []
    for line in lines:
        if len(line) <= 90:
            paragraphs.append(line)
            continue
        paragraphs.extend(_split_long_text(line))
    return [item for item in paragraphs if item][:MAX_SCENES]


def _split_long_text(text: str) -> List[str]:
    parts = re.split(r"(?<=[。！？])", text)
    chunks: List[str] = []
    current = ""
    for part in parts:
        if not part:
            continue
        if len(current) + len(part) <= 90:
            current += part
            continue
        if current:
            chunks.append(current)
        current = part
    if current:
        chunks.append(current)
    return chunks


def _memory_lines(memory: Dict[str, List[Any]]) -> List[str]:
    lines = []
    labels = {
        "life_story_materials": "生命故事",
        "important_relationships": "重要关系",
        "values_and_strengths": "珍视的事",
        "messages_to_family": "想说的话",
    }
    for key, label in labels.items():
        for item in memory.get(key, []) or []:
            text = _item_text(item)
            if text:
                lines.append(f"{label}：{text}")
    return lines


def _item_text(item: Any) -> str:
    if isinstance(item, str):
        return item.strip()
    if isinstance(item, dict):
        return "；".join(str(value).strip() for value in item.values() if str(value).strip())
    return str(item or "").strip()


def _scene_from_text(text: str) -> StoryboardScene:
    title = _title_from_text(text)
    duration = max(6, min(12, round(len(text) / 12) + 5))
    return {
        "title": title,
        "text": text,
        "duration": duration,
    }


def _title_from_text(text: str) -> str:
    clean = re.sub(r"^[^：:]{2,8}[：:]", "", text).strip()
    for sep in "，。；：":
        if sep in clean:
            clean = clean.split(sep, 1)[0]
            break
    return clean[:16] or "生命回顾"


def _assign_media(scenes: List[StoryboardScene], assets: List[VideoAsset]) -> None:
    if not assets:
        return
    unused = list(assets)
    for index, scene in enumerate(scenes):
        asset = _best_asset(scene, unused) or _best_asset(scene, assets) or assets[index % len(assets)]
        if asset in unused:
            unused.remove(asset)
        scene["media_url"] = asset.get("url", "")
        scene["media_type"] = asset.get("type", "")


def _best_asset(scene: StoryboardScene, assets: List[VideoAsset]) -> VideoAsset | None:
    scene_text = f"{scene.get('title', '')} {scene.get('text', '')}"
    best = None
    best_score = 0
    for asset in assets:
        label = asset.get("label") or asset.get("file_name") or ""
        score = _match_score(scene_text, label)
        if score > best_score:
            best = asset
            best_score = score
    return best if best_score > 0 else None


def _match_score(text: str, label: str) -> int:
    text = text.lower()
    tokens = [token for token in re.split(r"[\s,，。；;、_\-.]+", label.lower()) if token]
    return sum(1 for token in tokens if token and token in text)

