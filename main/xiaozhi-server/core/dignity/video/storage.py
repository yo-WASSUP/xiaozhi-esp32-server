from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any, Dict


def new_task_id() -> str:
    return f"video_{time.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"


def video_root(server_root: Path) -> Path:
    return server_root / "data" / "hospice_media" / "dignity_videos"


def task_dir(server_root: Path) -> Path:
    path = video_root(server_root) / "tasks"
    path.mkdir(parents=True, exist_ok=True)
    return path


def output_dir(server_root: Path) -> Path:
    path = video_root(server_root) / "outputs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_task(server_root: Path, task: Dict[str, Any]) -> None:
    path = task_dir(server_root) / f"{task['task_id']}.json"
    with path.open("w", encoding="utf-8") as file:
        json.dump(task, file, ensure_ascii=False, indent=2)


def load_task(server_root: Path, task_id: str) -> Dict[str, Any] | None:
    path = task_dir(server_root) / f"{task_id}.json"
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as file:
        value = json.load(file)
    return value if isinstance(value, dict) else None

