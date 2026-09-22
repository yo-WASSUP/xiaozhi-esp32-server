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
    "base.homedock": {},
    "arm.wave": {"side": "right", "repeat": 1, "duration_ms": 1500},
    "arm.gentle": {"side": "both", "repeat": 1, "duration_ms": 1000},
    "arm.comfort": {"side": "both", "repeat": 1, "duration_ms": 2000},
    "arm.reset": {"side": "both", "repeat": 1, "duration_ms": 1000},
    "eye.calm": {},
    "eye.warm_smile": {},
    "eye.attentive": {},
    "eye.speak": {},
    "eye.gentle": {},
    "eye.concern": {},
    "aroma.start": {"type": "1", "duration_ms": 60000},
    "aroma.stop": {},
    "aroma.scene_relax": {"type": "1", "duration_ms": 60000},
    "bed.head.1": {},
    "bed.head.2": {},
    "bed.head.3": {},
    "bed.head.up": {},
    "bed.head.down": {},
    "bed.head.stop": {},
    "bed.head.reset": {},
    "bed.feet.1": {},
    "bed.feet.2": {},
    "bed.feet.3": {},
    "bed.feet.up": {},
    "bed.feet.down": {},
    "bed.feet.stop": {},
    "bed.feet.reset": {},
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
        "往前",
        "往前一点",
        "向前",
        "向前一点",
        "向前走",
        "前进一点",
        "前进",
        "我看不清你",
        "我听不清你",
        "靠我近一点",
    ),
    "base.backward": (
        "后退",
        "后退一点",
        "退后一点",
        "离远一点",
        "往后",
        "往后一点",
        "向后",
        "离我远一点",
        "太近了",
    ),
    "base.turn_left": (
        "左转",
        "左转一下",
        "向左转",
        "往左转",
        "看左边",
        "转到左边",
        "往左边看",
    ),
    "base.turn_right": (
        "右转",
        "右转一下",
        "向右转",
        "往右转",
        "看右边",
        "转到右边",
        "往右边看",
    ),
    "base.move": (
        "导航到",
        "去到",
        "前往",
        "导航去",
    ),
    "base.homedock": (
        "回桩",
        "回充",
        "回充电桩",
        "返回充电桩",
        "回去充电",
    ),
    "arm.wave": (
        "挥挥手",
        "挥手",
        "挥动左手",
        "挥动右手",
        "左手挥动",
        "右手挥动",
        "左右手一起挥动",
        "挥动双手",
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
    "bed.head.1": ("床头1档位", "床头一档", "床头调到一档"),
    "bed.head.2": ("床头2档位", "床头二档", "床头调到二档"),
    "bed.head.3": ("床头3档位", "床头三档", "床头调到三档"),
    "bed.head.up": ("床头升高", "床头上升一点", "床头升高一点", "升高床头"),
    "bed.head.down": ("床头降低", "床头下降一点", "床头降低一点", "降低床头"),
    "bed.head.stop": ("床头停止运动", "床头停一下", "床头保持"),
    "bed.head.reset": ("床头复位", "复位床头"),
    "bed.feet.1": ("床尾1档位", "床尾一档", "床尾调到一档"),
    "bed.feet.2": ("床尾2档位", "床尾二档", "床尾调到二档"),
    "bed.feet.3": ("床尾3档位", "床尾三档", "床尾调到三档"),
    "bed.feet.up": ("床尾升高", "床尾上升一点", "床尾升高一点", "升高床尾"),
    "bed.feet.down": ("床尾降低", "床尾下降一点", "床尾降低一点", "降低床尾"),
    "bed.feet.stop": ("床尾停止运动", "床尾停一下", "床尾保持"),
    "bed.feet.reset": ("床尾复位", "复位床尾"),
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
