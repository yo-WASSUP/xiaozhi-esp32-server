"""Life review video endpoints for the hospice API."""
from __future__ import annotations

import asyncio
import json
import mimetypes
import re
import time
import uuid
from datetime import datetime
from pathlib import Path

from aiohttp import web
from config.logger import setup_logging
from core.dignity.video.renderer import render_video
from core.dignity.video.storage import load_task, new_task_id, save_task
from core.dignity.video.storyboard import build_storyboard

TAG = __name__
logger = setup_logging()

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
VIDEO_EXTS = {".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi", ".ogv", ".3gp"}
AUDIO_EXTS = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac"}
ASSET_EXTS = IMAGE_EXTS | VIDEO_EXTS | AUDIO_EXTS


class HospiceVideoMixin:
    async def handle_video_source(self, request):
        """GET /api/hospice/video/source?device_id=xxx."""
        try:
            device_id = request.query.get("device_id", "default")
            server_root = Path(__file__).resolve().parents[3]
            source = _load_video_source(server_root, device_id)
            return web.json_response({"success": True, **source}, headers=self._cors_headers())
        except Exception as e:
            logger.bind(tag=TAG).error(f"生命回顾视频来源读取失败: {e}")
            return web.json_response(
                {"success": False, "error": str(e)},
                status=500,
                headers=self._cors_headers(),
            )

    async def handle_video_assets(self, request):
        """POST /api/hospice/video/assets multipart: device_id, file."""
        try:
            reader = await request.multipart()
            device_id = "default"
            file_field = None
            while True:
                field = await reader.next()
                if field is None:
                    break
                if field.name == "device_id":
                    device_id = (await field.text() or "default").strip() or "default"
                    continue
                if field.name == "file":
                    file_field = field
                    break

            if file_field is None:
                return web.json_response(
                    {"success": False, "error": "missing file field"},
                    status=400,
                    headers=self._cors_headers(),
                )

            server_root = Path(__file__).resolve().parents[3]
            asset = await _save_video_asset(server_root, device_id, file_field, self.config)
            return web.json_response({"success": True, "asset": asset}, headers=self._cors_headers())
        except Exception as e:
            logger.bind(tag=TAG).error(f"生命回顾素材上传失败: {e}")
            return web.json_response(
                {"success": False, "error": str(e)},
                status=500,
                headers=self._cors_headers(),
            )

    async def handle_video_asset_delete(self, request):
        """DELETE /api/hospice/video/assets body: {device_id, url}."""
        try:
            data = await request.json()
            device_id = (data.get("device_id") or "default").strip() or "default"
            url = (data.get("url") or "").strip()
            if not url:
                return web.json_response(
                    {"success": False, "error": "url required"},
                    status=400,
                    headers=self._cors_headers(),
                )
            server_root = Path(__file__).resolve().parents[3]
            deleted = _delete_video_asset(server_root, device_id, url)
            return web.json_response({"success": True, "deleted": deleted}, headers=self._cors_headers())
        except Exception as e:
            logger.bind(tag=TAG).error(f"生命回顾素材删除失败: {e}")
            return web.json_response(
                {"success": False, "error": str(e)},
                status=500,
                headers=self._cors_headers(),
            )

    async def handle_video_asset_update(self, request):
        """PATCH /api/hospice/video/assets body: {device_id, url, label}."""
        try:
            data = await request.json()
            device_id = (data.get("device_id") or "default").strip() or "default"
            url = (data.get("url") or "").strip()
            label = (data.get("label") or "").strip()
            if not url:
                return web.json_response(
                    {"success": False, "error": "url required"},
                    status=400,
                    headers=self._cors_headers(),
                )
            server_root = Path(__file__).resolve().parents[3]
            asset = _update_video_asset_label(server_root, device_id, url, label)
            return web.json_response({"success": True, "asset": asset}, headers=self._cors_headers())
        except Exception as e:
            logger.bind(tag=TAG).error(f"生命回顾素材更新失败: {e}")
            return web.json_response(
                {"success": False, "error": str(e)},
                status=500,
                headers=self._cors_headers(),
            )

    async def handle_video_storyboard(self, request):
        """POST /api/hospice/video/storyboard.

        body: {device_id, document?, memory?, assets?}
        If document/assets are omitted, the server reads the persisted patient
        dignity document and the dedicated life-review asset library.
        """
        try:
            data = await request.json()
            device_id = (data.get("device_id") or "default").strip() or "default"
            server_root = Path(__file__).resolve().parents[3]
            source = _load_video_source(server_root, device_id)

            document = data.get("document") or source.get("document") or ""
            memory = data.get("memory") or source.get("memory") or {}
            assets = data.get("assets")
            if assets is None:
                assets = source.get("assets") or []

            scenes = build_storyboard(document=document, memory=memory, assets=assets, config=self.config)
            return web.json_response(
                {"success": True, "storyboard": scenes, "source": source},
                headers=self._cors_headers(),
            )
        except Exception as e:
            logger.bind(tag=TAG).error(f"生命回顾视频分镜生成失败: {e}")
            return web.json_response(
                {"success": False, "error": str(e)},
                status=500,
                headers=self._cors_headers(),
            )

    async def handle_video_render(self, request):
        """POST /api/hospice/video/render body: {device_id, storyboard}."""
        try:
            data = await request.json()
            device_id = (data.get("device_id") or "default").strip()
            storyboard = data.get("storyboard") or []
            if not isinstance(storyboard, list) or not storyboard:
                return web.json_response(
                    {"success": False, "error": "storyboard required"},
                    status=400,
                    headers=self._cors_headers(),
                )

            server_root = Path(__file__).resolve().parents[3]
            task_id = new_task_id()
            now = datetime.now().isoformat(timespec="seconds")
            task = {
                "task_id": task_id,
                "device_id": device_id,
                "status": "running",
                "storyboard": storyboard,
                "created_at": now,
                "updated_at": now,
            }
            save_task(server_root, task)
            try:
                output_url, subtitle_url = await asyncio.get_running_loop().run_in_executor(
                    None,
                    render_video,
                    server_root,
                    task_id,
                    storyboard,
                    {
                        "title": data.get("title") or "生命回顾影像",
                        "voiceover": data.get("voiceover", True),
                        "narration_voice": data.get("narration_voice") or "",
                        "background_music": data.get("background_music", True),
                        "music_url": data.get("music_url") or "",
                    },
                    self.config,
                )
                task.update({
                    "status": "ready",
                    "output_url": output_url,
                    "subtitle_url": subtitle_url,
                    "updated_at": datetime.now().isoformat(timespec="seconds"),
                })
                save_task(server_root, task)
                return web.json_response({"success": True, "task": task}, headers=self._cors_headers())
            except Exception as exc:
                task.update({
                    "status": "failed",
                    "error": str(exc),
                    "updated_at": datetime.now().isoformat(timespec="seconds"),
                })
                save_task(server_root, task)
                return web.json_response(
                    {"success": False, "error": str(exc), "task": task},
                    status=500,
                    headers=self._cors_headers(),
                )
        except Exception as e:
            logger.bind(tag=TAG).error(f"生命回顾视频生成失败: {e}")
            return web.json_response(
                {"success": False, "error": str(e)},
                status=500,
                headers=self._cors_headers(),
            )

    async def handle_video_status(self, request):
        task_id = request.query.get("task_id", "").strip()
        if not task_id:
            return web.json_response(
                {"success": False, "error": "task_id required"},
                status=400,
                headers=self._cors_headers(),
            )
        server_root = Path(__file__).resolve().parents[3]
        task = load_task(server_root, task_id)
        if not task:
            return web.json_response(
                {"success": False, "error": "task not found"},
                status=404,
                headers=self._cors_headers(),
            )
        return web.json_response({"success": True, "task": task}, headers=self._cors_headers())


