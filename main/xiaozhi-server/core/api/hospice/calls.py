"""WebRTC signaling endpoint for the hospice API."""
import json

from aiohttp import web
from config.logger import setup_logging

TAG = __name__
logger = setup_logging()


class HospiceCallsMixin:
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
        # 用 close code 4001 标记"被新连接顶替"，客户端据此判断不重连
        # （关闭码比 message 帧更可靠——不会被浏览器事件循环顺序搞乱）
        old = room.get(role)
        if old is not None and not old.closed:
            try:
                await old.close(code=4001, message=b"replaced-by-new")
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

