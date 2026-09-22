from __future__ import annotations

import argparse
import json
import signal
import sys
import threading
from datetime import datetime
from typing import Any


DEFAULT_DEVICE_ID = "rk3588-eye-001"
DEFAULT_COMMAND_TOPIC = "robot/rk3588-eye-001/aroma/cmd"
DEFAULT_STATUS_TOPIC = "robot/rk3588-eye-001/aroma/status"

SUPPORTED_AROMA_ACTIONS = {
    "aroma.start",
    "aroma.stop",
    "aroma.scene_relax",
}


class AromaBridge:
    def __init__(self, args: argparse.Namespace) -> None:
        try:
            import paho.mqtt.client as mqtt
        except ImportError as exc:
            raise RuntimeError("缺少 paho-mqtt，请先安装 requirements.txt") from exc

        self.args = args
        self.stop_event = threading.Event()
        self.current_action_id = None
        self.current_params = {}
        self.client = mqtt.Client(client_id=args.client_id)

        if args.username:
            self.client.username_pw_set(args.username, args.password or None)
        if args.tls:
            self.client.tls_set()

        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        self.client.on_disconnect = self.on_disconnect

    def run(self) -> None:
        print(
            f"[aroma-bridge] connecting broker={self.args.broker_host}:{self.args.broker_port} "
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
            print(f"[aroma-bridge] mqtt connect failed: {reason_code}", flush=True)
            return

        client.subscribe(self.args.command_topic, qos=self.args.qos)
        print(f"[aroma-bridge] subscribed {self.args.command_topic}", flush=True)
        self.publish_status()

    def on_disconnect(self, client, userdata, reason_code, properties=None) -> None:
        print(f"[aroma-bridge] disconnected: {reason_code}", flush=True)

    def on_message(self, client, userdata, msg) -> None:
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("payload must be a JSON object")

            action_id = str(payload.get("action_id") or "").strip()
            if not action_id:
                raise ValueError("missing action_id")
            if action_id not in SUPPORTED_AROMA_ACTIONS:
                raise ValueError(f"unsupported aroma action_id: {action_id}")

            params = _normalize_params(action_id, payload.get("params"))
            self.current_action_id = action_id
            self.current_params = params
            received_at = datetime.now().astimezone().strftime("%H:%M:%S")
            print(
                f"[aroma-bridge] received_at={received_at} "
                f"action_id={action_id} "
                f"params={json.dumps(params, ensure_ascii=False)} "
                f"event_time={payload.get('event_time', '')} "
                f"source_event={payload.get('source_event', '')} "
                f"session_id={payload.get('session_id', '')}",
                flush=True,
            )
            self.publish_status()
        except Exception as exc:
            print(f"[aroma-bridge] invalid command: {exc}", flush=True)
            self.publish_status(last_error=str(exc))

    def publish_status(self, last_error: str | None = None) -> None:
        status = {
            "type": "aroma.status",
            "device_id": self.args.device_id,
            "online": True,
            "current_action_id": self.current_action_id,
            "current_params": self.current_params,
            "last_error": last_error,
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        }
        self.client.publish(
            self.args.status_topic,
            json.dumps(status, ensure_ascii=False),
            qos=self.args.qos,
            retain=False,
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="RK3588 aroma action MQTT bridge")
    parser.add_argument("--broker-host", required=True)
    parser.add_argument("--broker-port", type=int, default=1883)
    parser.add_argument("--device-id", default=DEFAULT_DEVICE_ID)
    parser.add_argument("--command-topic", default=DEFAULT_COMMAND_TOPIC)
    parser.add_argument("--status-topic", default=DEFAULT_STATUS_TOPIC)
    parser.add_argument("--client-id", default=f"{DEFAULT_DEVICE_ID}-aroma-bridge")
    parser.add_argument("--username", default="")
    parser.add_argument("--password", default="")
    parser.add_argument("--tls", action="store_true")
    parser.add_argument("--qos", type=int, default=0)
    parser.add_argument("--keepalive", type=int, default=30)
    return parser.parse_args()


def _normalize_params(action_id: str, value: Any) -> dict:
    if action_id == "aroma.stop":
        return {}
    if value is None:
        value = {}
    if not isinstance(value, dict):
        raise ValueError("params must be a JSON object")

    aroma_type = value.get("type", "1")
    if not isinstance(aroma_type, str) or aroma_type not in {"1", "2", "3"}:
        raise ValueError("invalid aroma type: expected one of 1, 2, 3")
    if action_id == "aroma.scene_relax" and aroma_type != "1":
        raise ValueError("invalid aroma type: aroma.scene_relax requires type 1")

    duration_ms = value.get("duration_ms", 60000)
    if isinstance(duration_ms, bool) or not isinstance(duration_ms, int):
        raise ValueError("invalid aroma duration_ms: expected integer")
    if duration_ms <= 0:
        raise ValueError("invalid aroma duration_ms: expected positive integer")

    return {
        "type": aroma_type,
        "duration_ms": min(max(duration_ms, 1000), 1800000),
    }


def _is_success(reason_code: Any) -> bool:
    try:
        return int(reason_code) == 0
    except Exception:
        return str(reason_code).lower() in {"0", "success"}


def main() -> int:
    args = parse_args()
    bridge = AromaBridge(args)

    def stop(signum, frame) -> None:
        print(f"[aroma-bridge] stopping signal={signum}", flush=True)
        bridge.stop_event.set()

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)

    try:
        bridge.run()
        return 0
    except KeyboardInterrupt:
        return 0
    except Exception as exc:
        print(f"[aroma-bridge] fatal: {exc}", file=sys.stderr, flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
