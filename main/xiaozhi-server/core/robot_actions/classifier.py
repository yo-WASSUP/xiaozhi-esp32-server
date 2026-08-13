from __future__ import annotations

import json
import re
from difflib import SequenceMatcher
from typing import Any, Dict, Optional

from core.robot_actions.contract import (
    ACTION_EXAMPLE_HINTS,
    ACTION_EXAMPLES,
    NO_ACTION,
    is_valid_action_id,
)


TAG = __name__

SYSTEM_PROMPT = """你只负责把用户语音分类为一个机器人动作 action_id。
只能从动作表里选择一个 action_id。
如果不是明确的机器人控制意图，输出 no_action。
不要调用工具，不要解释，不要编造参数。
只输出 JSON：{"action_id":"...","reason":"..."}。"""

ACTION_TABLE = """
可选 action_id:
- system.stop: 停止、别动、暂停
- system.resume: 继续、恢复
- base.forward: 过来一点、靠近一点、往前一点
- base.backward: 后退一点、离远一点
- base.turn_left: 左转、看左边、转向左边
- base.turn_right: 右转、看右边、转向右边
- base.move: 特定底盘动作
- arm.wave: 挥手、打招呼
- arm.gentle: 轻微摆动、简单动作
- arm.comfort: 安抚动作、陪伴、安慰
- arm.reset: 收回来、复位、恢复原位
- eye.calm: 平静
- eye.warm_smile: 微笑、开心
- eye.attentive: 专注倾听
- eye.speak: 说话表情
- eye.gentle: 温和安抚表情
- eye.concern: 关切、风险提醒
- aroma.start: 打开香薰
- aroma.stop: 关闭香薰
- aroma.scene_relax: 放松香薰场景
- notify.nurse_alert: 护士提醒、需要人工介入
- no_action: 不是明确机器人动作控制
"""

CANDIDATE_HINTS = (
    "机器人",
    "安安",
    "动作",
    "动一下",
    "动一动",
    "过来",
    "靠近",
    "离远",
    "后退",
    "左",
    "右",
    "转",
    "停",
    "别动",
    "挥",
    "招呼",
    "复位",
    "收回",
    "香薰",
    "安抚",
    "护士",
)

HARD_RULES = {
    "system.stop": ("停一下", "停止", "停下", "别动", "不要动", "急停", "马上停"),
}


async def classify_robot_action(conn, text: str) -> Optional[Dict[str, Any]]:
    clean_text = _clean_text(text)
    if not clean_text:
        return None

    rule_result = classify_robot_action_by_rule(clean_text)
    if rule_result:
        return rule_result

    if not _looks_like_robot_action(clean_text):
        return None

    return await classify_robot_action_with_llm(conn, clean_text)


def classify_robot_action_by_rule(text: str) -> Optional[Dict[str, Any]]:
    clean_text = _clean_text(text)
    if not clean_text:
        return None

    for action_id, phrases in HARD_RULES.items():
        if any(phrase in clean_text for phrase in phrases):
            return {
                "action_id": action_id,
                "source": "voice_hard_rule",
                "reason": f"硬安全规则命中: {action_id}",
                "params": {},
            }

    for action_id, examples in ACTION_EXAMPLES.items():
        for example in examples:
            clean_example = _clean_text(example)
            if clean_example and (clean_example in clean_text or clean_text in clean_example):
                return _matched_result(action_id, "voice_example", f"样例命中: {example}")

    fuzzy = _best_example_match(clean_text)
    if fuzzy:
        action_id, example, score = fuzzy
        return _matched_result(
            action_id,
            "voice_example_fuzzy",
            f"样例相似命中: {example}, score={score:.2f}",
        )
    return None


async def classify_robot_action_with_llm(conn, text: str) -> Optional[Dict[str, Any]]:
    llm = getattr(conn, "llm", None)
    if llm is None:
        return None

    prompt = f"{ACTION_TABLE}\n用户语音：{text}\n请输出 JSON："

    def call_llm() -> str:
        return llm.response_no_stream(SYSTEM_PROMPT, prompt, temperature=0)

    try:
        loop = getattr(conn, "loop", None)
        executor = getattr(conn, "executor", None)
        if loop and executor:
            content = await loop.run_in_executor(executor, call_llm)
        else:
            content = call_llm()
        data = _loads_json_object(content)
    except Exception as exc:
        logger = getattr(conn, "logger", None)
        if logger:
            logger.bind(tag=TAG).warning(f"机器人动作 LLM 分类失败: {exc}")
        return None

    action_id = str(data.get("action_id") or "").strip()
    if action_id == NO_ACTION:
        return None
    if not is_valid_action_id(action_id):
        return None

    return {
        "action_id": action_id,
        "source": "voice_llm",
        "reason": str(data.get("reason") or "LLM JSON 分类命中").strip(),
        "params": {},
    }


def _looks_like_robot_action(text: str) -> bool:
    return any(hint in text for hint in CANDIDATE_HINTS) or any(
        hint in text for hint in ACTION_EXAMPLE_HINTS
    )


def _best_example_match(text: str) -> Optional[tuple[str, str, float]]:
    best: Optional[tuple[str, str, float]] = None
    for action_id, examples in ACTION_EXAMPLES.items():
        for example in examples:
            clean_example = _clean_text(example)
            if not clean_example:
                continue
            score = SequenceMatcher(None, text, clean_example).ratio()
            if score >= 0.78 and (best is None or score > best[2]):
                best = (action_id, example, score)
    return best


def _matched_result(action_id: str, source: str, reason: str) -> Dict[str, Any]:
    return {
        "action_id": action_id,
        "source": source,
        "reason": reason,
        "params": {},
    }


def _clean_text(text: str) -> str:
    return re.sub(r"\s+", "", str(text or "")).strip()


def _loads_json_object(content: str) -> Dict[str, Any]:
    text = (content or "").strip()
    if not text:
        return {}
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        extracted = _extract_json_object(text)
        if not extracted:
            return {}
        value = json.loads(extracted)
    return value if isinstance(value, dict) else {}


def _extract_json_object(text: str) -> str:
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return ""
    return text[start : end + 1]
