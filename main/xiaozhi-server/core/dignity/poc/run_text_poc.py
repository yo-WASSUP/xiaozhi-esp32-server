from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from openai import OpenAIError
from ruamel.yaml import YAML


SERVER_ROOT = Path(__file__).resolve().parents[3]
if str(SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVER_ROOT))

from core.dignity.poc.graph import OpenAIJsonDecisionModel, build_initial_state, run_text_turn


def main() -> int:
    parser = argparse.ArgumentParser(description="Run dignity therapy LangGraph text POC.")
    parser.add_argument(
        "utterances",
        nargs="*",
        help="Patient text turns. If omitted, a built-in demo is used.",
    )
    parser.add_argument(
        "--config",
        default="data/.config.yaml",
        help="Config YAML path relative to xiaozhi-server root.",
    )
    parser.add_argument(
        "--provider",
        default="DoubaoLLM",
        help="LLM provider key in the config YAML.",
    )
    args = parser.parse_args()

    utterances = args.utterances or [
        "我小时候跟父亲在院子里种花，那时候很开心。",
        "后来我工作很忙，但我一直觉得做人要诚实。",
        "我最想感谢我的女儿，她一直陪着我。",
        "我有点累了，想休息一下。",
    ]

    decision_model = load_decision_model_from_config(args.config, args.provider)
    state = build_initial_state(decision_model=decision_model)
    outputs = []
    try:
        for utterance in utterances:
            state = run_text_turn(state, utterance)
            outputs.append(
                {
                    "patient": utterance,
                    "stage": state["current_stage"],
                    "route": state["route"],
                    "risk_level": state["risk_level"],
                    "strategy": state["strategy"],
                    "next_action": state["next_action"],
                    "robot_action": state["robot_action"],
                    "eye_expression": state["eye_expression"],
                    "reply": state["reply"],
                    "completed_themes": state["completed_themes"],
                }
            )
    except OpenAIError as exc:
        print(f"LLM 调用失败：{exc}", file=sys.stderr)
        return 1

    print(json.dumps(outputs, ensure_ascii=False, indent=2))
    return 0


def load_decision_model_from_config(config_path: str, provider_name: str):
    path = Path(config_path)
    if not path.is_absolute():
        path = SERVER_ROOT / path

    yaml = YAML(typ="safe")
    config = yaml.load(path)
    provider_config = find_provider_config(config, provider_name)
    if not provider_config:
        raise RuntimeError(f"未在配置文件中找到 LLM Provider: {provider_name}")

    api_key = provider_config.get("api_key")
    model = provider_config.get("model_name")
    base_url = provider_config.get("base_url") or provider_config.get("url")
    timeout = float(provider_config.get("timeout", 30))
    if not api_key or not model:
        raise RuntimeError(f"LLM Provider {provider_name} 缺少 api_key 或 model_name")

    return OpenAIJsonDecisionModel(
        api_key=api_key,
        model=model,
        base_url=base_url,
        timeout=timeout,
    )


def find_provider_config(value, provider_name: str):
    if isinstance(value, dict):
        if provider_name in value and isinstance(value[provider_name], dict):
            return value[provider_name]
        for child in value.values():
            result = find_provider_config(child, provider_name)
            if result:
                return result
    if isinstance(value, list):
        for child in value:
            result = find_provider_config(child, provider_name)
            if result:
                return result
    return None


if __name__ == "__main__":
    raise SystemExit(main())
