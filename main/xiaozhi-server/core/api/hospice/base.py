"""Shared primitives for the hospice REST API."""
import asyncio
import os

from aiohttp import web

from core.api.hospice.storage import get_session_logger


class MessageBroker:
    """Simple in-memory message fan-out keyed by device_id."""

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


class HospiceBaseMixin:
    def __init__(self, config: dict):
        self.config = config
        self.session_logger = get_session_logger(config)
        self.broker = MessageBroker()
        self.upload_dir = os.path.join("data", "hospice_media")
        self.voice_settings_path = os.path.join("data", "hospice_voice_settings.yaml")
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