def _safe_key(value: str) -> str:
    key = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value or "")).strip("._")
    return key or "default"


def _load_video_source(server_root: Path, device_id: str) -> dict:
    patient_id = _safe_key(device_id)
    document_record = _load_latest_document_record(server_root, patient_id)
    return {
        "device_id": patient_id,
        "document": document_record.get("document", ""),
        "document_status": document_record.get("document_status", ""),
        "document_url": document_record.get("document_url", ""),
        "document_filename": document_record.get("document_filename", ""),
        "memory": _load_memory(server_root, patient_id),
        "assets": _list_video_assets(server_root, patient_id),
    }


def _load_latest_document_record(server_root: Path, patient_id: str) -> dict:
    source_dir = server_root / "data" / "hospice_media" / "dignity_documents" / "sources"
    for path in (source_dir / f"{patient_id}_latest.json", source_dir / f"{patient_id}.json"):
        if not path.exists():
            continue
        try:
            with path.open("r", encoding="utf-8") as file:
                value = json.load(file)
            return value if isinstance(value, dict) else {}
        except Exception:
            continue
    return {}


def _load_memory(server_root: Path, patient_id: str) -> dict:
    path = server_root / "data" / "dignity_memory" / f"{patient_id}.json"
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as file:
            value = json.load(file)
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def _asset_dir(server_root: Path, patient_id: str) -> Path:
    return server_root / "data" / "hospice_media" / "dignity_videos" / "assets" / patient_id


def _asset_meta_path(server_root: Path, patient_id: str) -> Path:
    return _asset_dir(server_root, patient_id) / "_assets.json"


