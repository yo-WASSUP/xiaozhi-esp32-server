from __future__ import annotations

import copy
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Tuple

from core.dignity.video.schemas import StoryboardScene
from core.dignity.video.storage import output_dir


VIDEO_EXTS = {".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi"}
AUDIO_EXTS = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac"}
TITLE_DURATION = 2


def render_video(
    server_root: Path,
    task_id: str,
    scenes: List[StoryboardScene],
    options: Dict[str, Any] | None = None,
    config: Dict[str, Any] | None = None,
) -> Tuple[str, str]:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("未找到 ffmpeg，请先安装 ffmpeg 后再生成视频")
    if not scenes:
        raise RuntimeError("分镜为空，无法生成视频")

    options = options or {}
    title = str(options.get("title") or "生命回顾影像").strip() or "生命回顾影像"
    out_dir = output_dir(server_root)
    work_dir = out_dir / f"{task_id}_work"
    work_dir.mkdir(parents=True, exist_ok=True)

    scenes, narration_path = _prepare_timed_scenes(
        ffmpeg=ffmpeg,
        work_dir=work_dir,
        scenes=scenes,
        config=config or {},
        voiceover=bool(options.get("voiceover", True)),
        narration_voice=str(options.get("narration_voice") or ""),
    )

    segments = []
    title_segment = work_dir / "scene_title.mp4"
    _render_title_segment(ffmpeg, title_segment, TITLE_DURATION)
    segments.append(title_segment)

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

    raw_video_path = work_dir / "visual_raw.mp4"
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
        str(raw_video_path),
    ])

    ass_path = work_dir / "overlay.ass"
    _write_ass(ass_path, scenes, title=title)

    subtitled_path = _render_text_overlay(
        ffmpeg=ffmpeg,
        work_dir=work_dir,
        raw_video_path=raw_video_path,
        ass_path=ass_path,
        scenes=scenes,
        title=title,
    )

    output_name = f"{task_id}.mp4"
    output_path = out_dir / output_name
    audio_inputs = _build_audio_inputs(
        ffmpeg=ffmpeg,
        server_root=server_root,
        work_dir=work_dir,
        scenes=scenes,
        options=options,
        config=config or {},
        narration_path=narration_path,
    )
    _mux_final_video(ffmpeg, subtitled_path, output_path, audio_inputs)

    return (
        f"/hospice-media/dignity_videos/outputs/{output_name}",
        "",
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


def _render_title_segment(ffmpeg: str, segment_path: Path, duration: int) -> None:
    _run([
        ffmpeg,
        "-y",
        "-f",
        "lavfi",
        "-i",
        "color=c=0x201a12:s=1280x720:r=25",
        "-t",
        str(duration),
        "-an",
        "-pix_fmt",
        "yuv420p",
        str(segment_path),
    ])


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


def _build_audio_inputs(
    ffmpeg: str,
    server_root: Path,
    work_dir: Path,
    scenes: List[StoryboardScene],
    options: Dict[str, Any],
    config: Dict[str, Any],
    narration_path: Path | None = None,
) -> List[Path]:
    audio_inputs: List[Path] = []
    if narration_path:
        audio_inputs.append(narration_path)

    if options.get("background_music", True):
        music = _resolve_media_path(server_root, str(options.get("music_url") or ""))
        if not music or not music.exists() or music.suffix.lower() not in AUDIO_EXTS:
            music = _default_background_music(server_root)
        if not music or not music.exists() or music.suffix.lower() not in AUDIO_EXTS:
            music = _generate_background_music(ffmpeg, work_dir, _total_duration(scenes))
        if music:
            audio_inputs.append(music)
    return audio_inputs


def _prepare_timed_scenes(
    ffmpeg: str,
    work_dir: Path,
    scenes: List[StoryboardScene],
    config: Dict[str, Any],
    voiceover: bool,
    narration_voice: str = "",
) -> Tuple[List[StoryboardScene], Path | None]:
    timed_scenes = [dict(scene) for scene in scenes]
    if not voiceover:
        return timed_scenes, None

    audio_items: List[Tuple[Path | None, int]] = []
    has_narration = False
    for index, scene in enumerate(timed_scenes):
        text = str(scene.get("text") or "").strip()
        duration = max(3, int(scene.get("duration") or 7))
        audio_path = _generate_scene_narration_audio(work_dir, text, config, index, narration_voice)
        if audio_path:
            duration = max(3, int(round(_probe_media_duration(ffmpeg, audio_path) + 1.0)))
            has_narration = True
        scene["duration"] = duration
        audio_items.append((audio_path, duration))

    if not has_narration:
        return timed_scenes, None
    return timed_scenes, _build_narration_timeline(ffmpeg, work_dir, audio_items)


def _generate_scene_narration_audio(
    work_dir: Path,
    text: str,
    config: Dict[str, Any],
    index: int,
    narration_voice: str = "",
) -> Path | None:
    if not text:
        return None
    try:
        from core.utils import tts

        tts_config = copy.deepcopy(config)
        selected = (tts_config.get("selected_module") or {}).get("TTS")
        if not selected:
            return None
        module_config = (tts_config.get("TTS") or {}).get(selected)
        if not isinstance(module_config, dict):
            return None
        module_config["output_dir"] = str(work_dir)
        module_config["delete_audio"] = False
        module_config["save_path"] = str(work_dir / f"narration_source_{index:03d}.wav")
        voice_id = _resolve_narration_voice(config, narration_voice)
        if voice_id and (module_config.get("type") == "alibl_stream" or selected == "AliBLTTS"):
            module_config["voice"] = voice_id
        provider_type = module_config.get("type") or selected
        provider = tts.create_instance(provider_type, module_config, False)
        provider.conn = _OfflineTTSContext()
        audio_path = provider.to_tts(text)
        if audio_path and Path(audio_path).exists():
            return Path(audio_path)
    except Exception:
        return None
    return None


def _resolve_narration_voice(config: Dict[str, Any], requested: str = "") -> str:
    allowed = {"longlaobo_v3", "longlaoyi_v3"}
    if requested in allowed:
        return requested
    hospice = config.get("hospice") or {}
    configured = str(hospice.get("life_review_narration_voice") or "").strip()
    if configured in allowed:
        return configured
    return "longlaoyi_v3"


def _build_narration_timeline(
    ffmpeg: str,
    work_dir: Path,
    audio_items: List[Tuple[Path | None, int]],
) -> Path:
    parts: List[Path] = []
    title_part = work_dir / "narration_part_title.wav"
    _render_silence_audio(ffmpeg, title_part, TITLE_DURATION)
    parts.append(title_part)

    for index, (audio_path, duration) in enumerate(audio_items):
        part_path = work_dir / f"narration_part_{index:03d}.wav"
        if audio_path:
            _normalize_audio_part(ffmpeg, audio_path, part_path, duration)
        else:
            _render_silence_audio(ffmpeg, part_path, duration)
        parts.append(part_path)

    concat_path = work_dir / "narration_concat.txt"
    with concat_path.open("w", encoding="utf-8") as file:
        for part in parts:
            file.write(f"file '{part.as_posix()}'\n")

    output_path = work_dir / "narration_timeline.wav"
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
    return output_path


def _normalize_audio_part(ffmpeg: str, input_path: Path, output_path: Path, duration: int) -> None:
    _run([
        ffmpeg,
        "-y",
        "-i",
        str(input_path),
        "-af",
        f"apad,atrim=0:{duration}",
        "-ac",
        "2",
        "-ar",
        "44100",
        "-c:a",
        "pcm_s16le",
        str(output_path),
    ])


def _render_silence_audio(ffmpeg: str, output_path: Path, duration: int) -> None:
    _run([
        ffmpeg,
        "-y",
        "-f",
        "lavfi",
        "-i",
        "anullsrc=channel_layout=stereo:sample_rate=44100",
        "-t",
        str(duration),
        "-c:a",
        "pcm_s16le",
        str(output_path),
    ])


def _probe_media_duration(ffmpeg: str, path: Path) -> float:
    ffmpeg_path = Path(ffmpeg)
    ffprobe = ffmpeg_path.with_name("ffprobe.exe") if ffmpeg_path.name.lower().endswith(".exe") else shutil.which("ffprobe")
    if not ffprobe:
        ffprobe = "ffprobe"
    completed = subprocess.run(
        [
            str(ffprobe),
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        return max(0.0, float((completed.stdout or "").strip()))
    except ValueError:
        return 0.0


class _OfflineTTSContext:
    sample_rate = 24000
    audio_format = "pcm"
    llm_first_token_time = None


def _default_background_music(server_root: Path) -> Path | None:
    path = server_root / "data" / "hospice_media" / "dignity_videos" / "bgm" / "life_review_bgm.mp3"
    return path if path.exists() else None


def _generate_background_music(ffmpeg: str, work_dir: Path, duration: int) -> Path | None:
    music_path = work_dir / "background_music.wav"
    try:
        _run([
            ffmpeg,
            "-y",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=196:sample_rate=44100",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=247:sample_rate=44100",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=330:sample_rate=44100",
            "-filter_complex",
            f"[0:a][1:a][2:a]amix=inputs=3:duration=longest,afade=t=in:st=0:d=2,afade=t=out:st={max(0, duration - 3)}:d=3,volume=0.08",
            "-t",
            str(duration),
            str(music_path),
        ])
        return music_path
    except Exception:
        return None


def _render_text_overlay(
    ffmpeg: str,
    work_dir: Path,
    raw_video_path: Path,
    ass_path: Path,
    scenes: List[StoryboardScene],
    title: str,
) -> Path:
    subtitled_path = work_dir / "visual_subtitled.mp4"
    try:
        _run([
            ffmpeg,
            "-y",
            "-i",
            str(raw_video_path),
            "-vf",
            f"ass=filename={ass_path.name}",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-an",
            str(subtitled_path),
        ], cwd=work_dir)
        return subtitled_path
    except RuntimeError:
        pass

    try:
        _render_drawtext_overlay(ffmpeg, work_dir, raw_video_path, subtitled_path, scenes, title)
        return subtitled_path
    except RuntimeError:
        _run([
            ffmpeg,
            "-y",
            "-i",
            str(raw_video_path),
            "-c",
            "copy",
            str(subtitled_path),
        ])
        return subtitled_path


def _render_drawtext_overlay(
    ffmpeg: str,
    work_dir: Path,
    raw_video_path: Path,
    output_path: Path,
    scenes: List[StoryboardScene],
    title: str,
) -> None:
    filters = []
    font = _drawtext_font_option()

    title_file = _write_drawtext_file(work_dir, "draw_title.txt", title)
    filters.append(
        _drawtext_filter(
            text_file=title_file.name,
            start=0,
            end=TITLE_DURATION,
            font=font,
            size=56,
            color="0xF7EFE1",
            border=3,
            x="(w-text_w)/2",
            y="(h-text_h)/2",
        )
    )

    current = TITLE_DURATION
    for index, scene in enumerate(scenes):
        duration = max(3, int(scene.get("duration") or 7))
        start = current
        end = current + duration
        current = end

        scene_title = str(scene.get("title") or "").strip()
        if scene_title:
            title_path = _write_drawtext_file(work_dir, f"draw_scene_title_{index:03d}.txt", scene_title)
            filters.append(
                _drawtext_filter(
                    text_file=title_path.name,
                    start=start,
                    end=end,
                    font=font,
                    size=34,
                    color="0xF7EFE1",
                    border=2,
                    x="(w-text_w)/2",
                    y="42",
                )
            )

        body = str(scene.get("text") or "").strip()
        if body:
            body_path = _write_drawtext_file(work_dir, f"draw_subtitle_{index:03d}.txt", _wrap_text(body, 24).replace(r"\N", "\n"))
            filters.append(
                _drawtext_filter(
                    text_file=body_path.name,
                    start=start,
                    end=end,
                    font=font,
                    size=30,
                    color="white",
                    border=3,
                    x="(w-text_w)/2",
                    y="h-text_h-58",
                )
            )

    if not filters:
        _run([
            ffmpeg,
            "-y",
            "-i",
            str(raw_video_path),
            "-c",
            "copy",
            str(output_path),
        ])
        return

    _run([
        ffmpeg,
        "-y",
        "-i",
        str(raw_video_path),
        "-vf",
        ",".join(filters),
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-an",
        str(output_path),
    ], cwd=work_dir)


def _write_drawtext_file(work_dir: Path, name: str, text: str) -> Path:
    path = work_dir / name
    path.write_text(str(text or ""), encoding="utf-8")
    return path


def _drawtext_font_option() -> str:
    for candidate in (
        Path("C:/Windows/Fonts/msyh.ttc"),
        Path("C:/Windows/Fonts/simhei.ttf"),
        Path("C:/Windows/Fonts/simsun.ttc"),
    ):
        if candidate.exists():
            value = candidate.as_posix().replace(":", r"\:")
            return f":fontfile='{value}'"
    return ""


def _drawtext_filter(
    text_file: str,
    start: int,
    end: int,
    font: str,
    size: int,
    color: str,
    border: int,
    x: str,
    y: str,
) -> str:
    return (
        f"drawtext=textfile='{text_file}'{font}:fontsize={size}:fontcolor={color}:"
        f"borderw={border}:bordercolor=black@0.75:line_spacing=8:"
        f"x={x}:y={y}:enable='between(t\\,{start}\\,{end})'"
    )


def _mux_final_video(ffmpeg: str, video_path: Path, output_path: Path, audio_inputs: List[Path]) -> None:
    if not audio_inputs:
        _run([
            ffmpeg,
            "-y",
            "-i",
            str(video_path),
            "-c",
            "copy",
            str(output_path),
        ])
        return

    cmd = [ffmpeg, "-y", "-i", str(video_path)]
    for item in audio_inputs:
        cmd.extend(["-i", str(item)])

    if len(audio_inputs) == 1:
        cmd.extend([
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-shortest",
            str(output_path),
        ])
        _run(cmd)
        return

    filter_inputs = "".join(f"[{index}:a]" for index in range(1, len(audio_inputs) + 1))
    cmd.extend([
        "-filter_complex",
        f"{filter_inputs}amix=inputs={len(audio_inputs)}:duration=first:dropout_transition=2,volume=1.0[aout]",
        "-map",
        "0:v:0",
        "-map",
        "[aout]",
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        "-shortest",
        str(output_path),
    ])
    _run(cmd)


def _write_ass(path: Path, scenes: List[StoryboardScene], title: str) -> None:
    lines = [
        "[Script Info]",
        "ScriptType: v4.00+",
        "PlayResX: 1280",
        "PlayResY: 720",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        "Style: Title,Microsoft YaHei,56,&H00F7EFE1,&H000000FF,&HAA1D1710,&H661D1710,0,0,0,0,100,100,0,0,1,2,1,5,80,80,60,1",
        "Style: SceneTitle,Microsoft YaHei,34,&H00F7EFE1,&H000000FF,&HAA1D1710,&H661D1710,0,0,0,0,100,100,0,0,1,2,1,8,70,70,42,1",
        "Style: Subtitle,Microsoft YaHei,30,&H00FFFFFF,&H000000FF,&HCC1D1710,&H881D1710,0,0,0,0,100,100,0,0,1,2,1,2,72,72,58,1",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
        f"Dialogue: 0,{_ass_time(0)},{_ass_time(TITLE_DURATION)},Title,,0,0,0,,{_ass_text(title)}",
    ]
    current = TITLE_DURATION
    for scene in scenes:
        duration = max(3, int(scene.get("duration") or 7))
        start = current
        end = current + duration
        current = end
        scene_title = str(scene.get("title") or "").strip()
        body = str(scene.get("text") or "").strip()
        if scene_title:
            lines.append(
                f"Dialogue: 0,{_ass_time(start)},{_ass_time(end)},SceneTitle,,0,0,0,,{_ass_text(scene_title)}"
            )
        if body:
            lines.append(
                f"Dialogue: 1,{_ass_time(start)},{_ass_time(end)},Subtitle,,0,0,0,,{_ass_text(_wrap_text(body, 24))}"
            )
    path.write_text("\n".join(lines), encoding="utf-8")


def _total_duration(scenes: List[StoryboardScene]) -> int:
    return TITLE_DURATION + sum(max(3, int(scene.get("duration") or 7)) for scene in scenes)


def _wrap_text(text: str, width: int) -> str:
    text = " ".join(str(text or "").split())
    if len(text) <= width:
        return text
    parts = []
    current = ""
    for char in text:
        current += char
        if len(current) >= width and char in "，。！？；、 ":
            parts.append(current.strip())
            current = ""
    if current:
        parts.append(current.strip())
    if len(parts) <= 1:
        parts = [text[index:index + width] for index in range(0, len(text), width)]
    return r"\N".join(parts[:3])


def _ass_text(text: str) -> str:
    return str(text or "").replace("\\", r"\\").replace("{", r"\{").replace("}", r"\}").replace("\n", r"\N")


def _ass_time(seconds: int) -> str:
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    return f"{h:d}:{m:02d}:{s:02d}.00"


def _run(cmd: List[str], cwd: Path | None = None) -> None:
    completed = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=str(cwd) if cwd else None,
    )
    if completed.returncode != 0:
        raise RuntimeError((completed.stderr or completed.stdout or "ffmpeg failed")[-1200:])
