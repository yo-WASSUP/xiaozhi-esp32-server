from __future__ import annotations

from typing import Any, Dict, List, TypedDict


class VideoAsset(TypedDict, total=False):
    url: str
    type: str
    label: str
    file_name: str


class StoryboardScene(TypedDict, total=False):
    title: str
    text: str
    media_url: str
    media_type: str
    duration: int


class VideoTask(TypedDict, total=False):
    task_id: str
    device_id: str
    status: str
    storyboard: List[StoryboardScene]
    output_url: str
    subtitle_url: str
    error: str
    created_at: str
    updated_at: str
    meta: Dict[str, Any]

