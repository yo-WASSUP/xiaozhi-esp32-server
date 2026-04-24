"""
安宁疗护 - 家属端 / 患者端 REST API
"""
import asyncio
import json
import os
import time
import uuid
from aiohttp import web
from config.logger import setup_logging
from core.api.hospice.storage import get_session_logger

TAG = __name__
logger = setup_logging()


class MessageBroker:
    """简单的内存消息广播：device_id -> set(asyncio.Queue)
    每条新消息 put 给该 device_id 下所有订阅者（患者端、家属端各自订阅）。
    """

    def __init__(self):
        self._subs: dict[str, set[asyncio.Queue]] = {}

    def subscribe(self, device_id: str) -> asyncio.Queue:
        q = asyncio.Queue()
        self._subs.setdefault(device_id, set()).add(q)
        return q

    def unsubscribe(self, device_id: str, q: asyncio.Queue):
        if device_id in self._subs:
            self._subs[device_id].discard(q)
            if not self._subs[device_id]:
                self._subs.pop(device_id, None)

    def publish(self, device_id: str, event: dict):
        for q in list(self._subs.get(device_id, ())):
            try:
                q.put_nowait(event)
            except Exception:
                pass


class HospiceFamilyHandler:
    """家属端 / 患者端 API"""

    def __init__(self, config: dict):
        self.config = config
        self.session_logger = get_session_logger(config)
        self.broker = MessageBroker()
        self.upload_dir = os.path.join("data", "hospice_media")
        os.makedirs(self.upload_dir, exist_ok=True)
        # 通话信令房间：device_id -> { 'family': ws, 'patient': ws }
        self.call_rooms: dict[str, dict[str, web.WebSocketResponse]] = {}

    def _cors_headers(self):
        return {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS, DELETE",
            "Access-Control-Allow-Headers": "Content-Type",
        }

    async def handle_options(self, request):
        return web.Response(status=200, headers=self._cors_headers())

    # ── 摘要接口 ──

    async def handle_summary_today(self, request):
        device_id = request.query.get("device_id", "default")
        summary = self.session_logger.get_summary_today(device_id)

        if not summary:
            conversations = self.session_logger.get_today_conversations(device_id)
            emotions = self.session_logger.get_today_emotions(device_id)

            patient_msgs = [c for c in conversations if c["role"] == "patient"]

            mood_counts = {}
            for e in emotions:
                mood = e["emotion_mood"]
                mood_counts[mood] = mood_counts.get(mood, 0) + 1

            summary = {
                "date": __import__("datetime").date.today().isoformat(),
                "device_id": device_id,
                "conversation_count": len(conversations),
                "patient_message_count": len(patient_msgs),
                "dominant_mood": max(mood_counts, key=mood_counts.get) if mood_counts else "无数据",
                "mood_distribution": mood_counts,
                "summary": f"今日共进行了 {len(patient_msgs)} 轮对话。" if patient_msgs else "今日暂无对话记录。",
            }

        return web.json_response(summary, headers=self._cors_headers())

    async def handle_summary_history(self, request):
        device_id = request.query.get("device_id", "default")
        limit = int(request.query.get("limit", "30"))
        history = self.session_logger.get_summary_history(device_id, limit)
        return web.json_response(history, headers=self._cors_headers())

    # ── 情绪接口 ──

    async def handle_emotion_today(self, request):
        device_id = request.query.get("device_id", "default")
        emotions = self.session_logger.get_today_emotions(device_id)
        return web.json_response(emotions, headers=self._cors_headers())

    async def handle_emotion_trend(self, request):
        device_id = request.query.get("device_id", "default")
        days = int(request.query.get("days", "7"))
        trend = self.session_logger.get_emotion_trend(device_id, days)
        return web.json_response(trend, headers=self._cors_headers())

    # ── 消息接口 ──

    async def handle_send_message(self, request):
        """POST /api/hospice/message
        body: {device_id, sender_name, sender_role('family'|'patient'), type, content, duration_ms?}
        """
        try:
            data = await request.json()
            device_id = data.get("device_id", "default")
            sender_name = data.get("sender_name", "家属")
            sender_role = data.get("sender_role", "family")
            msg_type = data.get("type", "text")
            content = data.get("content", "")
            duration_ms = data.get("duration_ms")
            file_path = data.get("file_path")
            contact_name = data.get("contact_name")

            row = self.session_logger.save_family_message(
                device_id=device_id,
                sender_name=sender_name,
                message_type=msg_type,
                content=content,
                file_path=file_path,
                sender_role=sender_role,
                duration_ms=duration_ms,
                contact_name=contact_name,
            )

            if row:
                self.broker.publish(device_id, {"event": "message.new", "data": row})

            return web.json_response(
                {"success": True, "message": row},
                headers=self._cors_headers()
            )
        except Exception as e:
            logger.bind(tag=TAG).error(f"发送消息失败: {e}")
            return web.json_response(
                {"success": False, "error": str(e)},
                status=500,
                headers=self._cors_headers()
            )

    async def handle_get_messages(self, request):
        """GET /api/hospice/messages?device_id=xxx&sender_role=family|patient&contact_name=xxx"""
        device_id = request.query.get("device_id", "default")
        limit = int(request.query.get("limit", "50"))
        sender_role = request.query.get("sender_role")
        contact_name = request.query.get("contact_name")
        messages = self.session_logger.get_family_messages(
            device_id, limit, sender_role, contact_name
        )
        return web.json_response(messages, headers=self._cors_headers())

    async def handle_client_config(self, request):
        """GET /api/hospice/config  返回前端需要知道的配置（目前：上传上限）"""
        max_mb = int((self.config.get("hospice", {}) or {}).get("upload_max_mb", 50))
        return web.json_response({"upload_max_mb": max_mb}, headers=self._cors_headers())

    async def handle_get_contacts(self, request):
        """GET /api/hospice/contacts?device_id=xxx
        返回按 contact_name 聚合的联系人列表（含最后一条消息与未读数）。
        """
        device_id = request.query.get("device_id", "default")
        contacts = self.session_logger.get_contacts(device_id)
        return web.json_response(contacts, headers=self._cors_headers())

    async def handle_mark_thread_read(self, request):
        """POST /api/hospice/thread/read?device_id=xxx&contact_name=xxx"""
        try:
            device_id = request.query.get("device_id", "default")
            contact_name = request.query.get("contact_name")
            if not contact_name:
                return web.json_response({"success": False, "error": "contact_name required"},
                                         status=400, headers=self._cors_headers())
            n = self.session_logger.mark_thread_read(device_id, contact_name)
            if n > 0:
                self.broker.publish(device_id, {
                    "event": "message.read",
                    "data": {"contact_name": contact_name, "count": n},
                })
            return web.json_response({"success": True, "count": n}, headers=self._cors_headers())
        except Exception as e:
            return web.json_response({"success": False, "error": str(e)},
                                     status=500, headers=self._cors_headers())

    async def handle_mark_read(self, request):
        """POST /api/hospice/message/{id}/read"""
        try:
            msg_id = int(request.match_info["id"])
            ok = self.session_logger.mark_message_read(msg_id)
            # 广播一条已读通知，对侧可更新 UI
            device_id = request.query.get("device_id")
            if ok and device_id:
                self.broker.publish(device_id, {"event": "message.read", "data": {"id": msg_id}})
            return web.json_response({"success": ok}, headers=self._cors_headers())
        except Exception as e:
            return web.json_response({"success": False, "error": str(e)},
                                     status=400, headers=self._cors_headers())

    async def handle_message_stream(self, request):
        """GET /api/hospice/message/stream?device_id=xxx  (SSE)"""
        device_id = request.query.get("device_id", "default")
        resp = web.StreamResponse(
            status=200,
            reason="OK",
            headers={
                "Content-Type": "text/event-stream",
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
                **self._cors_headers(),
            },
        )
        await resp.prepare(request)

        q = self.broker.subscribe(device_id)
        try:
            # 首帧：握手
            await resp.write(b": connected\n\n")
            while True:
                try:
                    event = await asyncio.wait_for(q.get(), timeout=25.0)
                    payload = f"event: {event['event']}\ndata: {json.dumps(event['data'], ensure_ascii=False, default=str)}\n\n"
                    await resp.write(payload.encode("utf-8"))
                except asyncio.TimeoutError:
                    await resp.write(b": ping\n\n")  # keepalive
        except (asyncio.CancelledError, ConnectionResetError):
            pass
        finally:
            self.broker.unsubscribe(device_id, q)
        return resp

    # ── 文件上传接口 ──

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

    async def handle_call_ws(self, request):
        """GET /api/hospice/call/ws?device_id=xxx&role=family|patient

        纯信令中继：把同一 device_id 房间里一端发来的消息原样转给另一端。
        支持的 type（客户端自定义，服务端不解析业务）：
          call-request / call-accept / call-reject / call-end
          offer / answer / ice
        """
        device_id = request.query.get("device_id", "default")
        role = request.query.get("role", "")
        if role not in ("family", "patient"):
            return web.Response(status=400, text="role must be family or patient")

        ws = web.WebSocketResponse(heartbeat=20)
        await ws.prepare(request)

        room = self.call_rooms.setdefault(device_id, {})
        # 若同角色已有连接，踢掉旧的
        old = room.get(role)
        if old is not None and not old.closed:
            try:
                await old.close()
            except Exception:
                pass
        room[role] = ws

        peer_role = "patient" if role == "family" else "family"
        logger.bind(tag=TAG).info(f"通话信令连接: device={device_id} role={role}")

        try:
            async for msg in ws:
                if msg.type == web.WSMsgType.TEXT:
                    peer = self.call_rooms.get(device_id, {}).get(peer_role)
                    if peer is not None and not peer.closed:
                        try:
                            await peer.send_str(msg.data)
                        except Exception as e:
                            logger.bind(tag=TAG).warning(f"转发信令失败: {e}")
                    else:
                        # 对端不在，返回一个占位提示（避免一端死等）
                        try:
                            await ws.send_str(json.dumps({
                                "type": "peer-absent",
                                "peer_role": peer_role,
                            }))
                        except Exception:
                            pass
                elif msg.type == web.WSMsgType.ERROR:
                    logger.bind(tag=TAG).warning(f"ws error: {ws.exception()}")
                    break
        finally:
            # 清理，并通知对端
            if self.call_rooms.get(device_id, {}).get(role) is ws:
                self.call_rooms[device_id].pop(role, None)
                if not self.call_rooms[device_id]:
                    self.call_rooms.pop(device_id, None)
            peer = self.call_rooms.get(device_id, {}).get(peer_role)
            if peer is not None and not peer.closed:
                try:
                    await peer.send_str(json.dumps({"type": "call-end", "reason": "peer-disconnect"}))
                except Exception:
                    pass
            logger.bind(tag=TAG).info(f"通话信令断开: device={device_id} role={role}")
        return ws

    # ── 对话记录接口 ──

    async def handle_conversations_today(self, request):
        device_id = request.query.get("device_id", "default")
        conversations = self.session_logger.get_today_conversations(device_id)
        return web.json_response(conversations, headers=self._cors_headers())


