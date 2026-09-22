from __future__ import annotations

import re
from typing import Any, Dict, Optional

from core.robot_actions.contract import (
    ACTION_EXAMPLES,
    default_params_for,
    is_valid_action_id,
)


HARD_RULES = {
    "bed.head.stop": ("床头停止", "床头停一下", "床头保持"),
    "bed.feet.stop": ("床尾停止", "床尾停一下", "床尾保持"),
    "system.stop": ("停一下", "停止", "停下", "别动", "不要动", "急停", "马上停"),
}

ACTOR_PREFIXES = ("机器人", "安安")
HIGH_CONFIDENCE_NAVIGATION_PREFIXES = ("导航到", "导航去", "去到", "前往", "带我去", "送我去")
ACTOR_SCOPED_NAVIGATION_PREFIXES = ("去",)
GENERIC_NAVIGATION_TARGETS = {"那里", "那边", "这里", "这边", "前面", "后面"}


async def classify_robot_action(conn, text: str) -> Optional[Dict[str, Any]]:
    clean_text = _clean_text(text)
    if not clean_text:
        return None

    rule_result = classify_robot_action_by_rule(clean_text)
    if rule_result:
        return _with_extracted_params(rule_result, clean_text)
    return None


def classify_robot_action_by_rule(text: str) -> Optional[Dict[str, Any]]:
    clean_text = _clean_text(text)
    if not clean_text:
        return None

    aroma_action = _parse_aroma_command(clean_text)
    if aroma_action:
        return aroma_action

    for action_id, phrases in HARD_RULES.items():
        if any(phrase in clean_text for phrase in phrases):
            return _with_extracted_params({
                "action_id": action_id,
                "source": "voice_hard_rule",
                "reason": f"硬安全规则命中: {action_id}",
                "params": {},
            }, clean_text)

    navigation_target = _parse_navigation_target(clean_text)
    if navigation_target:
        return _matched_result(
            "base.move",
            "voice_navigation_rule",
            f"导航目标命中: {navigation_target}",
            {"target_name": navigation_target},
        )

    matched_action = None
    matched_length = 0
    for action_id, examples in ACTION_EXAMPLES.items():
        # 香薰完整指令由专用规则解析，避免非法时长或否定句命中短语后开启。
        if action_id.startswith("aroma."):
            continue
        for example in examples:
            clean_example = _clean_text(example)
            # 完整动作短语优先，避免“床头复位”先命中机械臂的“复位”。
            if len(clean_example) > matched_length and clean_example in clean_text:
                matched_action = _matched_result(
                    action_id, "voice_example", f"样例命中: {example}"
                )
                matched_length = len(clean_example)

    return _with_extracted_params(matched_action, clean_text)


def _parse_aroma_command(text: str) -> Optional[Dict[str, Any]]:
    text = text.replace("香熏", "香薰")
    start = re.fullmatch(
        r"(?:开启|打开|开)(?:([一二三123])号)?香薰"
        r"(?:(\d+|[零〇一二两三四五六七八九十百]+)分钟)?",
        text,
    )
    if start:
        params = {}
        if start.group(1):
            params["type"] = start.group(1).translate(str.maketrans("一二三", "123"))
        if start.group(2):
            duration = start.group(2)
            minutes = int(duration) if duration.isdecimal() else _parse_chinese_int(duration)
            if minutes is None:
                return None
            params["duration_ms"] = minutes * 60000
        return _matched_result("aroma.start", "voice_aroma_rule", "香薰开启指令", params)

    if re.fullmatch(r"(?:关闭|关掉|关|停止|停)(?:所有)?香薰", text):
        return _matched_result("aroma.stop", "voice_aroma_rule", "香薰关闭指令")

    if text in {"安抚", "睡前", "紧张", "开启放松香薰"}:
        return _matched_result("aroma.scene_relax", "voice_aroma_rule", "香薰放松场景")
    for action_id in ("aroma.start", "aroma.stop", "aroma.scene_relax"):
        if text in ACTION_EXAMPLES[action_id]:
            return _matched_result(action_id, "voice_aroma_rule", f"香薰指令: {text}")
    return None


