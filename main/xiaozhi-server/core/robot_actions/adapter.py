from __future__ import annotations

import asyncio
import json
from datetime import datetime
from typing import Any, Dict, Optional

from core.robot_actions.contract import (
    ACTION_MODULES,
    default_params_for,
    is_valid_action_id,
)


TAG = __name__


def _json_for_log(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


ACTION_ID_TO_EYE_ACTION_ID = {
    "system.idle": "eye.calm",
    "system.stop": "eye.calm",
    "system.resume": "eye.attentive",
    "eye.calm": "eye.calm",
    "eye.warm_smile": "eye.warm_smile",
    "eye.attentive": "eye.attentive",
    "eye.speak": "eye.speak",
    "eye.gentle": "eye.gentle",
    "eye.concern": "eye.concern",
    "arm.comfort": "eye.gentle",
    "notify.nurse_alert": "eye.concern",
}

ACTION_ID_TO_ROBOT_ACTION = {
    "system.idle": "idle",
    "system.stop": "pause",
    "system.resume": "listening",
    "eye.calm": "idle",
    "eye.warm_smile": "happy",
    "eye.attentive": "listening",
    "eye.speak": "listening",
    "eye.gentle": "comfort",
    "eye.concern": "nurse_alert",
    "arm.comfort": "comfort",
    "notify.nurse_alert": "nurse_alert",
}


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
            or action_id == "aroma.stop"
            or action_id in {"bed.head.stop", "bed.feet.stop"}
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
        distance_m = _clamp_number(params.get("distance_m"), 0.05, 0.5)
        if distance_m is not None:
            params["distance_m"] = distance_m
            speed_for_duration = float(params.get("speed") or 0.2)
            params["duration_ms"] = _clamp_int(
                round(distance_m / speed_for_duration * 1000),
                200,
                3000,
            )

    if action_id.startswith("arm."):
        params = request.get("params") or {}
        default_side = str(default_params_for(action_id).get("side") or "both")
        side = str(params.get("side") or default_side).strip()
        if side not in {"left", "right", "both"}:
            side = default_side
        params["side"] = side
        params["repeat"] = _clamp_int(params.get("repeat"), 1, 3) or 1
        params["duration_ms"] = _clamp_int(params.get("duration_ms"), 500, 3000) or 1000

    if action_id.startswith("aroma."):
        params = request.get("params") or {}
        if action_id == "aroma.stop":
            request["params"] = {}
            return ""

        aroma_type = params.get("type", "1")
        if not isinstance(aroma_type, str) or aroma_type not in {"1", "2", "3"}:
            return "invalid aroma type: expected one of 1, 2, 3"
        if action_id == "aroma.scene_relax" and aroma_type != "1":
            return "invalid aroma type: aroma.scene_relax requires type 1"

        duration_ms = params.get("duration_ms", 60000)
        if isinstance(duration_ms, bool) or not isinstance(duration_ms, int):
            return "invalid aroma duration_ms: expected integer"
        if duration_ms <= 0:
            return "invalid aroma duration_ms: expected positive integer"

        params["type"] = aroma_type
        params["duration_ms"] = min(max(duration_ms, 1000), 1800000)

    if action_id.startswith("bed."):
        request["params"] = {}

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
        "event_time": datetime.now().astimezone().isoformat(timespec="seconds"),
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
        "current_stage",
        "strategy",
    ):
        if key in request:
            payload[key] = request[key]

    logger = getattr(conn, "logger", None)
    if logger:
        logger.bind(tag=TAG).opt(colors=True).info(
            f"<bold><light-magenta>机器人动作事件: action_id={payload['action_id']}, "
            f"module={payload['module']}, status={status}, "
            f"source={payload['source']}, source_event={payload['source_event']}, "
            f"params={_json_for_log(payload['params'])}, "
            f"reason={_json_for_log(payload['reason'])}, "
            f"rejected_reason={_json_for_log(payload['rejected_reason'])}"
            f"</light-magenta></bold>"
        )

    websocket = getattr(conn, "websocket", None)
    if websocket:
        await websocket.send(json.dumps(payload, ensure_ascii=False))
    _schedule_robot_eye_publish(conn, payload)
    _schedule_robot_arm_publish(conn, payload)
    _schedule_robot_aroma_publish(conn, payload)
    _schedule_robot_bed_publish(conn, payload)
    _schedule_robot_base_execute(conn, payload)
    return payload


