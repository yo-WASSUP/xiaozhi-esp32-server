from __future__ import annotations

from typing import Any, Dict, Set


NO_ACTION = "no_action"

ACTION_DEFAULTS: Dict[str, Dict[str, Any]] = {
    "system.idle": {},
    "system.stop": {},
    "system.resume": {},
    "base.forward": {"speed": 0.2, "duration_ms": 800},
    "base.backward": {"speed": 0.2, "duration_ms": 800},
    "base.turn_left": {"angle": 30, "speed": 0.2},
    "base.turn_right": {"angle": 30, "speed": 0.2},
    "base.move": {"speed": 0.2, "duration_ms": 800},
    "arm.wave": {},
    "arm.gentle": {},
    "arm.comfort": {},
    "arm.reset": {},
    "eye.calm": {},
    "eye.warm_smile": {},
    "eye.attentive": {},
    "eye.speak": {},
    "eye.gentle": {},
    "eye.concern": {},
    "aroma.start": {},
    "aroma.stop": {},
    "aroma.scene_relax": {},
    "notify.nurse_alert": {"level": "normal"},
}

VALID_ACTION_IDS: Set[str] = set(ACTION_DEFAULTS)

ACTION_MODULES: Dict[str, str] = {
    action_id: action_id.split(".", 1)[0] for action_id in VALID_ACTION_IDS
}

ACTION_EXAMPLES: Dict[str, tuple[str, ...]] = {
    "system.stop": (
        "停一下",
        "停止",
        "停下",
        "停了",
        "别动",
        "不要动",
        "先别动",
        "暂停",
        "急停",
        "马上停",
    ),
    "system.resume": (
        "继续动作",
        "恢复默认",
        "恢复状态",
        "接着动",
    ),
    "base.forward": (
        "过来一点",
        "靠近一点",
        "离我近一点",
        "往前一点",
        "前进一点",
        "我看不清你",
        "我听不清你",
        "靠我近一点",
    ),
    "base.backward": (
        "后退一点",
        "退后一点",
        "离远一点",
        "往后一点",
        "离我远一点",
        "太近了",
    ),
    "base.turn_left": (
        "左转一下",
        "向左转",
        "看左边",
        "转到左边",
        "往左边看",
    ),
    "base.turn_right": (
        "右转一下",
        "向右转",
        "看右边",
        "转到右边",
        "往右边看",
    ),
    "base.move": (
        "动一下",
        "移动一下",
        "换个位置",
    ),
    "arm.wave": (
        "挥挥手",
        "挥手",
        "招招手",
        "打个招呼",
        "跟我打招呼",
    ),
    "arm.gentle": (
        "轻轻动一下",
        "简单动一下",
        "摆一下手",
    ),
    "arm.comfort": (
        "安慰一下",
        "安抚一下",
        "陪陪我",
        "我有点难过",
    ),
    "arm.reset": (
        "复位",
        "收回来",
        "恢复原位",
        "手收回去",
    ),
    "aroma.start": (
        "打开香薰",
        "开香薰",
        "开启香薰",
        "来点香薰",
    ),
    "aroma.stop": (
        "关闭香薰",
        "关香薰",
        "停香薰",
        "不要香味",
    ),
    "aroma.scene_relax": (
        "放松一下",
        "我有点紧张",
        "让我放松一点",
    ),
    "notify.nurse_alert": (
        "叫护士",
        "找护士",
        "需要护士",
        "帮我叫人",
    ),
}

ACTION_EXAMPLE_HINTS: Set[str] = {
    keyword
    for examples in ACTION_EXAMPLES.values()
    for example in examples
    for keyword in (example, example[:2], example[-2:])
    if len(keyword) >= 2
}


def is_valid_action_id(action_id: str) -> bool:
    return action_id in VALID_ACTION_IDS


def default_params_for(action_id: str) -> Dict[str, Any]:
    return dict(ACTION_DEFAULTS.get(action_id, {}))
