from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from openai import OpenAI
import yaml

from core.dignity.engine.prompts import (
    DIGNITY_MEMORY_UPDATE_SYSTEM_PROMPT,
    DIGNITY_REPLY_WITH_MEMORY_SYSTEM_PROMPT,
    build_dignity_memory_update_user_prompt,
    build_memory_reply_user_prompt,
)
from core.dignity.engine.rules import normalize_decision
from core.dignity.engine.types import DignityDecision, DignityState


class OpenAIJsonDecisionModel:
    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: Optional[str] = None,
        timeout: float = 30,
        thinking_enabled: bool = False,
        thinking_configured: bool = False,
    ):
        self.model = model
        provider_hint = f"{base_url or ''} {model or ''}".lower()
        self.thinking_configured = thinking_configured or "deepseek" in provider_hint
        self.thinking_enabled = thinking_enabled
        self.client = OpenAI(api_key=api_key, base_url=base_url, timeout=timeout)

    @classmethod
    def from_provider_config(cls, provider_config: dict) -> "OpenAIJsonDecisionModel":
        api_key = provider_config.get("api_key")
        model = provider_config.get("model_name") or provider_config.get("model")
        if not api_key or not model:
            raise RuntimeError("LLM Provider 配置缺少 api_key 或 model_name")
        return cls(
            api_key=api_key,
            model=model,
            base_url=provider_config.get("base_url") or provider_config.get("url"),
            timeout=float(provider_config.get("timeout", 30)),
            thinking_enabled=bool((provider_config.get("thinking") or {}).get("enabled", False)),
            thinking_configured="thinking" in provider_config,
        )

    @classmethod
    def from_config(
        cls,
        config: dict,
        provider_name: Optional[str] = None,
    ) -> "OpenAIJsonDecisionModel":
        provider_name = provider_name or (config.get("selected_module") or {}).get("LLM")
        if not provider_name:
            raise RuntimeError("配置缺少 selected_module.LLM，无法确定 LLM Provider")

        provider_config = (config.get("LLM") or {}).get(provider_name)
        if not provider_config:
            raise RuntimeError(f"未在配置中找到 LLM Provider: {provider_name}")
        return cls.from_provider_config(provider_config)

    @classmethod
    def from_config_file(
        cls,
        config_path: str = "data/.config_hospice.yaml",
        provider_name: Optional[str] = None,
    ) -> "OpenAIJsonDecisionModel":
        path = Path(config_path)
        if not path.is_absolute():
            server_root = Path(__file__).resolve().parents[3]
            path = server_root / path
        with path.open("r", encoding="utf-8") as file:
            config = yaml.safe_load(file) or {}
        return cls.from_config(config, provider_name=provider_name)

    def decide_and_reply(self, state: DignityState) -> DignityDecision:
        request_params = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": DIGNITY_REPLY_WITH_MEMORY_SYSTEM_PROMPT},
                {"role": "user", "content": build_memory_reply_user_prompt(state)},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.2,
        }
        self._apply_thinking_config(request_params)
        response = self.client.chat.completions.create(**request_params)
        content = response.choices[0].message.content or "{}"
        return normalize_decision(json.loads(content))

    def update_dignity_memory(self, state: DignityState) -> dict:
        request_params = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": DIGNITY_MEMORY_UPDATE_SYSTEM_PROMPT},
                {"role": "user", "content": build_dignity_memory_update_user_prompt(state)},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0,
        }
        self._apply_thinking_config(request_params)
        response = self.client.chat.completions.create(**request_params)
        content = response.choices[0].message.content or "{}"
        value = json.loads(content)
        return value if isinstance(value, dict) else {}

    def _apply_thinking_config(self, request_params: dict) -> None:
        if not self.thinking_configured:
            return
        extra_body = dict(request_params.get("extra_body") or {})
        extra_body["thinking"] = {"type": "enabled" if self.thinking_enabled else "disabled"}
        request_params["extra_body"] = extra_body
