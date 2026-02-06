#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
ROS2 机器人控制插件

功能：通过设备端 MCP 工具 (ros2_execute) 控制 ROS2 机器人
流程：意图识别 → 生成参数 → 调用设备端 MCP → 前端执行 ROS2 命令
"""

import json
import asyncio
from config.logger import setup_logging
from plugins_func.register import register_function, ToolType, ActionResponse, Action

TAG = __name__
logger = setup_logging()


ROS2_ROBOT_CONTROL_FUNCTION_DESC = {
    "type": "function",
    "function": {
        "name": "ros2_robot_move",
        "description": (
            "控制机器人移动，用于控制ROS2机器人在Isaac Sim仿真环境中移动。"
            "当用户说'前进'、'后退'、'左转'、'右转'、'停止'、'机器人前进'、'让机器人动一动'等时调用此函数。"
            "用户说'前进两步'、'走两步'时，direction参数为'前进'，duration参数为2。"
            "用户说'快点前进'时，speed参数设为较高值如0.8。"
            "用户说'慢慢后退'时，direction为'后退'，speed参数设为较低值如0.3。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "direction": {
                    "type": "string",
                    "enum": ["前进", "后退", "左转", "右转", "停止"],
                    "description": "机器人移动方向：前进、后退、左转、右转、停止"
                },
                "speed": {
                    "type": "number",
                    "minimum": 0.1,
                    "maximum": 1.0,
                    "description": "移动速度，范围0.1-1.0 m/s，默认0.5"
                },
                "duration": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 10,
                    "description": "持续时间（秒），范围1-10秒，默认2秒"
                }
            },
            "required": ["direction"]
        }
    }
}


@register_function(
    name="ros2_robot_move",
    desc=ROS2_ROBOT_CONTROL_FUNCTION_DESC,
    type=ToolType.SYSTEM_CTL  # 使用 SYSTEM_CTL 以获取 conn 参数
)
def ros2_robot_move(conn, direction: str, speed: float = 0.5, duration: int = 2):
    """
    通过设备端 MCP 调用前端的 ros2_execute 工具来控制机器人

    Args:
        conn: 连接对象，包含 MCP 客户端
        direction: 移动方向（前进、后退、左转、右转、停止）
        speed: 移动速度 (0.1-1.0 m/s)
        duration: 持续时间（秒）

    Returns:
        ActionResponse: 包含执行结果的响应对象
    """
    try:
        logger.bind(tag=TAG).info(
            f"执行机器人控制: {direction}, 速度: {speed}, 持续时间: {duration}秒"
        )

        # 验证方向参数
        valid_directions = ["前进", "后退", "左转", "右转", "停止"]
        if direction not in valid_directions:
            error_msg = f"不支持的移动方向: {direction}"
            logger.bind(tag=TAG).error(error_msg)
            return ActionResponse(action=Action.RESPONSE, response=error_msg)

        # 检查设备端 MCP 客户端是否可用
        if not hasattr(conn, "mcp_client") or not conn.mcp_client:
            logger.bind(tag=TAG).warning("设备端 MCP 客户端未初始化，无法调用 ros2_execute")
            return ActionResponse(
                action=Action.RESPONSE,
                response="无法控制机器人，请确保客户端支持 MCP"
            )

        # 构建 MCP 工具调用参数
        tool_args = {
            "direction": direction,
            "speed": speed,
            "duration": duration
        }

        # 异步调用设备端 MCP 工具
        try:
            from core.providers.tools.device_mcp.mcp_handler import call_mcp_tool

            # 在事件循环中调用异步函数
            loop = conn.loop if hasattr(conn, 'loop') else asyncio.get_event_loop()

            future = asyncio.run_coroutine_threadsafe(
                call_mcp_tool(conn, conn.mcp_client, "ros2_execute", json.dumps(tool_args)),
                loop
            )

            # 等待结果（设置超时）
            result = future.result(timeout=10)
            logger.bind(tag=TAG).info(f"设备端 MCP 调用成功: {result}")

            # 解析返回结果
            if isinstance(result, str):
                try:
                    result_data = json.loads(result)
                    if result_data.get("action") == "RESPONSE":
                        return ActionResponse(
                            action=Action.RESPONSE,
                            response=result_data.get("response", f"机器人正在{direction}")
                        )
                except json.JSONDecodeError:
                    pass

            # 默认返回简短确认消息
            if direction == "停止":
                response_msg = "好的，机器人已停止"
            else:
                response_msg = f"好的，机器人正在{direction}"

            return ActionResponse(action=Action.RESPONSE, response=response_msg)

        except Exception as e:
            logger.bind(tag=TAG).error(f"调用设备端 MCP 工具失败: {e}")
            return ActionResponse(
                action=Action.RESPONSE,
                response="机器人控制失败，请检查客户端是否支持 ros2_execute 工具"
            )

    except Exception as e:
        error_msg = f"机器人控制异常: {str(e)}"
        logger.bind(tag=TAG).error(error_msg)
        return ActionResponse(action=Action.ERROR, response=error_msg)
