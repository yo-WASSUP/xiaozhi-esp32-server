from __future__ import annotations

import json
import math
import re
import time
from typing import Any, Dict, Optional, Tuple

import requests


DEFAULT_CONFIG = {
    "enabled": False,
    "driver": "slamware",
    "base_url": "http://127.0.0.1:1448",
    "linear_speed_mps": 0.2,
    "max_direct_distance_m": 0.5,
    "max_direct_angle_deg": 30,
    "timeout_sec": 3,
    "poll_interval_sec": 0.2,
    "max_wait_sec": 10,
    "navigation_mode": 0,
    "speed_ratio": 0.3,
    "force_single_floor_mode": True,
    "localization_quality_min": 50,
    "skip_localization_quality_check": True,
}

MAPPING = {
    "endpoints": {
        "capabilities": ("GET", "/api/core/system/v1/capabilities"),
        "power_status": ("GET", "/api/core/system/v1/power/status"),
        "robot_health": ("GET", "/api/core/system/v1/robot/health"),
        "localization_quality": ("GET", "/api/core/slam/v1/localization/quality"),
        "create_action": ("POST", "/api/core/motion/v1/actions"),
        "get_action": ("GET", "/api/core/motion/v1/actions/{action_id}"),
        "stop_current": ("DELETE", "/api/core/motion/v1/actions/:current"),
        "multi_floor_pois": ("GET", "/api/multi-floor/map/v1/pois"),
        "core_pois": ("GET", "/api/core/artifact/v1/pois"),
    },
    "actions": {
        "move_by": "slamtec.agent.actions.MoveByAction",
        "rotate": "slamtec.agent.actions.RotateAction",
        "go_home": "slamtec.agent.actions.GoHomeAction",
        "multi_floor_back_home": "slamtec.agent.actions.MultiFloorBackHomeAction",
        "multi_floor_move": "slamtec.agent.actions.MultiFloorMoveAction",
        "move_to": "slamtec.agent.actions.MoveToAction",
    },
    "direction": {
        "前进": 0,
        "后退": 1,
    },
}

ACTION_STATUS_LABELS = {
    0: "初始化",
    1: "运行中",
    2: "暂停",
    3: "停止中",
    4: "已结束",
}


class BaseDriverError(Exception):
    """User-facing base driver error."""


def is_robot_base_enabled(config: Dict[str, Any]) -> bool:
    return bool(_get_base_config(config).get("enabled", False))


def execute_robot_base_action(
    config: Dict[str, Any],
    payload: Dict[str, Any],
    logger=None,
) -> Dict[str, Any]:
    base_config = _get_base_config(config)
    action_id = str(payload.get("action_id") or "")
    params = payload.get("params") or {}

    if str(base_config.get("driver") or "slamware") != "slamware":
        raise BaseDriverError(f"unsupported robot_base driver: {base_config.get('driver')}")

    if action_id == "system.stop":
        _request_json(base_config, "stop_current", request_label="停止当前底盘动作", logger=logger)
        return _result(payload, "executed", "底盘已停止")

    if action_id == "base.forward":
        _run_safety_checks(base_config, logger=logger)
        driver_payload = _build_move_by_payload(base_config, "前进", params)
    elif action_id == "base.backward":
        _run_safety_checks(base_config, logger=logger)
        driver_payload = _build_move_by_payload(base_config, "后退", params)
    elif action_id == "base.turn_left":
        _run_safety_checks(base_config, logger=logger)
        driver_payload = _build_rotate_payload(base_config, "左转", params)
    elif action_id == "base.turn_right":
        _run_safety_checks(base_config, logger=logger)
        driver_payload = _build_rotate_payload(base_config, "右转", params)
    elif action_id == "base.homedock":
        checks = _run_safety_checks(base_config, require_multi_floor=True, require_localization=True, logger=logger)
        driver_payload = _build_go_home_payload(base_config, checks["multi_floor_enabled"])
    elif action_id == "base.move":
        checks = _run_safety_checks(base_config, require_multi_floor=True, require_localization=True, logger=logger)
        target_name = _normalize_poi_name(params.get("target_name"))
        if not target_name:
            raise BaseDriverError("base.move 需要 params.target_name")
        if checks["multi_floor_enabled"] and not _use_single_floor_mode(base_config):
            driver_payload = _build_multi_floor_move_payload(base_config, target_name)
        else:
            poi = _find_core_poi(base_config, target_name)
            driver_payload = _build_move_to_payload(base_config, poi)
    else:
        raise BaseDriverError(f"unsupported base action_id: {action_id}")

    result_message = _create_action(base_config, driver_payload, logger=logger)
    return _result(payload, "executed", result_message)


