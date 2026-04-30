"""
Check Doubao voice clone V3 API credentials without submitting a training job.

The training endpoint and get_voice endpoint use the same V3 auth headers, so a
get_voice request with a dummy speaker_id is enough to catch "Invalid X-Api-Key".
"""
import argparse
import json
import os
import sys
import uuid
from pathlib import Path

import requests
import yaml


TRAIN_API = "https://openspeech.bytedance.com/api/v3/tts/voice_clone"
QUERY_API = "https://openspeech.bytedance.com/api/v3/tts/get_voice"
DEFAULT_RESOURCE_ID = "seed-icl-2.0"
DEFAULT_SPEAKER_PREFIX = "S_hospice_key_check_"
DEFAULT_TRAIN_PREFIX = "S_hospice_train_"


def mask_secret(value):
    if not value:
        return ""
    value = str(value)
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}...{value[-4:]}"


def load_yaml(path):
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def find_clone_config(config):
    hospice_config = config.get("hospice") or {}
    clone_config = hospice_config.get("voice_clone") or {}
    selected_tts = (config.get("selected_module") or {}).get("TTS")
    tts_config = (config.get("TTS") or {}).get(selected_tts, {}) if selected_tts else {}

    api_key = (
        os.environ.get("DOUBAO_VOICE_CLONE_API_KEY")
        or clone_config.get("api_key")
        or tts_config.get("api_key")
    )
    resource_id = (
        os.environ.get("DOUBAO_VOICE_CLONE_RESOURCE_ID")
        or clone_config.get("resource_id")
        or DEFAULT_RESOURCE_ID
    )
    appid = str(
        os.environ.get("DOUBAO_VOICE_CLONE_APPID")
        or clone_config.get("appid")
        or tts_config.get("appid")
        or ""
    )
    language = int(os.environ.get("DOUBAO_VOICE_CLONE_LANGUAGE") or clone_config.get("language", 0))
    model_type = int(os.environ.get("DOUBAO_VOICE_CLONE_MODEL_TYPE") or clone_config.get("model_type", 5))
    source = int(os.environ.get("DOUBAO_VOICE_CLONE_SOURCE") or clone_config.get("source", 2))
    extra_params = clone_config.get("extra_params") or {}
    has_access_token = bool(tts_config.get("access_token"))
    return api_key, resource_id, appid, language, model_type, source, extra_params, selected_tts, has_access_token


def main():
    parser = argparse.ArgumentParser(description="Check Doubao voice clone V3 X-Api-Key.")
    parser.add_argument(
        "--config",
        default="main/xiaozhi-server/data/.config_hospice.yaml",
        help="Path to project config yaml.",
    )
    parser.add_argument(
        "--speaker-id",
        default=None,
        help="Speaker ID to query. Defaults to a random non-existing ID for key validation.",
    )
    parser.add_argument("--resource-id", default=None, help="Override X-Api-Resource-Id.")
    parser.add_argument(
        "--train-audio",
        default=None,
        help="Submit this audio file to the V3 voice_clone training endpoint.",
    )
    parser.add_argument("--timeout", type=int, default=15, help="HTTP timeout seconds.")
    args = parser.parse_args()

    config_path = Path(args.config)
    config = load_yaml(config_path)
    (
        api_key,
        resource_id,
        appid,
        language,
        model_type,
        source,
        extra_params,
        selected_tts,
        has_access_token,
    ) = find_clone_config(config)
    if args.resource_id:
        resource_id = args.resource_id
    if args.train_audio:
        speaker_id = args.speaker_id or f"{DEFAULT_TRAIN_PREFIX}{uuid.uuid4().hex[:12]}"
    else:
        speaker_id = args.speaker_id or f"{DEFAULT_SPEAKER_PREFIX}{uuid.uuid4().hex[:12]}"

    print(f"Config: {config_path}")
    print(f"Selected TTS: {selected_tts or '(none)'}")
    print(f"Voice clone resource_id: {resource_id}")
    print(f"Voice clone api_key: {mask_secret(api_key) or '(missing)'}")
    print(f"Voice clone appid: {appid or '(missing)'}")
    print(f"Voice clone model_type: {model_type}")
    print(f"Query speaker_id: {speaker_id}")

    if not api_key:
        print("")
        print("Missing voice clone V3 X-Api-Key.")
        print("Configure one of:")
        print("  hospice.voice_clone.api_key")
        print("  TTS.<selected module>.api_key")
        if has_access_token:
            print("")
            print("Note: the selected TTS has access_token, but voice clone V3 needs X-Api-Key.")
        return 2
    if not appid:
        print("")
        print("Missing voice clone appid.")
        print("Configure hospice.voice_clone.appid or TTS.<selected module>.appid")
        return 2

    headers = {
        "Content-Type": "application/json",
        "X-Api-Key": api_key,
        "X-Api-Resource-Id": resource_id,
        "X-Api-Request-Id": str(uuid.uuid4()),
    }
    if args.train_audio:
        audio_path = Path(args.train_audio)
        if not audio_path.exists():
            print(f"Missing audio file: {audio_path}")
            return 7
        audio_format = audio_path.suffix.lstrip(".").lower()
        if audio_format not in ("wav", "mp3", "ogg", "m4a", "aac", "pcm"):
            print("Unsupported audio format. Use wav, mp3, ogg, m4a, aac, or pcm.")
            return 8
        import base64

        payload = {
            "speaker_id": speaker_id,
            "appid": appid,
            "audios": [{
                "audio_bytes": base64.b64encode(audio_path.read_bytes()).decode("ascii"),
                "audio_format": audio_format,
            }],
            "source": source,
            "language": language,
            "model_type": model_type,
            "extra_params": json.dumps(extra_params, ensure_ascii=False),
        }
        url = TRAIN_API
        print(f"Mode: train submit")
        print(f"Audio: {audio_path}")
    else:
        payload = {"speaker_id": speaker_id, "appid": appid}
        url = QUERY_API
        print("Mode: status query")

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=args.timeout)
    except requests.RequestException as exc:
        print(f"Request failed: {exc}")
        return 3

    print(f"HTTP: {resp.status_code}")
    try:
        body = resp.json()
        print(json.dumps(body, ensure_ascii=False, indent=2))
    except ValueError:
        body = resp.text
        print(body)

    body_text = json.dumps(body, ensure_ascii=False) if not isinstance(body, str) else body
    if "Invalid X-Api-Key" in body_text:
        print("")
        print("Diagnosis: X-Api-Key is invalid for Doubao voice clone V3.")
        return 4
    if "resource ID is mismatched with speaker related resource" in body_text:
        print("")
        print("Diagnosis: X-Api-Key was accepted, but the speaker/resource binding check failed.")
        print("For status query, pass a real speaker_id trained under this resource_id.")
        print("For training validation, run with --train-audio <file> to submit an actual sample.")
        return 6
    if resp.status_code >= 400:
        print("")
        print("Diagnosis: request reached the V3 endpoint, but the service rejected it.")
        return 5

    print("")
    print("Diagnosis: X-Api-Key was accepted by the V3 endpoint.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
