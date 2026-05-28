"""Life review video endpoints for the hospice API."""
import asyncio
from datetime import datetime
from pathlib import Path

from aiohttp import web
from config.logger import setup_logging
from core.dignity.video.renderer import render_video
from core.dignity.video.storage import load_task, new_task_id, save_task
from core.dignity.video.storyboard import build_storyboard

TAG = __name__
logger = setup_logging()


class HospiceVideoMixin:
    async def handle_video_storyboard(self, request):
        """POST /api/hospice/video/storyboard
        body: {device_id, document, memory?, assets?}
        """
        try:
            data = await request.json()
            document = data.get("document") or ""
            memory = data.get("memory") or {}
            assets = data.get("assets") or []
            scenes = build_storyboard(document=document, memory=memory, assets=assets)
            return web.json_response(
                {"success": True, "storyboard": scenes},
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
        """POST /api/hospice/video/render
        body: {device_id, storyboard}
        """
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