def _get_base_config(config: Dict[str, Any]) -> Dict[str, Any]:
    hospice = config.get("hospice", {}) or {}
    robot_base = hospice.get("robot_base", {}) or {}
    merged = DEFAULT_CONFIG.copy()
    if isinstance(robot_base, dict):
        merged.update(robot_base)
    merged["base_url"] = str(merged["base_url"]).rstrip("/")
    return merged


def _result(payload: Dict[str, Any], status: str, message: str) -> Dict[str, Any]:
    return {
        "action_id": payload.get("action_id", ""),
        "module": "base",
        "status": status,
        "message": message,
        "session_id": payload.get("session_id", ""),
        "event_time": payload.get("event_time", ""),
    }


def _request_json(
    config: Dict[str, Any],
    endpoint_name: str,
    *,
    path_params: Optional[Dict[str, Any]] = None,
    payload: Optional[Dict[str, Any]] = None,
    request_label: str = "",
    log_request: bool = True,
    logger=None,
) -> Any:
    method, path = _endpoint(endpoint_name, **(path_params or {}))
    url = config["base_url"] + path
    if log_request and logger:
        logger.bind(tag=__name__).info(
            f"Slamware {request_label or endpoint_name}: {method} {path}"
            + (f"\n参数:\n{json.dumps(payload, ensure_ascii=False, indent=2)}" if payload is not None else "")
        )
    response = requests.request(method, url, json=payload, timeout=float(config["timeout_sec"]))
    if response.status_code >= 400:
        raise BaseDriverError(f"Slamware REST 请求失败: {method} {path} HTTP {response.status_code}")
    if not response.content:
        return None
    content_type = response.headers.get("Content-Type", "")
    if "application/json" in content_type:
        return response.json()
    text = response.text.strip()
    if text.lower() in {"true", "false"}:
        return text.lower() == "true"
    try:
        return int(text)
    except ValueError:
        return text


def _endpoint(name: str, **path_params) -> Tuple[str, str]:
    method, path = MAPPING["endpoints"][name]
    for key, value in path_params.items():
        path = path.replace("{" + key + "}", str(value))
    return method, path


def _run_safety_checks(
    config: Dict[str, Any],
    *,
    require_multi_floor: bool = False,
    require_localization: bool = False,
    logger=None,
) -> Dict[str, bool]:
    capabilities = _request_json(config, "capabilities", request_label="检查能力", logger=logger)
    if not _has_capability(capabilities, "slamware.agent.core"):
        raise BaseDriverError("机器人核心能力未启用，无法执行底盘动作")

    multi_floor_enabled = _has_capability(capabilities, "slamware.agent.multi_floor")
    if require_multi_floor and not multi_floor_enabled and logger:
        logger.bind(tag=__name__).info("Slamware multi-floor 能力未启用，准备使用单楼层 fallback")

    power_status = _ensure_dict(
        _request_json(config, "power_status", request_label="检查电源", logger=logger),
        "无法读取机器人电源状态",
    )
    if power_status.get("powerStage") != "running":
        raise BaseDriverError(f"机器人电源状态异常: {power_status.get('powerStage')}")
    if power_status.get("sleepMode") != "awake":
        raise BaseDriverError(f"机器人当前不在唤醒状态: {power_status.get('sleepMode')}")

    health = _ensure_dict(
        _request_json(config, "robot_health", request_label="检查健康", logger=logger),
        "无法读取机器人健康状态",
    )
    if health.get("hasError") or health.get("hasFatal"):
        raise BaseDriverError("机器人存在错误或致命告警，已拒绝底盘动作")

    if require_localization and not _is_truthy(config.get("skip_localization_quality_check")):
        quality = _request_json(config, "localization_quality", request_label="检查定位", logger=logger)
        quality_min = int(config["localization_quality_min"])
        if not isinstance(quality, (int, float)) or quality < quality_min:
            raise BaseDriverError(f"机器人定位质量过低，当前 {quality}，要求至少 {quality_min}")

    return {"multi_floor_enabled": multi_floor_enabled}