def _load_asset_meta(server_root: Path, patient_id: str) -> dict:
    path = _asset_meta_path(server_root, patient_id)
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as file:
            value = json.load(file)
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def _save_asset_meta(server_root: Path, patient_id: str, meta: dict) -> None:
    path = _asset_meta_path(server_root, patient_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(meta, file, ensure_ascii=False, indent=2)


def _list_video_assets(server_root: Path, patient_id: str) -> list:
    root = _asset_dir(server_root, patient_id)
    if not root.exists():
        return []
    meta = _load_asset_meta(server_root, patient_id)
    assets = []
    for path in sorted(root.iterdir(), key=lambda item: item.stat().st_mtime, reverse=True):
        if not path.is_file() or path.suffix.lower() not in ASSET_EXTS:
            continue
        ext = path.suffix.lower()
        media_type = _asset_media_type(ext)
        item_meta = meta.get(path.name, {}) if isinstance(meta.get(path.name), dict) else {}
        assets.append({
            "url": f"/hospice-media/dignity_videos/assets/{patient_id}/{path.name}",
            "type": media_type,
            "label": item_meta.get("label") or path.stem,
            "file_name": path.name,
            "selected": True,
        })
    return assets


async def _save_video_asset(server_root: Path, device_id: str, field, config: dict) -> dict:
    patient_id = _safe_key(device_id)
    filename = field.filename or ""
    ext = Path(filename).suffix.lower()
    if not ext:
        content_type = (field.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        ext = mimetypes.guess_extension(content_type) or ".bin"
    if ext not in ASSET_EXTS:
        raise ValueError("only image, video, or audio files are supported")

    max_mb = int((config.get("hospice", {}) or {}).get("upload_max_mb", 50))
    max_bytes = max_mb * 1024 * 1024
    root = _asset_dir(server_root, patient_id)
    root.mkdir(parents=True, exist_ok=True)
    safe_name = f"{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}{ext}"
    path = root / safe_name

    size = 0
    with path.open("wb") as file:
        while True:
            chunk = await field.read_chunk(64 * 1024)
            if not chunk:
                break
            size += len(chunk)
            if size > max_bytes:
                try:
                    path.unlink()
                except OSError:
                    pass
                raise ValueError(f"file too large, max {max_mb}MB")
            file.write(chunk)

    media_type = _asset_media_type(ext)
    meta = _load_asset_meta(server_root, patient_id)
    meta[safe_name] = {
        "label": filename or safe_name,
        "original_name": filename or safe_name,
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    _save_asset_meta(server_root, patient_id, meta)
    return {
        "url": f"/hospice-media/dignity_videos/assets/{patient_id}/{safe_name}",
        "type": media_type,
        "label": filename or safe_name,
        "file_name": filename or safe_name,
        "size": size,
        "selected": True,
    }


def _asset_path_from_url(server_root: Path, device_id: str, url: str) -> tuple[str, Path]:
    patient_id = _safe_key(device_id)
    prefix = f"/hospice-media/dignity_videos/assets/{patient_id}/"
    if not url.startswith(prefix):
        raise ValueError("invalid asset url")
    filename = Path(url.replace(prefix, "", 1)).name
    if not filename:
        raise ValueError("invalid asset filename")
    path = (_asset_dir(server_root, patient_id) / filename).resolve()
    root = _asset_dir(server_root, patient_id).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise ValueError("invalid asset path") from exc
    return patient_id, path


def _delete_video_asset(server_root: Path, device_id: str, url: str) -> bool:
    patient_id, path = _asset_path_from_url(server_root, device_id, url)
    existed = path.exists()
    if existed:
        path.unlink()
    meta = _load_asset_meta(server_root, patient_id)
    if path.name in meta:
        meta.pop(path.name, None)
        _save_asset_meta(server_root, patient_id, meta)
    return existed


def _update_video_asset_label(server_root: Path, device_id: str, url: str, label: str) -> dict:
    patient_id, path = _asset_path_from_url(server_root, device_id, url)
    if not path.exists():
        raise FileNotFoundError("asset not found")
    meta = _load_asset_meta(server_root, patient_id)
    current = meta.get(path.name, {}) if isinstance(meta.get(path.name), dict) else {}
    current["label"] = label or path.stem
    current["updated_at"] = datetime.now().isoformat(timespec="seconds")
    meta[path.name] = current
    _save_asset_meta(server_root, patient_id, meta)
    ext = path.suffix.lower()
    return {
        "url": url,
        "type": _asset_media_type(ext),
        "label": current["label"],
        "file_name": path.name,
        "selected": True,
    }


def _asset_media_type(ext: str) -> str:
    if ext in VIDEO_EXTS:
        return "video"
    if ext in AUDIO_EXTS:
        return "audio"
    return "image"