def _schedule_robot_eye_publish(conn, payload: Dict[str, Any]) -> None:
    if payload.get("status") != "accepted":
        return

    original_action_id = str(payload.get("action_id") or "").strip()
    eye_action_id = ACTION_ID_TO_EYE_ACTION_ID.get(original_action_id, "")
    if not eye_action_id:
        return

    robot_action = str(
        payload.get("robot_action") or ACTION_ID_TO_ROBOT_ACTION.get(eye_action_id, eye_action_id)
    ).strip()

    try:
        from core.dignity.robot_eye import (
            build_eye_command_payload,
            is_robot_eye_enabled,
            publish_robot_eye_command,
        )

        config = getattr(conn, "config", {}) or {}
        logger = getattr(conn, "logger", None)
        if not is_robot_eye_enabled(config):
            if logger:
                logger.bind(tag=TAG).info(
                    f"眼睛动作已接受但未启用 robot_eye driver: "
                    f"action_id={eye_action_id}, "
                    f"origin_action_id={original_action_id}, "
                    f"robot_action={robot_action}"
                )
            return

        eye_payload = build_eye_command_payload(
            config,
            str(payload.get("session_id") or getattr(conn, "session_id", "")),
            str(payload.get("source_event") or ""),
            robot_action,
            source=str(payload.get("source") or "system"),
            action_id=eye_action_id,
            module="eye",
            origin_action_id=original_action_id,
            event_time=str(payload.get("event_time") or ""),
        )
        loop = asyncio.get_running_loop()
        loop.create_task(
            asyncio.to_thread(
                publish_robot_eye_command,
                config,
                eye_payload,
                logger,
            )
        )
        if logger:
            origin_detail = (
                f", origin_action_id={original_action_id}"
                if original_action_id != eye_action_id
                else ""
            )
            logger.bind(tag=TAG).debug(
                f"眼睛动作 MQTT 发布已调度: action_id={eye_action_id}"
                f"{origin_detail}, robot_action={robot_action}"
            )
    except Exception as exc:
        logger = getattr(conn, "logger", None)
        if logger:
            logger.bind(tag=TAG).warning(f"机器人眼睛动作 MQTT 发布任务创建失败: {exc}")


def _schedule_robot_arm_publish(conn, payload: Dict[str, Any]) -> None:
    if payload.get("status") != "accepted":
        return

    action_id = str(payload.get("action_id") or "").strip()
    if not action_id.startswith("arm."):
        return

    try:
        from core.robot_actions.drivers.arm_mqtt import (
            build_arm_command_payload,
            is_robot_arm_enabled,
            publish_robot_arm_command,
        )

        config = getattr(conn, "config", {}) or {}
        logger = getattr(conn, "logger", None)
        if not is_robot_arm_enabled(config):
            if logger:
                logger.bind(tag=TAG).info(
                    f"机械臂动作已接受但未启用 robot_arm driver: "
                    f"action_id={action_id}, "
                    f"params={_json_for_log(payload.get('params') or {})}"
                )
            return

        arm_payload = build_arm_command_payload(
            config,
            str(payload.get("session_id") or getattr(conn, "session_id", "")),
            str(payload.get("source_event") or ""),
            source=str(payload.get("source") or "system"),
            action_id=action_id,
            params=payload.get("params") or {},
            event_time=str(payload.get("event_time") or ""),
        )
        loop = asyncio.get_running_loop()
        loop.create_task(
            asyncio.to_thread(
                publish_robot_arm_command,
                config,
                arm_payload,
                logger,
            )
        )
        if logger:
            logger.bind(tag=TAG).debug(
                f"机械臂动作 MQTT 发布已调度: action_id={action_id}, "
                f"params={_json_for_log(arm_payload.get('params') or {})}"
            )
    except Exception as exc:
        logger = getattr(conn, "logger", None)
        if logger:
            logger.bind(tag=TAG).warning(f"机器人机械臂动作 MQTT 发布任务创建失败: {exc}")


