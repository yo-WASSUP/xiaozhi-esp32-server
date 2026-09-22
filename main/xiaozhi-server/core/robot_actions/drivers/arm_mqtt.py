from __future__ import annotations

import json
import threading
import time
from typing import Any, Dict, Optional, Tuple

TAG = __name__


class RobotArmMqttPublisher:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._client = None
        self._config_key: Optional[Tuple[Any, ...]] = None

    def publish(self, config: Dict[str, Any], payload: Dict[str, Any], logger=None) -> None:
        arm_config = _get_arm_config(config)
        if not arm_config.get("enabled", False):
            return

        try:
            with self._lock:
                client = self._ensure_client(arm_config)
                topic = str(arm_config.get("command_topic") or "").strip()
                if not topic:
                    raise ValueError("hospice.robot_arm.command_topic 不能为空")

                qos = int(arm_config.get("qos", 0))
                info = client.publish(
                    topic,
                    json.dumps(payload, ensure_ascii=False),
                    qos=qos,
                    retain=False,
                )
                timeout = float(arm_config.get("publish_timeout_seconds", 2.0))
                info.wait_for_publish(timeout=timeout)
                if not info.is_published():
                    raise TimeoutError(f"发布机械臂 MQTT 超时: topic={topic}")
                if logger:
                    params = json.dumps(
                        payload.get("params") or {},
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    )
                    logger.bind(tag=TAG).debug(
                        f"机械臂 MQTT 发布成功: topic={topic}, "
                        f"action_id={payload.get('action_id', '')}, params={params}"
                    )
        except Exception as exc:
            self._reset_client()
            if logger:
                logger.bind(tag=TAG).warning(f"机械臂 MQTT 发布失败: {exc}")

    def _ensure_client(self, arm_config: Dict[str, Any]):
        config_key = _config_key(arm_config)
        if self._client is not None and self._config_key == config_key:
            if _is_client_connected(self._client):
                return self._client

        self._reset_client()

        try:
            import paho.mqtt.client as mqtt
        except ImportError as exc:
            raise RuntimeError("缺少 paho-mqtt，请先安装 requirements.txt") from exc

        client_id = str(
            arm_config.get("client_id")
            or f"xiaozhi-server-{arm_config.get('device_id', 'robot-arm')}-arm"
        )
        client = mqtt.Client(client_id=client_id)

        username = str(arm_config.get("username") or "")
        password = str(arm_config.get("password") or "")
        if username:
            client.username_pw_set(username, password or None)

        if bool(arm_config.get("tls", False)):
            client.tls_set()

        host = str(arm_config.get("broker_host") or "127.0.0.1")
        port = int(arm_config.get("broker_port") or 1883)
        keepalive = int(arm_config.get("keepalive_seconds", 30))
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
                arm_config.get(
                    "connect_timeout_seconds",
                    arm_config.get("publish_timeout_seconds", 2.0),
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


_publisher = RobotArmMqttPublisher()


def build_arm_command_payload(
    config: Dict[str, Any],
    session_id: str,
    source_event: str,
    *,
    source: str,
    action_id: str,
    params: Dict[str, Any],
    event_time: str = "",
) -> Dict[str, Any]:
    arm_config = _get_arm_config(config)
    return {
        "type": "arm.set",
        "device_id": str(arm_config.get("device_id") or "rk3588-eye-001"),
        "session_id": session_id,
        "source": source,
        "source_event": source_event,
        "event_time": event_time,
        "action_id": action_id,
        "module": "arm",
        "params": params,
    }


def publish_robot_arm_command(
    config: Dict[str, Any],
    payload: Dict[str, Any],
    logger=None,
) -> None:
    _publisher.publish(config, payload, logger=logger)


def is_robot_arm_enabled(config: Dict[str, Any]) -> bool:
    return bool(_get_arm_config(config).get("enabled", False))


def _get_arm_config(config: Dict[str, Any]) -> Dict[str, Any]:
    hospice = config.get("hospice", {}) or {}
    return hospice.get("robot_arm", {}) or {}


def _config_key(arm_config: Dict[str, Any]) -> Tuple[Any, ...]:
    return (
        arm_config.get("broker_host"),
        int(arm_config.get("broker_port") or 1883),
        arm_config.get("client_id"),
        arm_config.get("device_id"),
        arm_config.get("command_topic"),
        arm_config.get("username"),
        bool(arm_config.get("tls", False)),
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
                f"等待机械臂 MQTT 连接就绪超时: host={host}, port={port}"
            )
        time.sleep(min(0.01, remaining))
