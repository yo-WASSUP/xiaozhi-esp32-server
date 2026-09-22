from __future__ import annotations

import json
import threading
from typing import Any, Dict, Optional, Tuple

TAG = __name__


class RobotAromaMqttPublisher:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._client = None
        self._config_key: Optional[Tuple[Any, ...]] = None

    def publish(self, config: Dict[str, Any], payload: Dict[str, Any], logger=None) -> None:
        aroma_config = _get_aroma_config(config)
        if not aroma_config.get("enabled", False):
            return

        try:
            with self._lock:
                client = self._ensure_client(aroma_config)
                topic = str(aroma_config.get("command_topic") or "").strip()
                if not topic:
                    raise ValueError("hospice.robot_aroma.command_topic 不能为空")

                qos = int(aroma_config.get("qos", 0))
                info = client.publish(
                    topic,
                    json.dumps(payload, ensure_ascii=False),
                    qos=qos,
                    retain=False,
                )
                timeout = float(aroma_config.get("publish_timeout_seconds", 2.0))
                info.wait_for_publish(timeout=timeout)
                if not info.is_published():
                    raise TimeoutError(f"发布香薰 MQTT 超时: topic={topic}")
                if logger:
                    params = json.dumps(
                        payload.get("params") or {},
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    )
                    logger.bind(tag=TAG).debug(
                        f"香薰 MQTT 发布成功: topic={topic}, "
                        f"action_id={payload.get('action_id', '')}, params={params}"
                    )
        except Exception as exc:
            self._reset_client()
            if logger:
                logger.bind(tag=TAG).warning(f"香薰 MQTT 发布失败: {exc}")

    def _ensure_client(self, aroma_config: Dict[str, Any]):
        config_key = _config_key(aroma_config)
        if self._client is not None and self._config_key == config_key:
            return self._client

        self._reset_client()

        try:
            import paho.mqtt.client as mqtt
        except ImportError as exc:
            raise RuntimeError("缺少 paho-mqtt，请先安装 requirements.txt") from exc

        client_id = str(
            aroma_config.get("client_id")
            or f"xiaozhi-server-{aroma_config.get('device_id', 'robot-aroma')}-aroma"
        )
        client = mqtt.Client(client_id=client_id)

        username = str(aroma_config.get("username") or "")
        password = str(aroma_config.get("password") or "")
        if username:
            client.username_pw_set(username, password or None)

        if bool(aroma_config.get("tls", False)):
            client.tls_set()

        host = str(aroma_config.get("broker_host") or "127.0.0.1")
        port = int(aroma_config.get("broker_port") or 1883)
        keepalive = int(aroma_config.get("keepalive_seconds", 30))
        rc = client.connect(host, port, keepalive=keepalive)
        if rc != 0:
            raise ConnectionError(f"连接 MQTT Broker 失败: rc={rc}, host={host}, port={port}")

        client.loop_start()
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


_publisher = RobotAromaMqttPublisher()


def build_aroma_command_payload(
    config: Dict[str, Any],
    session_id: str,
    source_event: str,
    *,
    source: str,
    action_id: str,
    params: Dict[str, Any],
    event_time: str = "",
) -> Dict[str, Any]:
    aroma_config = _get_aroma_config(config)
    return {
        "type": "aroma.set",
        "device_id": str(aroma_config.get("device_id") or "rk3588-eye-001"),
        "session_id": session_id,
        "source": source,
        "source_event": source_event,
        "event_time": event_time,
        "action_id": action_id,
        "module": "aroma",
        "params": params,
    }


def publish_robot_aroma_command(
    config: Dict[str, Any],
    payload: Dict[str, Any],
    logger=None,
) -> None:
    _publisher.publish(config, payload, logger=logger)


def is_robot_aroma_enabled(config: Dict[str, Any]) -> bool:
    return bool(_get_aroma_config(config).get("enabled", False))


def _get_aroma_config(config: Dict[str, Any]) -> Dict[str, Any]:
    hospice = config.get("hospice", {}) or {}
    return hospice.get("robot_aroma", {}) or {}


def _config_key(aroma_config: Dict[str, Any]) -> Tuple[Any, ...]:
    return (
        aroma_config.get("broker_host"),
        int(aroma_config.get("broker_port") or 1883),
        aroma_config.get("client_id"),
        aroma_config.get("device_id"),
        aroma_config.get("command_topic"),
        aroma_config.get("username"),
        bool(aroma_config.get("tls", False)),
    )
