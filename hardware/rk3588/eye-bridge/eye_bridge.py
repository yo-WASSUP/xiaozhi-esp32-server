from __future__ import annotations

import argparse
import asyncio
import json
import signal
import sys
import threading
from datetime import datetime
from typing import Any

import paho.mqtt.client as mqtt


DEFAULT_DEVICE_ID = "rk3588-eye-001"
DEFAULT_COMMAND_TOPIC = "robot/rk3588-eye-001/eye/cmd"
DEFAULT_STATUS_TOPIC = "robot/rk3588-eye-001/eye/status"
DEFAULT_RENDERER_WS_HOST = "127.0.0.1"
DEFAULT_RENDERER_WS_PORT = 8765

SUPPORTED_EYE_ACTIONS = {
    "eye.calm",
    "eye.warm_smile",
    "eye.attentive",
    "eye.speak",
    "eye.gentle",
    "eye.concern",
}


class EyeBridge:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.stop_event = threading.Event()
        self.current_action_id = None
        self.last_rendered_action_id = None
        self.renderer_loop = None
        self.renderer_clients = set()
        self.client = mqtt.Client(client_id=args.client_id)

        if args.username:
            self.client.username_pw_set(args.username, args.password or None)
        if args.tls:
            self.client.tls_set()

        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        self.client.on_disconnect = self.on_disconnect

    def run(self) -> None:
        renderer_thread = threading.Thread(
            target=self.run_renderer_server,
            name="eye-renderer-websocket",
            daemon=True,
        )
        renderer_thread.start()

        print(
            f"[eye-bridge] connecting broker={self.args.broker_host}:{self.args.broker_port} "
            f"device_id={self.args.device_id}",
            flush=True,
        )
        self.client.connect(
            self.args.broker_host,
            self.args.broker_port,
            keepalive=self.args.keepalive,
        )
        self.client.loop_start()
        try:
            self.stop_event.wait()
        finally:
            self.client.loop_stop()
            self.client.disconnect()
            self.stop_event.set()

    def on_connect(self, client, userdata, flags, reason_code, properties=None) -> None:
        if not _is_success(reason_code):
            print(f"[eye-bridge] mqtt connect failed: {reason_code}", flush=True)
            return

        client.subscribe(self.args.command_topic, qos=self.args.qos)
        print(f"[eye-bridge] subscribed {self.args.command_topic}", flush=True)
        self.publish_status()

    def on_disconnect(self, client, userdata, reason_code, properties=None) -> None:
        print(f"[eye-bridge] disconnected: {reason_code}", flush=True)

    def on_message(self, client, userdata, msg) -> None:
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("payload must be a JSON object")

            action_id = str(payload.get("action_id") or "").strip()
            if not action_id:
                raise ValueError("missing action_id")
            if action_id not in SUPPORTED_EYE_ACTIONS:
                raise ValueError(f"unsupported eye action_id: {action_id}")

            render_key = action_id
            self.current_action_id = action_id
            is_duplicate = render_key == self.last_rendered_action_id
            received_at = datetime.now().astimezone().strftime("%H:%M:%S")
            print(
                f"[eye-bridge] received_at={received_at} "
                f"action_id={action_id} "
                f"source_event={payload.get('source_event', '')} "
                f"session_id={payload.get('session_id', '')} "
                f"duplicate={str(is_duplicate).lower()}",
                flush=True,
            )
            self.publish_status()
            if is_duplicate:
                return

            self.last_rendered_action_id = render_key
            self.broadcast_renderer_state(
                source_event=str(payload.get("source_event") or ""),
                session_id=str(payload.get("session_id") or ""),
            )
        except Exception as exc:
            print(f"[eye-bridge] invalid command: {exc}", flush=True)
            self.publish_status(last_error=str(exc))
            self.broadcast_renderer_state(last_error=str(exc))

    def publish_status(self, last_error: str | None = None) -> None:
        status = {
            "type": "eye.status",
            "device_id": self.args.device_id,
            "online": True,
            "current_action_id": self.current_action_id,
            "last_error": last_error,
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        }
        self.client.publish(
            self.args.status_topic,
            json.dumps(status, ensure_ascii=False),
            qos=self.args.qos,
            retain=False,
        )

    def run_renderer_server(self) -> None:
        try:
            asyncio.run(self.serve_renderer())
        except Exception as exc:
            print(f"[eye-bridge] renderer websocket fatal: {exc}", file=sys.stderr, flush=True)

    async def serve_renderer(self) -> None:
        import websockets

        self.renderer_loop = asyncio.get_running_loop()
        async with websockets.serve(
            self.on_renderer_connected,
            self.args.renderer_ws_host,
            self.args.renderer_ws_port,
        ):
            print(
                f"[eye-bridge] renderer websocket ws://{self.args.renderer_ws_host}:{self.args.renderer_ws_port}",
                flush=True,
            )
            await asyncio.to_thread(self.stop_event.wait)

    async def on_renderer_connected(self, websocket) -> None:
        self.renderer_clients.add(websocket)
        print("[eye-bridge] renderer connected", flush=True)
        try:
            await self.send_renderer_state(websocket)
            await websocket.wait_closed()
        finally:
            self.renderer_clients.discard(websocket)
            print("[eye-bridge] renderer disconnected", flush=True)

    def broadcast_renderer_state(
        self,
        source_event: str = "",
        session_id: str = "",
        last_error: str | None = None,
    ) -> None:
        if self.renderer_loop is None:
            return

        message = self.renderer_message(source_event, session_id, last_error)
        asyncio.run_coroutine_threadsafe(
            self.broadcast_renderer_message(message),
            self.renderer_loop,
        )

    async def broadcast_renderer_message(self, message: dict) -> None:
        if not self.renderer_clients:
            return

        encoded = json.dumps(message, ensure_ascii=False)
        disconnected = []
        for websocket in list(self.renderer_clients):
            try:
                await websocket.send(encoded)
            except Exception:
                disconnected.append(websocket)

        for websocket in disconnected:
            self.renderer_clients.discard(websocket)

    async def send_renderer_state(self, websocket) -> None:
        await websocket.send(json.dumps(self.renderer_message(), ensure_ascii=False))
        self.last_rendered_action_id = self.current_action_id or "eye.calm"

    def renderer_message(
        self,
        source_event: str = "",
        session_id: str = "",
        last_error: str | None = None,
    ) -> dict:
        return {
            "type": "eye.render",
            "device_id": self.args.device_id,
            "action_id": self.current_action_id or "eye.calm",
            "source_event": source_event,
            "session_id": session_id,
            "last_error": last_error,
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="RK3588 eye expression MQTT bridge")
    parser.add_argument("--broker-host", required=True)
    parser.add_argument("--broker-port", type=int, default=1883)
    parser.add_argument("--device-id", default=DEFAULT_DEVICE_ID)
    parser.add_argument("--command-topic", default=DEFAULT_COMMAND_TOPIC)
    parser.add_argument("--status-topic", default=DEFAULT_STATUS_TOPIC)
    parser.add_argument("--client-id", default=f"{DEFAULT_DEVICE_ID}-bridge")
    parser.add_argument("--username", default="")
    parser.add_argument("--password", default="")
    parser.add_argument("--tls", action="store_true")
    parser.add_argument("--qos", type=int, default=0)
    parser.add_argument("--keepalive", type=int, default=30)
    parser.add_argument("--renderer-ws-host", default=DEFAULT_RENDERER_WS_HOST)
    parser.add_argument("--renderer-ws-port", type=int, default=DEFAULT_RENDERER_WS_PORT)
    return parser.parse_args()


def _is_success(reason_code: Any) -> bool:
    try:
        return int(reason_code) == 0
    except Exception:
        return str(reason_code).lower() in {"0", "success"}


def main() -> int:
    args = parse_args()
    bridge = EyeBridge(args)

    def stop(signum, frame) -> None:
        print(f"[eye-bridge] stopping signal={signum}", flush=True)
        bridge.stop_event.set()

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)

    try:
        bridge.run()
        return 0
    except KeyboardInterrupt:
        return 0
    except Exception as exc:
        print(f"[eye-bridge] fatal: {exc}", file=sys.stderr, flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
