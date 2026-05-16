"""
患者端本地语音动作识别。

这些动作不需要进入普通 LLM 对话，识别后直接下发给患者端浏览器执行。
"""
import re
from typing import Optional, Dict, Any


def _normalized(text: str) -> str:
    return re.sub(r"[\s，。！？、,.!?；;：:\"'“”‘’（）()【】\[\]《》<>-]+", "", text or "")


def _has_any(text: str, phrases: tuple[str, ...]) -> bool:
    return any(p in text for p in phrases)


def _extract_contact_name(text: str) -> Optional[str]:
    match = re.search(r"(?:收听|播放|读|念)(?P<name>[\u4e00-\u9fa5A-Za-z0-9_]{1,12})的消息", text)
    if not match:
        return None
    name = match.group("name")
    if name in ("家人", "家属", "家里人", "一下", "新的", "最新"):
        return None
    return name


def detect_patient_action(text: str, call_active: bool = False) -> Optional[Dict[str, Any]]:
    normalized = _normalized(text)
    if not normalized:
        return None

    # 先判拒接，避免“不接电话”误命中“接电话”。
    if _has_any(normalized, ("不接", "拒接", "别接", "不要接", "挂掉来电", "挂了来电")):
        return {"type": "client_action", "action": "reject_call", "text": text}

    if _has_any(normalized, ("接电话", "接听电话", "接一下", "接通", "帮我接", "接起来")):
        return {"type": "client_action", "action": "accept_call", "text": text}

    if _has_any(normalized, ("挂电话", "挂断电话", "结束通话", "挂了电话", "挂掉电话", "挂断", "挂了")):
        return {"type": "client_action", "action": "hangup_call", "text": text}

    if _has_any(normalized, ("停止播放", "别读了", "不要读了", "停一下消息")):
        return {"type": "client_action", "action": "stop_playback", "text": text}

    if _has_any(normalized, ("有几条消息", "几条消息", "谁给我发消息", "有没有消息", "有新消息吗")):
        return {"type": "client_action", "action": "announce_unread", "text": text}

    if (
        _has_any(normalized, ("收听", "播放", "读", "念"))
        and _has_any(normalized, ("家人消息", "家属消息", "消息", "留言"))
    ) or _has_any(normalized, ("有什么消息", "读一下消息", "播放消息")):
        action = {"type": "client_action", "action": "read_family_messages", "text": text}
        contact_name = _extract_contact_name(normalized)
        if contact_name:
            action["contact_name"] = contact_name
        return action

    return None
