#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
ROS2 机器人控制插件 - 底盘移动
"""

from config.logger import setup_logging
from plugins_func.register import register_function, ToolType, ActionResponse, Action

TAG = __name__
logger = setup_logging()


ROS2_ROBOT_CONTROL_FUNCTION_DESC = {
    "type": "function",
    "function": {
        "name": "ros2_robot_move",
        "description": "控制机器人底盘移动（前进、后退、转向、停止）",
        "parameters": {
            "type": "object",
            "properties": {
                "direction": {
                    "type": "string",
                    "enum": ["前进", "后退", "左转", "右转", "停止"],
                    "description": "移动方向"
                },
                "speed": {
                    "type": "number",
                    "description": "速度0.1-1.0，默认0.5"
                },
                "duration": {
                    "type": "integer",
                    "description": "持续秒数1-10，默认2"
                }
            },
            "required": ["direction"]
        }
    }
}


@register_function(
    name="ros2_robot_move",
    desc=ROS2_ROBOT_CONTROL_FUNCTION_DESC,
    type=ToolType.WAIT
)
def ros2_robot_move(direction: str, speed: float = 0.5, duration: int = 2):
    logger.bind(tag=TAG).info(
        f"机器人控制指令: {direction}, 速度: {speed}, 持续时间: {duration}秒"
    )

    valid_directions = ["前进", "后退", "左转", "右转", "停止"]
    if direction not in valid_directions:
        return ActionResponse(action=Action.RESPONSE, response=f"不支持的移动方向: {direction}")

    if direction == "停止":
        response_msg = "好的，机器人已停止"
    else:
        response_msg = f"好的，机器人正在{direction}，速度{speed}，持续{duration}秒"

    return ActionResponse(action=Action.RESPONSE, response=response_msg)
