#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import subprocess
import json
import os
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
    type=ToolType.NONE
)
def ros2_robot_move(direction: str, speed: float = 0.5, duration: int = 2):
    """
    使用ROS2命令控制Isaac Sim仿真环境中的机器人移动
    
    Args:
        direction: 移动方向（前进、后退、左转、右转、停止）
        speed: 移动速度 (0.1-1.0 m/s)
        duration: 持续时间（秒）
    
    Returns:
        ActionResponse: 包含执行结果的响应对象
    """
    try:
        logger.bind(tag=TAG).info(f"执行机器人控制: {direction}, 速度: {speed}, 持续时间: {duration}秒")
        
        # 根据方向设置速度参数
        linear_x = 0.0
        linear_y = 0.0
        angular_z = 0.0
        
        if direction == "前进":
            linear_x = speed
        elif direction == "后退":
            linear_x = -speed
        elif direction == "左转":
            angular_z = speed
        elif direction == "右转":
            angular_z = -speed
        elif direction == "停止":
            # 所有速度都为0
            pass
        else:
            error_msg = f"不支持的移动方向: {direction}"
            logger.bind(tag=TAG).error(error_msg)
            return ActionResponse(action=Action.RESPONSE, response=error_msg)
        
        # 构建ROS2命令
        twist_msg = {
            'linear': {'x': linear_x, 'y': linear_y, 'z': 0.0},
            'angular': {'x': 0.0, 'y': 0.0, 'z': angular_z}
        }
        
        # 构建ROS2命令（不执行）
        result = _build_ros2_command('/cmd_vel', 'geometry_msgs/msg/Twist', twist_msg)
        
        if result['success']:
            if direction == "停止":
                response_msg = f"请在Ubuntu客户端执行: {result['command']}"
            else:
                response_msg = f"机器人{direction}命令已生成，请在Ubuntu客户端执行:\n{result['command']}"
            
            logger.bind(tag=TAG).info(f"ROS2控制命令构建成功: {result['command']}")
            return ActionResponse(
                action=Action.RESPONSE, 
                response=response_msg,
                result=result
            )
        else:
            error_msg = f"ROS2控制命令构建失败: {result.get('error', '未知错误')}"
            logger.bind(tag=TAG).error(error_msg)
            return ActionResponse(action=Action.RESPONSE, response=error_msg)
            
    except Exception as e:
        error_msg = f"机器人控制异常: {str(e)}"
        logger.bind(tag=TAG).error(error_msg)
        return ActionResponse(action=Action.ERROR, response=error_msg)


def _build_ros2_command(topic: str, msg_type: str, msg_data: dict):
    """
    构建ROS2 topic pub命令（不执行）
    
    Args:
        topic: ROS2话题名称
        msg_type: 消息类型
        msg_data: 消息数据字典
    
    Returns:
        dict: 包含命令字符串的字典
    """
    try:
        # 将消息数据转换为ROS2命令格式
        msg_str = json.dumps(msg_data)
        
        # 构建完整的ROS2命令字符串
        command = f"ros2 topic pub --once {topic} {msg_type} '{msg_str}'"
        
        logger.bind(tag=TAG).info(f"构建ROS2命令: {command}")
        
        return {
            'success': True,
            'command': command,
            'topic': topic,
            'msg_type': msg_type,
            'msg_data': msg_data
        }
            
    except Exception as e:
        error_msg = f"构建ROS2命令时发生异常: {str(e)}"
        logger.bind(tag=TAG).error(error_msg)
        return {
            'success': False,
            'error': error_msg
        }
