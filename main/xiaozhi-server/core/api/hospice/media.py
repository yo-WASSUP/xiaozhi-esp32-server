"""Media upload endpoint for the hospice API."""
import os
import time
import uuid

from aiohttp import web
from config.logger import setup_logging

TAG = __name__
logger = setup_logging()


class HospiceMediaMixin:
    async def handle_upload(self, request):
        """POST /api/hospice/upload  multipart: field 'file'
        返回: { url, file_name, size, duration_ms? }
        保存到 data/hospice_media/，URL 通过 /hospice-media/ 静态路由对外暴露。
        """
        try:
            reader = await request.multipart()
            field = await reader.next()
            if field is None or field.name != "file":
                return web.json_response({"success": False, "error": "missing file field"},
                                         status=400, headers=self._cors_headers())

            # 文件扩展名（从 content-type 或 filename 推断）
            filename = field.filename or ""
            ext = os.path.splitext(filename)[1].lower()
            if not ext:
                ct = (field.headers.get("Content-Type") or "").lower()
                ext = {
                    "audio/webm": ".webm", "audio/ogg": ".ogg", "audio/mpeg": ".mp3",
                    "audio/wav": ".wav", "audio/mp4": ".m4a",
                    "image/jpeg": ".jpg", "image/png": ".png", "image/gif": ".gif",
                    "image/webp": ".webp",
                    "video/mp4": ".mp4", "video/webm": ".webm", "video/quicktime": ".mov",
                    "video/x-matroska": ".mkv", "video/ogg": ".ogv", "video/3gpp": ".3gp",
                }.get(ct.split(";")[0].strip(), ".bin")

            # 大小上限（家属端 / 患者端发送媒体）
            max_mb = int((self.config.get("hospice", {}) or {}).get("upload_max_mb", 50))
            max_bytes = max_mb * 1024 * 1024

            # 时间戳 + 短 uuid 防撞
            ts = time.strftime("%Y%m%d-%H%M%S")
            safe_name = f"{ts}-{uuid.uuid4().hex[:8]}{ext}"
            save_path = os.path.join(self.upload_dir, safe_name)

            size = 0
            too_big = False
            with open(save_path, "wb") as f:
                while True:
                    chunk = await field.read_chunk(64 * 1024)
                    if not chunk:
                        break
                    size += len(chunk)
                    if size > max_bytes:
                        too_big = True
                        break
                    f.write(chunk)

            if too_big:
                try:
                    os.remove(save_path)
                except OSError:
                    pass
                return web.json_response(
                    {"success": False, "error": f"文件过大，最多 {max_mb}MB"},
                    status=413, headers=self._cors_headers(),
                )

            url = f"/hospice-media/{safe_name}"
            logger.bind(tag=TAG).info(f"媒体上传完成: {safe_name} ({size} bytes)")
            return web.json_response(
                {"success": True, "url": url, "file_name": safe_name, "size": size},
                headers=self._cors_headers(),
            )
        except Exception as e:
            logger.bind(tag=TAG).error(f"上传失败: {e}")
            return web.json_response({"success": False, "error": str(e)},
                                     status=500, headers=self._cors_headers())

    # ── 通话信令（WebRTC） ──

