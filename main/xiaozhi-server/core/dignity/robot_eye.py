from __future__ import annotations

import json
import threading
import time
from typing import Any, Dict, Optional, Tuple

TAG = __name__


class RobotEyeMqttPublisher:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._client = None
        self._config_key: Optional[Tuple[Any, ...]] = None

    def publish(self, config: Dict[str, Any], payload: Dict[str, Any], logger=None) -> None:
        eye_config = _get_eye_config(config)
        if not eye_config.get("enabled", False):
            return

        try:
            with self._lock:
                client = self._ensure_client(eye_config)
                topic = str(eye_config.get("command_topic") or "").strip()
                if not topic:
                    raise ValueError("hospice.robot_eye.command_topic 不能为空")

                qos = int(eye_config.get("qos", 0))
                info = client.publish(
                    topic,
                    json.dumps(payload, ensure_ascii=False),
                    qos=qos,
                    retain=False,
                )
                timeout = float(eye_config.get("publish_timeout_seconds", 2.0))
                info.wait_for_publish(timeout=timeout)
                if not info.is_published():
                    raise TimeoutError(f"发布眼睛表情 MQTT 超时: topic={topic}")
                if logger:
                    action_id = str(payload.get("action_id") or "")
                    origin_action_id = str(payload.get("origin_action_id") or "")
                    origin_detail = (
                        f", origin_action_id={origin_action_id}"
                        if origin_action_id and origin_action_id != action_id
                        else ""
                    )
                    logger.bind(tag=TAG).debug(
                        f"眼睛表情 MQTT 发布成功: topic={topic}, "
                        f"action_id={action_id}{origin_detail}, "
                        f"robot_action={payload.get('robot_action', '')}"
                    )
        except Exception as exc:
            self._reset_client()
            if logger:
                logger.bind(tag=TAG).warning(f"眼睛表情 MQTT 发布失败: {exc}")

    def _ensure_client(self, eye_config: Dict[str, Any]):
        config_key = _config_key(eye_config)
        if self._client is not None and self._config_key == config_key:
            if _is_client_connected(self._client):
                return self._client

        self._reset_client()

        try:
            import paho.mqtt.client as mqtt
        except ImportError as exc:
            raise RuntimeError("缺少 paho-mqtt，请先安装 requirements.txt") from exc

        client_id = str(
            eye_config.get("client_id")
            or f"xiaozhi-server-{eye_config.get('device_id', 'robot-eye')}-eye"
        )
        client = mqtt.Client(client_id=client_id)

        username = str(eye_config.get("username") or "")
        password = str(eye_config.get("password") or "")
        if username:
            client.username_pw_set(username, password or None)

        if bool(eye_config.get("tls", False)):
            client.tls_set()

        host = str(eye_config.get("broker_host") or "127.0.0.1")
        port = int(eye_config.get("broker_port") or 1883)
        keepalive = int(eye_config.get("keepalive_seconds", 30))
        loop_started = False
        try:
            rc = client.connect(host, port, keepalive=keepalive)
            if rc != 0:
                raise ConnectionError(
                    f"连接 MQTT Broker 失败: rc={rc}, host={host}, port={port}"
                )

            client.loop_start()
            loop_started = True
            connect_timeout = float(
                eye_config.get(
                    "connect_timeout_seconds",
                    eye_config.get("publish_timeout_seconds", 2.0),
                )
            )
            _wait_until_connected(
                client,
                timeout=max(connect_timeout, 0.01),
                host=host,
                port=port,
            )
        except Exception:
            if loop_started:
                try:
                    client.loop_stop()
                except Exception:
                    pass
            try:
                client.disconnect()
            except Exception:
                pass
            raise

        self._client = client
        self._config_key = config_key
        return client

    def _reset_client(self) -> None:
        client = self._client
        self._client = None
        self._config_key = None
        if client is None:
            return
        try:
            client.loop_stop()
        except Exception:
            pass
        try:
            client.disconnect()
        except Exception:
            pass


_publisher = RobotEyeMqttPublisher()


def build_eye_command_payload(
    config: Dict[str, Any],
    session_id: str,
    source_event: str,
    robot_action: str,
    source: str = "dignity",
    action_id: str = "",
    module: str = "",
    origin_action_id: str = "",
    event_time: str = "",
) -> Dict[str, Any]:
    eye_config = _get_eye_config(config)
    return {
        "type": "eye.set",
        "device_id": str(eye_config.get("device_id") or "rk3588-eye-001"),
        "session_id": session_id,
        "source": source,
        "source_event": source_event,
        "action_id": action_id,
        "module": module,
        "origin_action_id": origin_action_id,
        "event_time": event_time,
        "robot_action": robot_action,
    }


def publish_robot_eye_command(
    config: Dict[str, Any],
    payload: Dict[str, Any],
    logger=None,
) -> None:
    _publisher.publish(config, payload, logger=logger)


def is_robot_eye_enabled(config: Dict[str, Any]) -> bool:
    return bool(_get_eye_config(config).get("enabled", False))


def _get_eye_config(config: Dict[str, Any]) -> Dict[str, Any]:
    hospice = config.get("hospice", {}) or {}
    return hospice.get("robot_eye", {}) or {}


def _config_key(eye_config: Dict[str, Any]) -> Tuple[Any, ...]:
    return (
        eye_config.get("broker_host"),
        int(eye_config.get("broker_port") or 1883),
        eye_config.get("client_id"),
        eye_config.get("device_id"),
        eye_config.get("command_topic"),
        eye_config.get("username"),
        bool(eye_config.get("tls", False)),
    )


def _is_client_connected(client) -> bool:
    try:
        return bool(client.is_connected())
    except Exception:
        return False


def _wait_until_connected(client, *, timeout: float, host: str, port: int) -> None:
    deadline = time.monotonic() + timeout
    while not _is_client_connected(client):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError(
                f"等待眼睛表情 MQTT 连接就绪超时: host={host}, port={port}"
            )
        time.sleep(min(0.01, remaining))