def register_hospice_routes(app: web.Application, config: dict):
    handler = HospiceFamilyHandler(config)

    routes = [
        web.get("/api/hospice/summary/today", handler.handle_summary_today),
        web.get("/api/hospice/summary/history", handler.handle_summary_history),
        web.get("/api/hospice/emotion/today", handler.handle_emotion_today),
        web.get("/api/hospice/emotion/trend", handler.handle_emotion_trend),
        web.post("/api/hospice/message", handler.handle_send_message),
        web.get("/api/hospice/messages", handler.handle_get_messages),
        web.get("/api/hospice/config", handler.handle_client_config),
        web.get("/api/hospice/contacts", handler.handle_get_contacts),
        web.post("/api/hospice/thread/read", handler.handle_mark_thread_read),
        web.post("/api/hospice/message/{id}/read", handler.handle_mark_read),
        web.get("/api/hospice/message/stream", handler.handle_message_stream),
        web.get("/api/hospice/call/ws", handler.handle_call_ws),
        web.post("/api/hospice/upload", handler.handle_upload),
        web.get("/api/hospice/conversations/today", handler.handle_conversations_today),
        web.options("/api/hospice/{path:.*}", handler.handle_options),
    ]

    app.add_routes(routes)
    logger.bind(tag=TAG).info(f"安宁疗护 API 路由已注册 ({len(routes)} 条)")
