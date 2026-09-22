from __future__ import annotations

from typing import Any, Dict, Mapping, Optional

from core.robot_actions.contract import ACTION_EXAMPLES


DEFAULT_HOTWORD_WEIGHT = 4

_MODULE_CONFIG_KEYS = {
    "arm": "robot_arm",
    "aroma": "robot_aroma",
    "base": "robot_base",
    "bed": "robot_bed",
}

_ALWAYS_EXTRA_HOTWORDS = (
    "停止当前动作",
    "停止机器人",
    "机器人停止",
    "马上停下",
    "恢复默认状态",
    "继续执行",
    "通知护士",
    "呼叫护士",
)

_EXTRA_HOTWORDS_BY_MODULE = {
    "base": ("往前走",),
    "aroma": (
        "停止香薰",
        "一号香薰",
        "二号香薰",
        "三号香薰",
        "开启放松香薰",
    ),
    "bed": ("医疗床",),
}

def build_hardware_vocabulary(
    config: Mapping[str, Any],
    configured_vocabulary: Optional[Mapping[str, int]] = None,
) -> Dict[str, int]:
    """Return ASR hotwords for hardware modules enabled in this connection."""
    hospice = config.get("hospice", {}) or {}
    vocabulary = dict(configured_vocabulary or {})
    if not hospice or not bool(hospice.get("enable_robot_voice_actions", True)):
        return vocabulary
    enabled_modules = {"system", "notify"}
    for phrase in _ALWAYS_EXTRA_HOTWORDS:
        vocabulary[phrase] = max(
            int(vocabulary.get(phrase, 0)),
            DEFAULT_HOTWORD_WEIGHT,
        )
    for module, config_key in _MODULE_CONFIG_KEYS.items():
        module_config = hospice.get(config_key, {}) or {}
        if not bool(module_config.get("enabled", False)):
            continue
        enabled_modules.add(module)
        for phrase in _EXTRA_HOTWORDS_BY_MODULE.get(module, ()):
            vocabulary[phrase] = max(
                int(vocabulary.get(phrase, 0)),
                DEFAULT_HOTWORD_WEIGHT,
            )
    for action_id, examples in ACTION_EXAMPLES.items():
        if action_id.split(".", 1)[0] not in enabled_modules:
            continue
        for phrase in examples:
            vocabulary[phrase] = max(
                int(vocabulary.get(phrase, 0)),
                DEFAULT_HOTWORD_WEIGHT,
            )
    return vocabulary
