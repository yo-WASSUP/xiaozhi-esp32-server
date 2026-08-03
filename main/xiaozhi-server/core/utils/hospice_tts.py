import copy
import os

import yaml

from core.utils import tts


VOICE_SETTINGS_PATH = os.path.join("data", "hospice_voice_settings.yaml")


def load_hospice_voice_settings(device_id, settings_path=VOICE_SETTINGS_PATH):
    if not device_id or not os.path.exists(settings_path):
        return {}
    try:
        with open(settings_path, "r", encoding="utf-8") as file:
            settings = yaml.safe_load(file) or {}
    except (OSError, yaml.YAMLError):
        return {}
    device_settings = settings.get(device_id) or {}
    return device_settings if isinstance(device_settings, dict) else {}


def is_aliyun_cloned_voice_active(voice_settings):
    if not isinstance(voice_settings, dict) or not voice_settings.get("active"):
        return False
    voice_id = voice_settings.get("voice_id") or voice_settings.get("speaker_id")
    provider = voice_settings.get("provider")
    return bool(voice_id and provider == "aliyun_cosyvoice")


def build_aliyun_cloned_tts_config(config, voice_settings):
    """Build an isolated CosyVoice config without changing the default TTS."""
    providers = (config or {}).get("TTS") or {}
    provider_config = next(
        (
            item
            for item in providers.values()
            if isinstance(item, dict) and item.get("type") == "alibl_stream"
        ),
        {},
    )
    result = copy.deepcopy(provider_config)

    hospice_config = (config or {}).get("hospice") or {}
    cosy_config = hospice_config.get("cosyvoice") or {}
    ali_llm_config = ((config or {}).get("LLM") or {}).get("AliLLM") or {}
    result["api_key"] = (
        cosy_config.get("api_key")
        or result.get("api_key")
        or ali_llm_config.get("api_key")
    )
    result["model"] = (
        voice_settings.get("model")
        or cosy_config.get("model")
        or result.get("model")
        or "cosyvoice-v3.5-flash"
    )
    voice_id = voice_settings.get("voice_id") or voice_settings.get("speaker_id")
    result["private_voice"] = voice_id
    if voice_settings.get("instruction") or cosy_config.get("instruction"):
        result["instruction"] = voice_settings.get("instruction") or cosy_config.get(
            "instruction"
        )
    result.setdefault("output_dir", "tmp/")
    return result


def create_aliyun_cloned_tts(config, voice_settings):
    if not is_aliyun_cloned_voice_active(voice_settings):
        raise ValueError("当前设备没有启用阿里云克隆音色")
    provider_config = build_aliyun_cloned_tts_config(config, voice_settings)
    if not provider_config.get("api_key"):
        raise ValueError("缺少阿里云 CosyVoice api_key")
    delete_audio_file = str((config or {}).get("delete_audio", True)).lower() in (
        "true",
        "1",
        "yes",
    )
    return tts.create_instance("alibl_stream", provider_config, delete_audio_file)
