from __future__ import annotations

import json
from typing import Any, Dict, Optional

from core.robot_actions.contract import (
    ACTION_MODULES,
    default_params_for,
    is_valid_action_id,
)


TAG = __name__


async def dispatch_robot_action(
    conn,
    request: Dict[str, Any],
    *,
    source_event: str = "voice_action",
) -> Dict[str, Any]:
    action_id = str(request.get("action_id") or "").strip()
    if not is_valid_action_id(action_id):
        return await _send_result(
            conn,
            request,
            status="rejected",
            rejected_reason=f"unsupported action_id: {action_id}",
            source_event=source_event,
        )

    params = default_params_for(action_id)
    custom_params = request.get("params")
    if isinstance(custom_params, dict):
        params.update(custom_params)

    normalized = {
        "action_id": action_id,
        "module": ACTION_MODULES.get(action_id, ""),
        "source": request.get("source") or "system",
        "reason": request.get("reason") or "",
        "params": params,
    }

    rejected_reason = _safety_rejected_reason(conn, normalized)
    if rejected_reason:
        return await _send_result(
            conn,
            normalized,
            status="rejected",
            rejected_reason=rejected_reason,
            source_event=source_event,
        )

    return await _send_result(
        conn,
        normalized,
        status="accepted",
        rejected_reason="",
        source_event=source_event,
    )


def map_dignity_robot_action(robot_action: str) -> Optional[Dict[str, Any]]:
    mapping = {
        "idle": "eye.calm",
        "listening": "eye.attentive",
        "comfort": "eye.gentle",
        "pause": "system.stop",
        "nurse_alert": "notify.nurse_alert",
        "happy": "eye.warm_smile",
    }
    action_id = mapping.get(str(robot_action or "").strip())
    if not action_id:
        return None
    return {
        "action_id": action_id,
        "source": "dignity_engine",
        "reason": f"尊严疗法 robot_action={robot_action}",
        "params": {},
    }


def _safety_rejected_reason(conn, request: Dict[str, Any]) -> str:
    action_id = request["action_id"]
    if bool(getattr(conn, "robot_emergency_stop", False)):
        if not (
            action_id == "system.stop"
            or action_id.startswith("eye.")
            or action_id == "notify.nurse_alert"
        ):
            return "emergency stop active"

    if action_id.startswith("base."):
        params = request.get("params") or {}
        speed = _clamp_number(params.get("speed"), 0.1, 0.5)
        if speed is not None:
            params["speed"] = speed
        duration = _clamp_int(params.get("duration_ms"), 200, 3000)
        if duration is not None:
            params["duration_ms"] = duration
        angle = _clamp_int(params.get("angle"), 5, 90)
        if angle is not None:
            params["angle"] = angle

    return ""


async def _send_result(
    conn,
    request: Dict[str, Any],
    *,
    status: str,
    rejected_reason: str,
    source_event: str,
) -> Dict[str, Any]:
    payload = {
        "type": "client_action",
        "action": "robot_action",
        "source_event": source_event,
        "session_id": getattr(conn, "session_id", ""),
        "action_id": request.get("action_id", ""),
        "module": request.get("module") or ACTION_MODULES.get(request.get("action_id", ""), ""),
        "source": request.get("source") or "system",
        "reason": request.get("reason") or "",
        "params": request.get("params") or {},
        "status": status,
        "rejected_reason": rejected_reason,
    }
    for key in (
        "robot_action",
        "robot_action_enum",
        "eye_expression",
        "current_stage",
        "strategy",
    ):
        if key in request:
            payload[key] = request[key]

    logger = getattr(conn, "logger", None)
    if logger:
        logger.bind(tag=TAG).info(
            f"机器人动作事件: action_id={payload['action_id']}, status={status}, source={payload['source']}"
        )

    websocket = getattr(conn, "websocket", None)
    if websocket:
        await websocket.send(json.dumps(payload, ensure_ascii=False))
    return payload


def _clamp_number(value: Any, minimum: float, maximum: float) -> Optional[float]:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return min(max(number, minimum), maximum)


def _clamp_int(value: Any, minimum: int, maximum: int) -> Optional[int]:
    if value is None:
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return min(max(number, minimum), maximum)