def _schedule_robot_aroma_publish(conn, payload: Dict[str, Any]) -> None:
    if payload.get("status") != "accepted":
        return

    original_action_id = str(payload.get("action_id") or "").strip()
    if original_action_id == "system.stop":
        action_id = "aroma.stop"
        params = {}
    elif original_action_id.startswith("aroma."):
        action_id = original_action_id
        params = payload.get("params") or {}
    else:
        return

    try:
        from core.robot_actions.drivers.aroma_mqtt import (
            build_aroma_command_payload,
            is_robot_aroma_enabled,
            publish_robot_aroma_command,
        )

        config = getattr(conn, "config", {}) or {}
        logger = getattr(conn, "logger", None)
        if not is_robot_aroma_enabled(config):
            if logger:
                logger.bind(tag=TAG).info(
                    f"香薰动作已接受但未启用 robot_aroma driver: "
                    f"action_id={action_id}, params={_json_for_log(params)}"
                )
            return

        aroma_payload = build_aroma_command_payload(
            config,
            str(payload.get("session_id") or getattr(conn, "session_id", "")),
            str(payload.get("source_event") or ""),
            source=str(payload.get("source") or "system"),
            action_id=action_id,
            params=params,
            event_time=str(payload.get("event_time") or ""),
        )
        loop = asyncio.get_running_loop()
        loop.create_task(
            asyncio.to_thread(
                publish_robot_aroma_command,
                config,
                aroma_payload,
                logger,
            )
        )
        if logger:
            logger.bind(tag=TAG).debug(
                f"香薰动作 MQTT 发布已调度: action_id={action_id}, "
                f"params={_json_for_log(aroma_payload.get('params') or {})}"
            )
    except Exception as exc:
        logger = getattr(conn, "logger", None)
        if logger:
            logger.bind(tag=TAG).warning(f"机器人香薰动作 MQTT 发布任务创建失败: {exc}")


def _schedule_robot_bed_publish(conn, payload: Dict[str, Any]) -> None:
    if payload.get("status") != "accepted":
        return

    original_action_id = str(payload.get("action_id") or "").strip()
    if original_action_id == "system.stop":
        action_ids = ("bed.head.stop", "bed.feet.stop")
    elif original_action_id.startswith("bed."):
        action_ids = (original_action_id,)
    else:
        return

    try:
        from core.robot_actions.drivers.bed_mqtt import (
            build_bed_command_payload,
            is_robot_bed_enabled,
            publish_robot_bed_command,
        )

        config = getattr(conn, "config", {}) or {}
        logger = getattr(conn, "logger", None)
        if not is_robot_bed_enabled(config):
            if logger:
                logger.bind(tag=TAG).info(
                    f"医疗床动作已接受但未启用 robot_bed driver: "
                    f"action_ids={','.join(action_ids)}"
                )
            return

        loop = asyncio.get_running_loop()
        for action_id in action_ids:
            bed_payload = build_bed_command_payload(
                config,
                str(payload.get("session_id") or getattr(conn, "session_id", "")),
                str(payload.get("source_event") or ""),
                source=str(payload.get("source") or "system"),
                action_id=action_id,
                event_time=str(payload.get("event_time") or ""),
                origin_action_id=(
                    original_action_id if original_action_id != action_id else ""
                ),
            )
            loop.create_task(
                asyncio.to_thread(
                    publish_robot_bed_command,
                    config,
                    bed_payload,
                    logger,
                )
            )
            if logger:
                origin_detail = (
                    f", origin_action_id={original_action_id}"
                    if original_action_id != action_id
                    else ""
                )
                logger.bind(tag=TAG).debug(
                    f"医疗床动作 MQTT 发布已调度: action_id={action_id}{origin_detail}"
                )
    except Exception as exc:
        logger = getattr(conn, "logger", None)
        if logger:
            logger.bind(tag=TAG).warning(f"机器人医疗床动作 MQTT 发布任务创建失败: {exc}")


def _schedule_robot_base_execute(conn, payload: Dict[str, Any]) -> None:
    if payload.get("status") != "accepted":
        return

    action_id = str(payload.get("action_id") or "").strip()
    if not (action_id.startswith("base.") or action_id == "system.stop"):
        return

    try:
        from core.robot_actions.drivers.base_slamware import (
            execute_robot_base_action,
            is_robot_base_enabled,
        )

        config = getattr(conn, "config", {}) or {}
        logger = getattr(conn, "logger", None)
        if not is_robot_base_enabled(config):
            if logger:
                logger.bind(tag=TAG).info(f"底盘动作已接受但未启用 robot_base driver: action_id={action_id}")
            return

        loop = asyncio.get_running_loop()
        loop.create_task(
            asyncio.to_thread(
                _execute_robot_base_action_with_log,
                execute_robot_base_action,
                config,
                payload,
                logger,
            )
        )
    except Exception as exc:
        logger = getattr(conn, "logger", None)
        if logger:
            logger.bind(tag=TAG).warning(f"机器人底盘动作执行任务创建失败: {exc}")


def _execute_robot_base_action_with_log(execute_func, config, payload, logger) -> None:
    try:
        result = execute_func(config, payload, logger=logger)
        if logger:
            logger.bind(tag=TAG).info(
                f"机器人底盘动作执行完成: action_id={result.get('action_id')}, "
                f"status={result.get('status')}, message={result.get('message')}"
            )
    except Exception as exc:
        if logger:
            logger.bind(tag=TAG).warning(
                f"机器人底盘动作执行失败: action_id={payload.get('action_id')}, error={exc}"
            )


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
