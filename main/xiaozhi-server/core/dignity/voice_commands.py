import re
from typing import Any, Dict, Optional


DEFAULT_START_COMMANDS = (
    "进入尊严疗法",
    "开始尊严疗法",
    "开启尊严疗法",
    "进入尊严访谈",
    "开始尊严访谈",
    "开启尊严访谈",
    "进入尊严聊法",
    "开始尊严聊法",
    "开启尊严聊法",
)

DEFAULT_STOP_COMMANDS = (
    "退出尊严疗法",
    "结束尊严疗法",
    "关闭尊严疗法",
    "退出尊严访谈",
    "结束尊严访谈",
    "关闭尊严访谈",
    "停止尊严访谈",
    "结束人生回顾",
    "回到普通聊天",
    "切回普通聊天",
    "返回普通聊天",
)

PREFIXES = ("小暖", "请", "请你", "麻烦", "帮我", "帮忙", "我要", "我想", "现在")
SUFFIXES = ("吧", "一下", "可以吗", "好吗", "模式")
NEGATION_HINTS = ("不要", "别", "不用", "不想", "先别", "暂时不要")

PUNCTUATION_RE = re.compile(
    r"[\s,，。.!！?？、：:；;\"'“”‘’（）()\[\]【】<>《》\-]+"
)


def detect_dignity_voice_command(
    text: str,
    config: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, str]]:
    options = _voice_switch_options(config)
    if not options["enabled"]:
        return None

    normalized = _normalize(text)
    if not normalized or _looks_negated(normalized):
        return None

    stop_match = _match_command(normalized, options["stop_commands"])
    if stop_match:
        return {"action": "stop", "matched_command": stop_match}

    start_match = _match_command(normalized, options["start_commands"])
    if start_match:
        return {"action": "start", "matched_command": start_match}

    return None


def _voice_switch_options(config: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    hospice_config = (config or {}).get("hospice", {}) or {}
    switch_config = hospice_config.get("dignity_voice_switch", {}) or {}

    return {
        "enabled": switch_config.get("enabled", True) is not False,
        "start_commands": _configured_commands(
            switch_config.get("start_commands"),
            DEFAULT_START_COMMANDS,
        ),
        "stop_commands": _configured_commands(
            switch_config.get("stop_commands"),
            DEFAULT_STOP_COMMANDS,
        ),
    }


def _configured_commands(value: Any, defaults: tuple[str, ...]) -> tuple[str, ...]:
    if not isinstance(value, list):
        return defaults

    commands = tuple(
        str(item or "").strip()
        for item in value
        if str(item or "").strip()
    )
    return commands or defaults


def _match_command(text: str, commands: tuple[str, ...]) -> Optional[str]:
    candidate = _strip_affixes(text)
    for command in sorted((_normalize(item) for item in commands), key=len, reverse=True):
        if not command:
            continue
        if candidate == command:
            return command
        if text == command:
            return command
        if text.startswith(command) and _strip_affixes(text[len(command):]) == "":
            return command
    return None


def _strip_affixes(text: str) -> str:
    value = text
    changed = True
    while changed:
        changed = False
        for prefix in sorted(PREFIXES, key=len, reverse=True):
            prefix = _normalize(prefix)
            if prefix and value.startswith(prefix):
                value = value[len(prefix):]
                changed = True
        for suffix in sorted(SUFFIXES, key=len, reverse=True):
            suffix = _normalize(suffix)
            if suffix and value.endswith(suffix):
                value = value[:-len(suffix)]
                changed = True
    return value


def _looks_negated(text: str) -> bool:
    return any(hint in text for hint in NEGATION_HINTS)


def _normalize(text: str) -> str:
    return PUNCTUATION_RE.sub("", str(text or "")).strip()
