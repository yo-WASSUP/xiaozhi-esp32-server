from __future__ import annotations

import argparse
import time
from pathlib import Path
from typing import Any, Dict

import yaml
from openai import OpenAI


SERVER_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = SERVER_ROOT / "data" / ".config_hospice.yaml"
DEFAULT_PROVIDER = "DeepSeekLLM"
DEFAULT_PROMPT = "请用一句话回答：1+1等于几？"


def load_provider_config(config_path: Path, provider_name: str) -> Dict[str, Any]:
    with config_path.open("r", encoding="utf-8") as file:
        config = yaml.safe_load(file) or {}

    provider_config = (config.get("LLM") or {}).get(provider_name)
    if not isinstance(provider_config, dict):
        raise RuntimeError(f"未在配置中找到 LLM.{provider_name}")
    if not provider_config.get("api_key"):
        raise RuntimeError(f"LLM.{provider_name} 缺少 api_key")
    if not (provider_config.get("model_name") or provider_config.get("model")):
        raise RuntimeError(f"LLM.{provider_name} 缺少 model_name")
    return provider_config


def apply_thinking_config(request_params: Dict[str, Any], provider_config: Dict[str, Any]) -> None:
    model_name = provider_config.get("model_name") or provider_config.get("model") or ""
    base_url = provider_config.get("base_url") or provider_config.get("url") or ""
    provider_hint = f"{base_url} {model_name}".lower()
    thinking_config = provider_config.get("thinking") or {}

    if "thinking" not in provider_config and "deepseek" not in provider_hint:
        return

    enabled = bool(thinking_config.get("enabled", False))
    extra_body = dict(request_params.get("extra_body") or {})
    extra_body["thinking"] = {"type": "enabled" if enabled else "disabled"}
    request_params["extra_body"] = extra_body


def main() -> None:
    parser = argparse.ArgumentParser(description="Test DeepSeek V4 Pro API latency.")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH), help="配置文件路径")
    parser.add_argument("--provider", default=DEFAULT_PROVIDER, help="LLM provider 名称")
    parser.add_argument("--prompt", default=DEFAULT_PROMPT, help="测试问题")
    args = parser.parse_args()

    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = SERVER_ROOT / config_path

    provider_config = load_provider_config(config_path, args.provider)
    model_name = provider_config.get("model_name") or provider_config.get("model")
    base_url = provider_config.get("base_url") or provider_config.get("url")
    timeout = float(provider_config.get("timeout", 30))

    client = OpenAI(
        api_key=provider_config["api_key"],
        base_url=base_url,
        timeout=timeout,
    )

    request_params: Dict[str, Any] = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": "你是一个简洁的中文助手。"},
            {"role": "user", "content": args.prompt},
        ],
        "temperature": 0,
        "max_tokens": 64,
    }
    apply_thinking_config(request_params, provider_config)

    started_at = time.perf_counter()
    response = client.chat.completions.create(**request_params)
    elapsed_ms = (time.perf_counter() - started_at) * 1000

    answer = response.choices[0].message.content or ""
    usage = getattr(response, "usage", None)
    thinking_type = (request_params.get("extra_body") or {}).get("thinking", {}).get("type", "not_sent")

    print(f"provider: {args.provider}")
    print(f"model: {model_name}")
    print(f"base_url: {base_url}")
    print(f"thinking: {thinking_type}")
    print(f"latency_ms: {elapsed_ms:.0f}")
    print(f"latency_sec: {elapsed_ms / 1000:.3f}")
    if usage:
        print(f"prompt_tokens: {getattr(usage, 'prompt_tokens', 'unknown')}")
        print(f"completion_tokens: {getattr(usage, 'completion_tokens', 'unknown')}")
        print(f"total_tokens: {getattr(usage, 'total_tokens', 'unknown')}")
    print(f"answer: {answer.strip()}")


if __name__ == "__main__":
    main()
