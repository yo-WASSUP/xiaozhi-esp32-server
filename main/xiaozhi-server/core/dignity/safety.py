from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any, Dict, Optional


RISK_LEVEL_RANK = {"L0": 0, "L1": 1, "L2": 2, "L3": 3}

_NEGATED_RISK = re.compile(
    r"(?:没有|没想过|从没|从未|并不|不想|不会|否认).{0,6}"
    r"(?:自杀|轻生|想死|去死|结束生命|伤害自己)"
)

_RULES = (
    (
        "L3",
        "self_harm",
        (
            r"(?:现在|马上|这就|立刻|今晚|今天).{0,8}(?:想死|要去死|要自杀|准备自杀|打算自杀|结束生命|跳楼|割腕)",
            r"(?:现在|马上|这就|立刻|今晚|今天).{0,8}(?:要|想|准备|打算|去).{0,6}(?:自杀|轻生|想死|去死|结束生命|跳楼|割腕)",
            r"(?:已经|刚刚).{0,8}(?:吞了|吃了).{0,8}(?:一把|很多|大量|过量).{0,3}药",
            r"(?:已经|刚刚).{0,8}(?:割腕|跳楼|喝了农药|上了楼顶|打开煤气)",
            r"(?:刀|绳子|农药|煤气|安眠药).{0,10}(?:准备好了|就在手边|已经拿到|已经买好)",
        ),
        "检测到当前或近期自伤意图、行为或可用手段",
    ),
    (
        "L3",
        "medical_emergency",
        (
            r"(?:现在|突然).{0,6}(?:喘不过气|无法呼吸|胸口剧痛|大量出血|大出血)",
            r"(?:有人|家里人).{0,5}(?:正在|马上要).{0,5}(?:打我|伤害我|杀我)",
        ),
        "检测到可能需要立即人工处置的安全事件",
    ),
    (
        "L2",
        "self_harm",
        (
            r"(?:我)?(?:想|要|打算|准备).{0,5}(?:自杀|轻生|去死|结束生命|割腕|跳楼)",
            r"(?:我)?(?:想死|想去死|想轻生)",
            r"(?:不想活了|活不下去了|让我死|想结束生命)",
            r"(?:自杀|轻生|割腕|跳楼).{0,8}(?:方法|怎么|念头|计划)",
            r"(?:以前|曾经|之前).{0,8}(?:自杀|轻生|割腕|跳楼|伤害过自己)",
        ),
        "检测到主动自伤想法、方法构想或既往行为",
    ),
    (
        "L2",
        "medical",
        (
            r"(?:疼|痛).{0,5}(?:受不了|忍不住|要命)",
            r"(?:药|治疗).{0,8}(?:全停了|不吃了|不治了)",
        ),
        "检测到严重症状或可能影响安全的医疗决定",
    ),
    (
        "L1",
        "emotional_distress",
        (
            r"(?:活着没意思|死了算了|希望睡着别醒|不如死了)",
            r"(?:我是|觉得自己是).{0,5}(?:累赘|负担|拖累)",
            r"(?:没有希望|一点希望都没有|撑不下去)",
        ),
        "检测到消极死亡愿望或明显绝望情绪",
    ),
)


def assess_safety_risk(
    patient_text: str,
    model_assessment: Optional[Dict[str, Any]] = None,
    strategy: str = "",
) -> Dict[str, Any]:
    """Combine model output with deterministic safety rules.

    Rules provide a predictable fallback. Model L2/L3 results must include an
    evidence fragment found in the patient's text before they can pause a session.
    """

    text = str(patient_text or "").strip()
    searchable = _NEGATED_RISK.sub("", text)
    rule_result = _rule_assessment(searchable)
    model_result = _model_assessment(text, model_assessment)
    result = max(
        (rule_result, model_result),
        key=lambda item: RISK_LEVEL_RANK.get(item["level"], 0),
    )

    if strategy == "handoff_nurse" and result["level"] == "L0":
        result = {
            "level": "L1",
            "category": "other",
            "evidence": text[:80],
            "reason": "访谈模型建议医护人员复核",
            "source": "model_strategy",
        }

    level = result["level"]
    result.update(
        {
            "requires_alert": level != "L0",
            "requires_pause": level in {"L2", "L3"},
            "requires_handoff": level == "L3",
        }
    )
    return result


def build_safety_task(level: str, created_at: Optional[datetime] = None) -> Dict[str, Any]:
    now = created_at or datetime.now()
    task = {
        "status": "pending",
        "created_at": now.isoformat(timespec="seconds"),
    }
    if level == "L1":
        task.update(
            {
                "priority": "review",
                "review_deadline": (now + timedelta(hours=12)).isoformat(timespec="seconds"),
                "recommended_action": "医护人员复核并根据专业判断联系患者",
            }
        )
    elif level == "L2":
        task.update(
            {
                "priority": "urgent",
                "confirm_deadline": (now + timedelta(minutes=10)).isoformat(timespec="seconds"),
                "contact_deadline": (now + timedelta(minutes=30)).isoformat(timespec="seconds"),
                "close_deadline": (now + timedelta(hours=6)).isoformat(timespec="seconds"),
                "recommended_action": "确认患者当前安全状态并完成人工联系",
            }
        )
    else:
        task.update(
            {
                "priority": "emergency",
                "confirm_deadline": now.isoformat(timespec="seconds"),
                "recommended_action": "立即人工接管并核实患者现实安全",
            }
        )
    return task


def safety_reply(assessment: Dict[str, Any]) -> str:
    level = assessment.get("level")
    if level == "L3":
        return "我很担心您现在的安全。我们先暂停访谈，并请医护人员立即来关注您。请您先不要独处，远离可能伤害自己的物品。"
    if level == "L2":
        return "我听到您现在很难受。为了您的安全，我们先暂停访谈，并请医护人员尽快来陪您。"
    if level == "L1":
        return "听起来您现在很难受，谢谢您愿意告诉我。我会把这个情况记录下来，请医护人员关注。您现在感觉安全吗？"
    return ""


def _rule_assessment(text: str) -> Dict[str, Any]:
    for level, category, patterns, reason in _RULES:
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return {
                    "level": level,
                    "category": category,
                    "evidence": match.group(0)[:80],
                    "reason": reason,
                    "source": "rule",
                }
    return _empty_assessment()


def _model_assessment(text: str, raw: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not isinstance(raw, dict):
        return _empty_assessment()
    level = str(raw.get("level") or "L0").upper()
    if level not in RISK_LEVEL_RANK:
        level = "L0"
    evidence = str(raw.get("evidence") or "").strip()[:80]
    if level in {"L2", "L3"} and (not evidence or evidence not in text):
        level = "L1"
    return {
        "level": level,
        "category": str(raw.get("category") or "other")[:40],
        "evidence": evidence,
        "reason": str(raw.get("reason") or "访谈模型检测到需要关注的安全线索")[:160],
        "source": "model",
    }


def _empty_assessment() -> Dict[str, Any]:
    return {
        "level": "L0",
        "category": "none",
        "evidence": "",
        "reason": "未检测到安全风险线索",
        "source": "none",
    }
