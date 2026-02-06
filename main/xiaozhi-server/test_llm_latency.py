#!/usr/bin/env python3
"""
LLM 延迟测试脚本
测试不同配置下的 LLM 响应时间
"""

import time
import json
import asyncio
from openai import OpenAI

# ============ 配置区域 - 根据你的实际情况修改 ============

# 阿里云通义千问配置
ALIYUN_CONFIG = {
    "name": "阿里云 qwen-flash",
    "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "api_key": "sk-645b09df224e4acc9546a8e2fff39120",  # 替换成你的
    "model": "qwen-flash-2025-07-28",  # 当前使用的模型
}

# 可选：测试其他模型
ALIYUN_TURBO_CONFIG = {
    "name": "阿里云 qwen-turbo",
    "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "api_key": "sk-645b09df224e4acc9546a8e2fff39120",  # 替换成你的
    "model": "qwen-turbo",
}

# ============ 测试用的 Prompt ============

# 简短 prompt
SHORT_PROMPT = "你好"

# 中等 prompt（模拟实际对话）
MEDIUM_PROMPT = """你是小智，说话简洁活泼。回复不超过30字。
当前时间：2024-02-06 16:00，星期四

用户说：你好，今天天气怎么样？"""

# 长 prompt（模拟带函数定义）
LONG_PROMPT = """你可以使用以下工具:
[{"type": "function", "function": {"name": "ros2_robot_move", "description": "控制机器人移动，用于控制ROS2机器人在Isaac Sim仿真环境中移动。当用户说'前进'、'后退'、'左转'、'右转'、'停止'时调用此函数。", "parameters": {"type": "object", "properties": {"direction": {"type": "string", "enum": ["前进", "后退", "左转", "右转", "停止"], "description": "机器人移动方向"}, "speed": {"type": "number", "minimum": 0.1, "maximum": 1.0, "description": "移动速度，默认0.5"}, "duration": {"type": "integer", "minimum": 1, "maximum": 10, "description": "持续时间（秒），默认2秒"}}, "required": ["direction"]}}}]

调用工具时用JSON格式回复:
<tool_call>
{"name": "工具名", "arguments": {"参数": "值"}}
</tool_call>

如不需要调用工具，直接回复用户。回复要简洁。

用户说：机器人前进两步"""


def test_llm_latency(config: dict, prompt: str, prompt_name: str = ""):
    """
    测试单个 LLM 配置的延迟
    """
    print(f"\n{'='*60}")
    print(f"测试: {config['name']}")
    print(f"模型: {config['model']}")
    print(f"Prompt: {prompt_name} ({len(prompt)} 字符)")
    print(f"{'='*60}")

    try:
        client = OpenAI(
            base_url=config["base_url"],
            api_key=config["api_key"],
        )

        messages = [{"role": "user", "content": prompt}]

        # 开始计时
        start_time = time.time()
        first_token_time = None
        full_response = ""
        token_count = 0

        # 流式请求
        stream = client.chat.completions.create(
            model=config["model"],
            messages=messages,
            stream=True,
            max_tokens=100,
        )

        for chunk in stream:
            if first_token_time is None:
                first_token_time = time.time()

            if chunk.choices and chunk.choices[0].delta.content:
                content = chunk.choices[0].delta.content
                full_response += content
                token_count += 1
                print(content, end="", flush=True)

        end_time = time.time()
        print()  # 换行

        # 计算延迟
        first_token_latency = (first_token_time - start_time) * 1000 if first_token_time else 0
        total_latency = (end_time - start_time) * 1000

        print(f"\n--- 结果 ---")
        print(f"首包延迟 (TTFT): {first_token_latency:.0f} ms")
        print(f"总耗时: {total_latency:.0f} ms")
        print(f"Token 数: {token_count}")
        print(f"响应内容: {full_response[:100]}...")

        return {
            "success": True,
            "first_token_ms": first_token_latency,
            "total_ms": total_latency,
            "tokens": token_count,
        }

    except Exception as e:
        print(f"错误: {e}")
        return {"success": False, "error": str(e)}


def run_all_tests():
    """
    运行所有测试
    """
    print("\n" + "="*60)
    print("LLM 延迟测试")
    print("="*60)

    results = []

    # 测试当前使用的模型
    configs_to_test = [
        ALIYUN_CONFIG,
        ALIYUN_TURBO_CONFIG,  # 取消注释以测试
    ]

    prompts_to_test = [
        ("短prompt", SHORT_PROMPT),
        ("中等prompt", MEDIUM_PROMPT),
        ("长prompt(带函数)", LONG_PROMPT),
    ]

    for config in configs_to_test:
        if "你的API密钥" in config["api_key"]:
            print(f"\n跳过 {config['name']}: 请先配置 API 密钥")
            continue

        for prompt_name, prompt in prompts_to_test:
            result = test_llm_latency(config, prompt, prompt_name)
            results.append({
                "config": config["name"],
                "model": config["model"],
                "prompt": prompt_name,
                "prompt_len": len(prompt),
                **result
            })
            time.sleep(1)  # 避免请求过快

    # 打印汇总
    print("\n" + "="*60)
    print("测试汇总")
    print("="*60)
    print(f"{'模型':<20} {'Prompt':<15} {'字符数':<8} {'首包(ms)':<10} {'总耗时(ms)':<10}")
    print("-"*60)
    for r in results:
        if r.get("success"):
            print(f"{r['model']:<20} {r['prompt']:<15} {r['prompt_len']:<8} {r['first_token_ms']:<10.0f} {r['total_ms']:<10.0f}")
        else:
            print(f"{r['model']:<20} {r['prompt']:<15} {r['prompt_len']:<8} {'错误':<10} {r.get('error', '')[:20]}")


if __name__ == "__main__":
    # 快速测试单个配置
    # test_llm_latency(ALIYUN_CONFIG, SHORT_PROMPT, "短prompt")

    # 运行所有测试
    run_all_tests()
