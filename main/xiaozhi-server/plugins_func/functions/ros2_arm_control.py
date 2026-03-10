#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
机械臂和夹爪控制插件
"""

from config.logger import setup_logging
from plugins_func.register import register_function, ToolType, ActionResponse, Action

TAG = __name__
logger = setup_logging()


# ========== 机械臂运动控制 ==========
ARM_MOVE_FUNCTION_DESC = {
    "type": "function",
    "function": {
        "name": "robot_arm_move",
        "description": "控制机械臂运动（移动、挥手、指向、复位）",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["移动", "挥手", "指向", "复位"],
                    "description": "动作类型"
                },
                "position": {
                    "type": "string",
                    "enum": ["上", "下", "左", "右", "前", "后"],
                    "description": "目标方位，移动或指向时使用"
                },
                "height": {
                    "type": "number",
                    "description": "手臂高度0.0-1.0，默认0.5"
                },
                "speed": {
                    "type": "number",
                    "description": "速度0.1-1.0，默认0.5"
                }
            },
            "required": ["action"]
        }
    }
}


@register_function(
    name="robot_arm_move",
    desc=ARM_MOVE_FUNCTION_DESC,
    type=ToolType.WAIT
)
def robot_arm_move(action: str, position: str = "前", height: float = 0.5, speed: float = 0.5):
    logger.bind(tag=TAG).info(
        f"机械臂控制: action={action}, position={position}, height={height}, speed={speed}"
    )

    if action == "挥手":
        response_msg = "好的，我来挥挥手打个招呼"
    elif action == "指向":
        response_msg = f"好的，我正在指向{position}方"
    elif action == "复位":
        response_msg = "好的，机械臂已回到初始位置"
    elif action == "移动":
        height_desc = "高" if height > 0.7 else "低" if height < 0.3 else "中等"
        response_msg = f"好的，机械臂正在向{position}移动，高度{height_desc}"
    else:
        response_msg = f"收到，正在执行机械臂动作: {action}"

    return ActionResponse(action=Action.RESPONSE, response=response_msg)


# ========== 夹爪控制 ==========
GRIPPER_FUNCTION_DESC = {
    "type": "function",
    "function": {
        "name": "robot_gripper",
        "description": "控制夹爪开合和抓取释放物体",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["抓取", "释放", "张开", "闭合"],
                    "description": "夹爪动作"
                },
                "force": {
                    "type": "number",
                    "description": "力度0.1-1.0，默认0.5"
                },
                "target": {
                    "type": "string",
                    "description": "目标物体名称"
                }
            },
            "required": ["action"]
        }
    }
}


@register_function(
    name="robot_gripper",
    desc=GRIPPER_FUNCTION_DESC,
    type=ToolType.WAIT
)
def robot_gripper(action: str, force: float = 0.5, target: str = ""):
    logger.bind(tag=TAG).info(
        f"夹爪控制: action={action}, force={force}, target={target}"
    )

    target_str = f"{target}" if target else "物体"

    if action == "抓取":
        force_desc = "轻轻" if force < 0.3 else "用力" if force > 0.7 else ""
        response_msg = f"好的，正在{force_desc}抓取{target_str}"
    elif action == "释放":
        response_msg = f"好的，已松开{target_str}"
    elif action == "张开":
        response_msg = "好的，夹爪已张开"
    elif action == "闭合":
        response_msg = "好的，夹爪已闭合"
    else:
        response_msg = f"收到，正在执行夹爪动作: {action}"

    return ActionResponse(action=Action.RESPONSE, response=response_msg)
