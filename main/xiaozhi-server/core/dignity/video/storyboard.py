from __future__ import annotations

import copy
import json
import re
from typing import Any, Dict, List

from core.dignity.video.schemas import StoryboardScene, VideoAsset


MAX_SCENES = 80
MIN_SCENES = 3
SMART_MIN_SCENES = 6
SMART_MAX_SCENES = 10


def build_storyboard(
    document: str,
    memory: Dict[str, List[Any]] | None = None,
    assets: List[VideoAsset] | None = None,
    config: Dict[str, Any] | None = None,
) -> List[StoryboardScene]:
    smart_scenes = _build_smart_storyboard(document, memory or {}, config or {})
    if smart_scenes:
        _assign_media(smart_scenes, assets or [])
        return smart_scenes

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


def _build_smart_storyboard(
    document: str,
    memory: Dict[str, List[Any]],
    config: Dict[str, Any],
) -> List[StoryboardScene]:
    if not (document or "").strip():
        return []
    try:
        provider = _create_llm_provider(config)
        if not provider:
            return []
        content = provider.response_no_stream(
            _smart_storyboard_system_prompt(),
            _smart_storyboard_user_prompt(document, memory),
            temperature=0.2,
            max_tokens=2500,
        )
        scenes = _parse_smart_storyboard(content)
        return scenes[:SMART_MAX_SCENES]
    except Exception:
        return []


def _create_llm_provider(config: Dict[str, Any]):
    selected = (config.get("selected_module") or {}).get("LLM")
    if not selected:
        return None
    module_config = (config.get("LLM") or {}).get(selected)
    if not isinstance(module_config, dict):
        return None
    from core.utils import llm

    safe_config = copy.deepcopy(module_config)
    provider_type = safe_config.get("type") or selected
    return llm.create_instance(provider_type, safe_config)


def _smart_storyboard_system_prompt() -> str:
    return (
        "你是一名安宁疗护生命回顾影像导演。"
        "你的任务是从人生故事中选择最适合做短片的关键内容，"
        "生成克制、温暖、适合家属观看的中文分镜。"
        "不要逐字复述全文，不要编造故事没有的信息。"
        "只输出 JSON，不要输出 Markdown。"
    )


def _smart_storyboard_user_prompt(document: str, memory: Dict[str, List[Any]]) -> str:
    memory_text = json.dumps(memory or {}, ensure_ascii=False)
    return f"""
请把下面的人生故事整理成 {SMART_MIN_SCENES} 到 {SMART_MAX_SCENES} 个视频分镜。

要求：
1. 每个分镜代表一个清晰主题或人生片段，不要把故事所有句子都塞进去。
2. 分镜顺序要自然：开场、人生经历、重要关系、珍视的事、给家人的话、收束。
3. 每条 text 是旁白稿，建议 40 到 90 个中文字符，口语、温和、适合 TTS 朗读。
4. title 控制在 4 到 12 个中文字符。
5. duration 给一个初始估计，范围 6 到 14 秒；后续系统会按真实 TTS 时长校准。
6. 若信息不足，少做分镜；不要补不存在的经历。

输出格式：
{{
  "scenes": [
    {{"title": "分镜标题", "text": "旁白文本", "duration": 10}}
  ]
}}

人生故事：
{(document or "").strip()[:12000]}

结构化记忆，可作为补充但不要优先于人生故事：
{memory_text[:4000]}
""".strip()


def _parse_smart_storyboard(content: str) -> List[StoryboardScene]:
    text = (content or "").strip()
    if not text:
        return []
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        extracted = _extract_json_from_string(text)
        if not extracted:
            return []
        value = json.loads(extracted)
    raw_scenes = value.get("scenes") if isinstance(value, dict) else value
    if not isinstance(raw_scenes, list):
        return []

    scenes: List[StoryboardScene] = []
    for item in raw_scenes:
        if not isinstance(item, dict):
            continue
        body = str(item.get("text") or "").strip()
        if not body:
            continue
        title = str(item.get("title") or _title_from_text(body)).strip()[:16]
        try:
            duration = int(item.get("duration") or 10)
        except (TypeError, ValueError):
            duration = 10
        scenes.append({
            "title": title or _title_from_text(body),
            "text": body,
            "duration": max(6, min(14, duration)),
        })

    if len(scenes) < MIN_SCENES:
        return []
    return scenes


def _extract_json_from_string(text: str) -> str:
    start = min(
        [index for index in (text.find("{"), text.find("[")) if index >= 0],
        default=-1,
    )
    if start < 0:
        return ""
    pairs = {"{": "}", "[": "]"}
    opener = text[start]
    closer = pairs.get(opener)
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if char == opener:
            depth += 1
        elif char == closer:
            depth -= 1
            if depth == 0:
                return text[start:index + 1]
    return ""


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
