"""Summary, emotion, chat, and read-state endpoints for the hospice API."""
import asyncio
import json
from datetime import date

from aiohttp import web
from config.logger import setup_logging
from core.connection import ConnectionHandler
from core.handle.abortHandle import handleAbortMessage

TAG = __name__
logger = setup_logging()


class HospiceMessagesMixin:
    async def handle_summary_today(self, request):
        device_id = request.query.get("device_id", "default")
        summary = self.session_logger.get_summary_today(device_id)

        if not summary:
            summary_date = date.today().isoformat()
            conversations = self.session_logger.get_today_conversations(device_id)
            emotions = self.session_logger.get_today_emotions(device_id)
            is_today = True

            if not conversations:
                latest_date = self.session_logger.get_latest_conversation_date(device_id)
                if latest_date:
                    summary_date = latest_date
                    conversations = self.session_logger.get_conversations_by_date(device_id, latest_date)
                    emotions = self.session_logger.get_emotions_by_date(device_id, latest_date)
                    is_today = latest_date == date.today().isoformat()

            patient_msgs = [c for c in conversations if c["role"] == "patient"]

            mood_counts = {}
            for e in emotions:
                mood = e["emotion_mood"]
                mood_counts[mood] = mood_counts.get(mood, 0) + 1

            summary = {
                "date": summary_date,
                "device_id": device_id,
                "conversation_count": len(conversations),
                "patient_message_count": len(patient_msgs),
                "dominant_mood": max(mood_counts, key=mood_counts.get) if mood_counts else "无数据",
                "mood_distribution": mood_counts,
                "summary": (
                    f"{'今日' if is_today else '最近一次记录'}共进行了 {len(patient_msgs)} 轮对话。"
                    if patient_msgs else "暂无对话记录。"
                ),
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
            family_id = data.get("family_id")
            if family_id and not self.session_logger.get_family_binding(device_id, family_id):
                return web.json_response(
                    {"success": False, "error": "家属绑定已解除，请重新配对"},
                    status=403,
                    headers=self._cors_headers(),
                )

            row = self.session_logger.save_family_message(
                device_id=device_id,
                sender_name=sender_name,
                message_type=msg_type,
                content=content,
                file_path=file_path,
                sender_role=sender_role,
                duration_ms=duration_ms,
                contact_name=contact_name,
                family_id=family_id,
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
        family_id = request.query.get("family_id")
        messages = self.session_logger.get_family_messages(
            device_id, limit, sender_role, contact_name, family_id
        )
        return web.json_response(messages, headers=self._cors_headers())

    async def handle_client_config(self, request):
        """GET /api/hospice/config  返回前端需要知道的配置。"""
        hospice = self.config.get("hospice", {}) or {}
        wakeup = dict(hospice.get("patient_wakeup", {}) or {})
        # Flat hospice config is authoritative so toggling enable_patient_wakeup
        # cannot be shadowed by an older nested patient_wakeup block.
        wakeup["enabled"] = hospice.get("enable_patient_wakeup", wakeup.get("enabled", True))
        wakeup["mode"] = hospice.get("patient_wakeup_mode", wakeup.get("mode", "sherpa_onnx_kws"))
        wakeup["threshold"] = hospice.get("patient_wakeup_threshold", wakeup.get("threshold", 0.50))
        wakeup["sherpa_onnx"] = hospice.get(
            "patient_wakeup_sherpa_onnx",
            wakeup.get("sherpa_onnx", {}) or {},
        ) or {}
        max_mb = int(hospice.get("upload_max_mb", 50))
        return web.json_response(
            {
                "upload_max_mb": max_mb,
                "enable_patient_wakeup": wakeup["enabled"],
                "patient_wakeup": wakeup,
            },
            headers=self._cors_headers(),
        )

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
            family_id = request.query.get("family_id")
            if not contact_name and not family_id:
                return web.json_response({"success": False, "error": "contact_name or family_id required"},
                                         status=400, headers=self._cors_headers())
            n = self.session_logger.mark_thread_read(device_id, contact_name, family_id)
            if n > 0:
                self.broker.publish(device_id, {
                    "event": "message.read",
                    "data": {"contact_name": contact_name, "family_id": family_id, "count": n},
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

    async def handle_conversations_today(self, request):
        device_id = request.query.get("device_id", "default")
        conversations = self.session_logger.get_today_conversations(device_id)
        return web.json_response(conversations, headers=self._cors_headers())

    async def handle_pairing_code(self, request):
        """POST /api/hospice/pairing/code body: {device_id}"""
        try:
            data = await request.json()
            device_id = (data.get("device_id") or "").strip()
            if not device_id:
                return web.json_response({"success": False, "error": "device_id required"},
                                         status=400, headers=self._cors_headers())
            item = self.session_logger.create_pairing_code(device_id)
            if not item:
                raise RuntimeError("create pairing code failed")
            return web.json_response({"success": True, **item}, headers=self._cors_headers())
        except Exception as e:
            return web.json_response({"success": False, "error": str(e)},
                                     status=500, headers=self._cors_headers())

    async def handle_pairing_bind(self, request):
        """POST /api/hospice/pairing/bind body: {code, family_name, relationship?}"""
        try:
            data = await request.json()
            code = "".join(ch for ch in str(data.get("code") or "") if ch.isdigit())
            family_name = (data.get("family_name") or "").strip()
            relationship = (data.get("relationship") or "").strip()
            if len(code) != 6:
                return web.json_response({"success": False, "error": "配对码需要 6 位数字"},
                                         status=400, headers=self._cors_headers())
            if not family_name:
                return web.json_response({"success": False, "error": "请输入家属称呼"},
                                         status=400, headers=self._cors_headers())
            binding = self.session_logger.bind_family(code, family_name, relationship or None)
            if not binding:
                return web.json_response({"success": False, "error": "配对码无效或已过期"},
                                         status=400, headers=self._cors_headers())
            return web.json_response({"success": True, "binding": binding}, headers=self._cors_headers())
        except Exception as e:
            return web.json_response({"success": False, "error": str(e)},
                                     status=500, headers=self._cors_headers())

    async def handle_pairing_families(self, request):
        device_id = request.query.get("device_id", "default")
        rows = self.session_logger.get_family_bindings(device_id)
        return web.json_response({"success": True, "families": rows}, headers=self._cors_headers())

    async def handle_pairing_unbind(self, request):
        """DELETE /api/hospice/pairing/bindings?device_id=xxx&family_id=xxx"""
        try:
            device_id = (request.query.get("device_id") or "").strip()
            family_id = (request.query.get("family_id") or "").strip()
            if not device_id or not family_id:
                try:
                    data = await request.json()
                except Exception:
                    data = {}
                device_id = device_id or (data.get("device_id") or "").strip()
                family_id = family_id or (data.get("family_id") or "").strip()
            if not device_id or not family_id:
                return web.json_response(
                    {"success": False, "error": "device_id and family_id required"},
                    status=400,
                    headers=self._cors_headers(),
                )
            binding = self.session_logger.revoke_family_binding(device_id, family_id)
            if not binding:
                return web.json_response(
                    {"success": False, "error": "绑定不存在或已解除"},
                    status=404,
                    headers=self._cors_headers(),
                )
            self.broker.publish(device_id, {"event": "pairing.revoked", "data": binding})
            return web.json_response({"success": True, "binding": binding}, headers=self._cors_headers())
        except Exception as e:
            return web.json_response({"success": False, "error": str(e)},
                                     status=500, headers=self._cors_headers())

    # ── 生命回顾视频接口 ──