def _build_move_by_payload(config: Dict[str, Any], direction: str, params: Dict[str, Any]) -> Dict[str, Any]:
    duration_ms = _duration_from_params(config, params)
    return {
        "action_name": MAPPING["actions"]["move_by"],
        "options": {
            "direction": MAPPING["direction"][direction],
            "duration": duration_ms,
        },
    }


def _duration_from_params(config: Dict[str, Any], params: Dict[str, Any]) -> int:
    distance_m = _to_float(params.get("distance_m"))
    if distance_m is not None:
        if distance_m <= 0:
            raise BaseDriverError("移动距离必须大于 0")
        max_distance = float(config["max_direct_distance_m"])
        if distance_m > max_distance:
            raise BaseDriverError(f"移动距离超过安全限制 {max_distance} 米")
        speed = float(params.get("speed") or config["linear_speed_mps"])
        if speed <= 0:
            raise BaseDriverError("底盘速度必须大于 0")
        return _clamp_int(round(distance_m / speed * 1000), 200, 3000)
    return _clamp_int(params.get("duration_ms"), 200, 3000)


def _build_rotate_payload(config: Dict[str, Any], turn_direction: str, params: Dict[str, Any]) -> Dict[str, Any]:
    angle_deg = _to_float(params.get("angle"))
    if angle_deg is None:
        angle_deg = 30
    if angle_deg <= 0:
        raise BaseDriverError("旋转角度必须大于 0")
    max_angle = float(config["max_direct_angle_deg"])
    if angle_deg > max_angle:
        raise BaseDriverError(f"旋转角度超过安全限制 {max_angle} 度")
    angle = math.radians(angle_deg)
    if turn_direction == "右转":
        angle = -angle
    return {
        "action_name": MAPPING["actions"]["rotate"],
        "options": {
            "angle": angle,
        },
    }


def _build_go_home_payload(config: Dict[str, Any], multi_floor_enabled: bool) -> Dict[str, Any]:
    action_key = "multi_floor_back_home" if multi_floor_enabled and not _use_single_floor_mode(config) else "go_home"
    return {
        "action_name": MAPPING["actions"][action_key],
        "options": {
            "gohome_options": {
                "flags": "dock",
                "move_options": {
                    "mode": int(config["navigation_mode"]),
                },
            }
        },
    }


def _build_multi_floor_move_payload(config: Dict[str, Any], target_name: str) -> Dict[str, Any]:
    return {
        "action_name": MAPPING["actions"]["multi_floor_move"],
        "options": {
            "target": {"poi_name": target_name},
            "move_options": _build_move_options(config),
        },
    }


def _build_move_to_payload(config: Dict[str, Any], poi: Dict[str, Any]) -> Dict[str, Any]:
    pose = poi["pose"]
    target = {"x": pose["x"], "y": pose["y"]}
    if "yaw" in pose:
        target["z"] = pose["yaw"]
    return {
        "action_name": MAPPING["actions"]["move_to"],
        "options": {
            "target": target,
            "move_options": _build_move_options(config),
        },
    }


def _build_move_options(config: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "mode": int(config["navigation_mode"]),
        "flags": [],
        "speed_ratio": float(config["speed_ratio"]),
    }