def _matched_result(
    action_id: str,
    source: str,
    reason: str,
    params: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return {
        "action_id": action_id,
        "source": source,
        "reason": reason,
        "params": params or {},
    }


def _with_extracted_params(
    action: Optional[Dict[str, Any]],
    text: str,
) -> Optional[Dict[str, Any]]:
    if not action:
        return None

    action_id = str(action.get("action_id") or "")
    params = dict(action.get("params") or {})

    if action_id in {"base.forward", "base.backward"}:
        distance_m = _extract_distance_m(text)
        if distance_m is not None:
            params["distance_m"] = distance_m
    elif action_id in {"base.turn_left", "base.turn_right"}:
        angle = _extract_angle_deg(text)
        if angle is not None:
            params["angle"] = angle
    elif action_id == "base.move":
        target_name = _extract_navigation_target(text)
        if target_name:
            params["target_name"] = target_name
    elif action_id.startswith("arm."):
        params["side"] = _extract_arm_side(text, action_id)

    action["params"] = params
    return action


def _extract_arm_side(text: str, action_id: str) -> str:
    has_left = "左" in text
    has_right = "右" in text
    if has_left and not has_right:
        return "left"
    if has_right and not has_left:
        return "right"
    if has_left and has_right:
        return "both"
    return str(default_params_for(action_id).get("side") or "both")


def _extract_distance_m(text: str) -> Optional[float]:
    match = re.search(r"(\d+(?:\.\d+)?)(?:\s*)(厘米|公分|cm|米|m)", text, re.IGNORECASE)
    if match:
        try:
            distance = float(match.group(1))
        except ValueError:
            return None
        return distance / 100 if match.group(2).lower() in {"厘米", "公分", "cm"} else distance

    chinese_match = re.search(r"([零〇一二两三四五六七八九十百]+)(厘米|公分|米)", text)
    if not chinese_match:
        return None
    distance = _parse_chinese_int(chinese_match.group(1))
    if distance is None:
        return None
    return distance / 100 if chinese_match.group(2) in {"厘米", "公分"} else float(distance)


def _extract_angle_deg(text: str) -> Optional[int]:
    match = re.search(r"(\d+(?:\.\d+)?)(?:度|°)", text)
    if match:
        try:
            return int(round(float(match.group(1))))
        except ValueError:
            return None

    chinese_match = re.search(r"([零〇一二两三四五六七八九十百]+)(?:度|°)", text)
    if not chinese_match:
        return None
    return _parse_chinese_int(chinese_match.group(1))


def _parse_chinese_int(text: str) -> Optional[int]:
    digits = {
        "零": 0,
        "〇": 0,
        "一": 1,
        "二": 2,
        "两": 2,
        "三": 3,
        "四": 4,
        "五": 5,
        "六": 6,
        "七": 7,
        "八": 8,
        "九": 9,
    }

    def digit_value(value: str, default: Optional[int] = None) -> Optional[int]:
        if value == "":
            return default
        if len(value) == 1:
            return digits.get(value)
        result = 0
        for char in value:
            if char not in digits:
                return None
            result = result * 10 + digits[char]
        return result

    if not text:
        return None
    if "百" in text:
        left, right = text.split("百", 1)
        hundreds = digit_value(left, 1)
        if hundreds is None:
            return None
        rest = _parse_chinese_int(right) if right else 0
        if rest is None:
            return None
        return hundreds * 100 + rest
    if "十" in text:
        left, right = text.split("十", 1)
        tens = digit_value(left, 1)
        ones = digit_value(right, 0)
        if tens is None or ones is None:
            return None
        return tens * 10 + ones
    return digit_value(text)


def _extract_navigation_target(text: str) -> str:
    target = _parse_navigation_target(text)
    if target:
        return target
    for prefix in HIGH_CONFIDENCE_NAVIGATION_PREFIXES:
        if prefix in text:
            target = text.split(prefix, 1)[1].strip()
            return "" if target in GENERIC_NAVIGATION_TARGETS else target
    return ""


def _parse_navigation_target(text: str) -> str:
    stripped_actor_text = ""
    for actor in ACTOR_PREFIXES:
        if text.startswith(actor):
            stripped_actor_text = text[len(actor) :].strip()
            break

    for candidate in (text, stripped_actor_text):
        if not candidate:
            continue
        target = _target_after_prefix(candidate, HIGH_CONFIDENCE_NAVIGATION_PREFIXES)
        if target:
            return target

    if stripped_actor_text:
        target = _target_after_prefix(stripped_actor_text, ACTOR_SCOPED_NAVIGATION_PREFIXES)
        if target:
            return target

    return ""


def _target_after_prefix(text: str, prefixes: tuple[str, ...]) -> str:
    for prefix in prefixes:
        if text.startswith(prefix):
            target = text[len(prefix) :].strip()
            return "" if not target or target in GENERIC_NAVIGATION_TARGETS else target
    return ""


def _clean_text(text: str) -> str:
    return re.sub(r"[，。！？、；：,!?\s]+", "", str(text or "")).strip()
