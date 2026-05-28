from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import List, Tuple

from core.dignity.video.schemas import StoryboardScene
from core.dignity.video.storage import output_dir


VIDEO_EXTS = {".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi"}


def render_video(
    server_root: Path,
    task_id: str,
    scenes: List[StoryboardScene],
) -> Tuple[str, str]:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("未找到 ffmpeg，请先安装 ffmpeg 后再生成视频")
    if not scenes:
        raise RuntimeError("分镜为空，无法生成视频")

    out_dir = output_dir(server_root)
    work_dir = out_dir / f"{task_id}_work"
    work_dir.mkdir(parents=True, exist_ok=True)
    segments = []

    for index, scene in enumerate(scenes):
        segment_path = work_dir / f"scene_{index:03d}.mp4"
        media_path = _resolve_media_path(server_root, scene.get("media_url", ""))
        duration = max(3, int(scene.get("duration") or 7))
        if media_path and media_path.exists():
            _render_media_segment(ffmpeg, media_path, segment_path, duration)
        else:
            _render_color_segment(ffmpeg, segment_path, duration)
        segments.append(segment_path)

    concat_path = work_dir / "concat.txt"
    with concat_path.open("w", encoding="utf-8") as file:
        for segment in segments:
            file.write(f"file '{segment.as_posix()}'\n")

    output_name = f"{task_id}.mp4"
    output_path = out_dir / output_name
    _run([
        ffmpeg,
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(concat_path),
        "-c",
        "copy",
        str(output_path),
    ])

    subtitle_path = out_dir / f"{task_id}.srt"
    _write_srt(subtitle_path, scenes)
    return (
        f"/hospice-media/dignity_videos/outputs/{output_name}",
        f"/hospice-media/dignity_videos/outputs/{task_id}.srt",
    )


def _resolve_media_path(server_root: Path, url: str) -> Path | None:
    if not url or not url.startswith("/hospice-media/"):
        return None
    relative = url.replace("/hospice-media/", "", 1).lstrip("/\\")
    path = (server_root / "data" / "hospice_media" / relative).resolve()
    media_root = (server_root / "data" / "hospice_media").resolve()
    try:
        path.relative_to(media_root)
    except ValueError:
        return None
    return path


def _render_media_segment(ffmpeg: str, media_path: Path, segment_path: Path, duration: int) -> None:
    ext = media_path.suffix.lower()
    vf = "scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720,format=yuv420p"
    if ext in VIDEO_EXTS:
        _run([
            ffmpeg,
            "-y",
            "-t",
            str(duration),
            "-i",
            str(media_path),
            "-an",
            "-vf",
            vf,
            "-r",
            "25",
            str(segment_path),
        ])
        return

    _run([
        ffmpeg,
        "-y",
        "-loop",
        "1",
        "-t",
        str(duration),
        "-i",
        str(media_path),
        "-an",
        "-vf",
        vf,
        "-r",
        "25",
        str(segment_path),
    ])


def _render_color_segment(ffmpeg: str, segment_path: Path, duration: int) -> None:
    _run([
        ffmpeg,
        "-y",
        "-f",
        "lavfi",
        "-i",
        "color=c=0x1e1810:s=1280x720:r=25",
        "-t",
        str(duration),
        "-an",
        "-pix_fmt",
        "yuv420p",
        str(segment_path),
    ])


def _write_srt(path: Path, scenes: List[StoryboardScene]) -> None:
    current = 0
    with path.open("w", encoding="utf-8") as file:
        for index, scene in enumerate(scenes, start=1):
            duration = max(3, int(scene.get("duration") or 7))
            start = current
            end = current + duration
            current = end
            file.write(f"{index}\n")
            file.write(f"{_srt_time(start)} --> {_srt_time(end)}\n")
            file.write(f"{scene.get('title', '')}\n{scene.get('text', '')}\n\n")


def _srt_time(seconds: int) -> str:
    return time.strftime("%H:%M:%S", time.gmtime(seconds)) + ",000"


def _run(cmd: List[str]) -> None:
    completed = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if completed.returncode != 0:
        raise RuntimeError((completed.stderr or completed.stdout or "ffmpeg failed")[-1200:])

