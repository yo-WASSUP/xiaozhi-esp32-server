from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

from aiohttp import WSMsgType, web

from providers import (
    BrowserBridge,
    ProviderConfigError,
    create_provider,
    provider_statuses,
)


WEB_ROOT = Path(__file__).resolve().parent
STATIC_ROOT = WEB_ROOT / "static"


async def index(request: web.Request) -> web.FileResponse:
    del request
    return web.FileResponse(STATIC_ROOT / "index.html")


async def health(request: web.Request) -> web.Response:
    del request
    return web.json_response({"status": "ok"})


async def providers(request: web.Request) -> web.Response:
    del request
    return web.json_response({"providers": provider_statuses()})


async def receive_browser_audio(
    websocket: web.WebSocketResponse,
    audio_queue: asyncio.Queue[bytes],
) -> None:
    async for message in websocket:
        if message.type == WSMsgType.BINARY:
            if audio_queue.full():
                try:
                    audio_queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            audio_queue.put_nowait(bytes(message.data))
        elif message.type == WSMsgType.TEXT:
            payload = json.loads(message.data)
            if payload.get("type") == "stop":
                return
        elif message.type in (WSMsgType.CLOSE, WSMsgType.CLOSED, WSMsgType.ERROR):
            return


async def realtime_socket(request: web.Request) -> web.WebSocketResponse:
    websocket = web.WebSocketResponse(
        heartbeat=20,
        max_msg_size=1024 * 1024,
        compress=False,
    )
    await websocket.prepare(request)
    bridge = BrowserBridge(websocket)

    try:
        first_message = await websocket.receive(timeout=15)
        if first_message.type != WSMsgType.TEXT:
            raise ProviderConfigError("连接后必须先发送接口选择")
        payload: dict[str, Any] = json.loads(first_message.data)
        if payload.get("type") != "start":
            raise ProviderConfigError("首条消息必须是 start")
        provider = str(payload.get("provider", ""))
        adapter = create_provider(provider)
        audio_queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=250)

        await bridge.status("connecting")
        browser_task = asyncio.create_task(
            receive_browser_audio(websocket, audio_queue)
        )
        provider_task = asyncio.create_task(adapter.run(audio_queue, bridge))
        tasks = (browser_task, provider_task)
        try:
            done, _ = await asyncio.wait(
                tasks,
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in done:
                task.result()
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
    except asyncio.TimeoutError:
        await bridge.send_json("error", message="等待接口选择超时")
    except (ProviderConfigError, json.JSONDecodeError) as exc:
        await bridge.send_json("error", message=str(exc))
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        await bridge.send_json("error", message=str(exc))
    finally:
        if not websocket.closed:
            await websocket.close()
    return websocket


def create_app() -> web.Application:
    app = web.Application()
    app.router.add_get("/", index)
    app.router.add_get("/health", health)
    app.router.add_get("/api/providers", providers)
    app.router.add_get("/ws", realtime_socket)
    app.router.add_static("/static", STATIC_ROOT, show_index=False)
    return app


def main() -> None:
    host = os.getenv("REALTIME_WEB_HOST", "127.0.0.1")
    port = int(os.getenv("REALTIME_WEB_PORT", "8765"))
    print(f"Realtime Voice Lab: http://{host}:{port}")
    web.run_app(
        create_app(),
        host=host,
        port=port,
        print=None,
        access_log=None,
    )


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n服务已停止")
    except Exception as exc:
        print(f"启动失败: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
