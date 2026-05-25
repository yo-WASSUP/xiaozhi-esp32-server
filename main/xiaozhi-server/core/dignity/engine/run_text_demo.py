from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from openai import OpenAIError

SERVER_ROOT = Path(__file__).resolve().parents[3]
if str(SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVER_ROOT))

from core.dignity.engine.graph import OpenAIJsonDecisionModel, build_initial_state, run_text_turn


def main() -> int:
    parser = argparse.ArgumentParser(description="Run dignity therapy text demo.")
    parser.add_argument(
        "utterances",
        nargs="*",
        help="Patient text turns. If omitted, a built-in demo is used.",
    )
    parser.add_argument(
        "--config",
        default="data/.config_hospice.yaml",
        help="Config YAML path relative to xiaozhi-server root.",
    )
    parser.add_argument(
        "--provider",
        default=None,
        help="LLM provider key in the config YAML.",
    )
    args = parser.parse_args()

    utterances = args.utterances or [
        "我小时候跟父亲在院子里种花，那时候很开心。",
        "后来我工作很忙，但我一直觉得做人要诚实。",
        "我最想感谢我的女儿，她一直陪着我。",
        "我有点累了，想休息一下。",
    ]

    decision_model = OpenAIJsonDecisionModel.from_config_file(args.config, provider_name=args.provider)
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
                    "strategy": state["strategy"],
                    "next_action": state["next_action"],
                    "robot_action": state["robot_action"],
                    "eye_expression": state["eye_expression"],
                    "reply": state["reply"],
                    "dignity_memory": state["dignity_memory"],
                    "completed_themes": state["completed_themes"],
                }
            )
    except OpenAIError as exc:
        print(f"LLM 调用失败：{exc}", file=sys.stderr)
        return 1

    print(json.dumps(outputs, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