def _create_action(config: Dict[str, Any], payload: Dict[str, Any], logger=None) -> str:
    action_info = _request_json(
        config,
        "create_action",
        payload=payload,
        request_label="下发底盘动作",
        logger=logger,
    )
    action_id = action_info.get("action_id") if isinstance(action_info, dict) else None
    if logger:
        logger.bind(tag=__name__).info(f"Slamware 底盘动作已创建: action_id={action_id}")
    if action_id is None:
        return "底盘动作已下发"
    return _wait_for_action(config, int(action_id), logger=logger)


def _wait_for_action(config: Dict[str, Any], action_id: int, logger=None) -> str:
    deadline = time.monotonic() + float(config["max_wait_sec"])
    poll_interval = float(config["poll_interval_sec"])
    last_state = None
    last_state_signature = None
    while time.monotonic() <= deadline:
        action_info = _request_json(
            config,
            "get_action",
            path_params={"action_id": action_id},
            log_request=False,
            logger=logger,
        )
        action_info = _ensure_dict(action_info, "无法读取机器人动作状态")
        state = action_info.get("state", {})
        last_state = state
        state_signature = (state.get("status"), state.get("result"), state.get("reason"))
        if state_signature != last_state_signature and logger:
            logger.bind(tag=__name__).info(
                f"Slamware 底盘动作状态: action_id={action_id}, {_format_action_state(state)}"
            )
            last_state_signature = state_signature
        if state.get("status") == 4:
            result = state.get("result")
            if result == 0:
                return "底盘动作执行成功"
            if result == -2:
                return "底盘动作已取消"
            return f"底盘动作执行失败: {state.get('reason') or '未知原因'}"
        time.sleep(max(0.05, poll_interval))
    return f"底盘动作已下发，但等待结果超时，最后状态: {last_state}"


def _find_core_poi(config: Dict[str, Any], target_name: str) -> Dict[str, Any]:
    normalized_target = _normalize_poi_name(target_name)
    pois = _request_json(config, "core_pois", request_label=f"查询POI({normalized_target})")
    if not isinstance(pois, list):
        raise BaseDriverError("无法读取 POI 列表")
    for poi in pois:
        if _poi_name_matches(poi, normalized_target):
            pose = poi.get("pose") or {}
            if "x" in pose and "y" in pose:
                return poi
    raise BaseDriverError(f"未找到目标点位: {normalized_target or target_name}")


def _poi_name_matches(poi: Dict[str, Any], target_name: str) -> bool:
    metadata = poi.get("metadata") or {}
    target = _normalize_poi_name(target_name)
    names = {
        poi.get("poi_name"),
        poi.get("name"),
        poi.get("id"),
        metadata.get("display_name"),
        metadata.get("poi_name"),
        metadata.get("name"),
    }
    return bool(target) and target in {_normalize_poi_name(name) for name in names if name}


def _normalize_poi_name(value: Any) -> str:
    return re.sub(r"[，。！？、；：,!?\s]+$", "", str(value or "").strip())


def _format_action_state(state: Dict[str, Any]) -> str:
    status = state.get("status")
    result = state.get("result")
    reason = state.get("reason") or ""
    status_text = ACTION_STATUS_LABELS.get(status, f"未知状态({status})")
    result_text = f", result={result}" if result is not None else ""
    reason_text = f", reason={reason}" if reason else ""
    return f"status={status_text}{result_text}{reason_text}"


def _has_capability(capabilities: Any, name: str) -> bool:
    return isinstance(capabilities, list) and any(
        capability.get("name") == name and capability.get("enabled") is True
        for capability in capabilities
    )


def _ensure_dict(data: Any, error_message: str) -> Dict[str, Any]:
    if not isinstance(data, dict):
        raise BaseDriverError(error_message)
    return data


def _is_truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _use_single_floor_mode(config: Dict[str, Any]) -> bool:
    return _is_truthy(config.get("force_single_floor_mode"))


def _to_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _clamp_int(value: Any, minimum: int, maximum: int) -> int:
    try:
        number = int(round(float(value)))
    except (TypeError, ValueError):
        number = minimum
    return min(max(number, minimum), maximum)
