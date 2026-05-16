"""
Test Alibaba Cloud Bailian CosyVoice voice enrollment and synthesis.

Official flow:
1. Create/query a custom voice with the REST customization API.
2. Synthesize with DashScope SpeechSynthesizer using the same target model.
"""
import argparse
import base64
import json
import mimetypes
import os
import re
import sys
import time
import uuid
from pathlib import Path

import requests
import yaml


DEFAULT_CONFIG = "main/xiaozhi-server/data/.config_hospice.yaml"
DEFAULT_MODEL = "cosyvoice-v3.5-flash"
DEFAULT_PREFIX = "hospice"
DEFAULT_OUTPUT = "main/xiaozhi-server/test/output/cosyvoice_output.mp3"

HTTP_BASES = {
    "cn": "https://dashscope.aliyuncs.com/api/v1",
    "intl": "https://dashscope-intl.aliyuncs.com/api/v1",
}
WS_BASES = {
    "cn": "wss://dashscope.aliyuncs.com/api-ws/v1/inference",
    "intl": "wss://dashscope-intl.aliyuncs.com/api-ws/v1/inference",
}


def load_yaml(path):
    path = Path(path)
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def nested_get(data, path):
    current = data
    for part in path:
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def find_api_key(config, explicit=None):
    candidates = [
        ("--api-key", explicit),
        ("DASHSCOPE_API_KEY", os.getenv("DASHSCOPE_API_KEY")),
        ("ALIYUN_DASHSCOPE_API_KEY", os.getenv("ALIYUN_DASHSCOPE_API_KEY")),
        ("hospice.cosyvoice.api_key", nested_get(config, ["hospice", "cosyvoice", "api_key"])),
        ("hospice.voice_clone.aliyun.api_key", nested_get(config, ["hospice", "voice_clone", "aliyun", "api_key"])),
        ("LLM.AliLLM.api_key", nested_get(config, ["LLM", "AliLLM", "api_key"])),
    ]
    for source, value in candidates:
        if value:
            return str(value), source
    return None, None


def find_oss_config(config, args):
    cosyvoice = nested_get(config, ["hospice", "cosyvoice"]) or {}
    oss_config = cosyvoice.get("oss") or nested_get(config, ["hospice", "oss"]) or {}
    values = {
        "access_key_id": args.oss_access_key_id
        or os.getenv("ALIYUN_OSS_ACCESS_KEY_ID")
        or os.getenv("OSS_ACCESS_KEY_ID")
        or oss_config.get("access_key_id"),
        "access_key_secret": args.oss_access_key_secret
        or os.getenv("ALIYUN_OSS_ACCESS_KEY_SECRET")
        or os.getenv("OSS_ACCESS_KEY_SECRET")
        or oss_config.get("access_key_secret"),
        "endpoint": args.oss_endpoint
        or os.getenv("ALIYUN_OSS_ENDPOINT")
        or os.getenv("OSS_ENDPOINT")
        or oss_config.get("endpoint"),
        "bucket": args.oss_bucket
        or os.getenv("ALIYUN_OSS_BUCKET")
        or os.getenv("OSS_BUCKET")
        or oss_config.get("bucket"),
        "prefix": args.oss_prefix
        or os.getenv("ALIYUN_OSS_PREFIX")
        or os.getenv("OSS_PREFIX")
        or oss_config.get("prefix")
        or "xiaozhi/cosyvoice",
    }
    return values


def mask_secret(value):
    if not value:
        return "(missing)"
    value = str(value)
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}...{value[-4:]}"


def clean_prefix(prefix):
    prefix = re.sub(r"[^A-Za-z0-9]", "", prefix or DEFAULT_PREFIX)
    return (prefix or DEFAULT_PREFIX)[:10]


def customization_url(region):
    return f"{HTTP_BASES[region]}/services/audio/tts/customization"


def post_customization(args, payload):
    config = load_yaml(args.config)
    api_key, key_source = find_api_key(config, args.api_key)
    if not api_key:
        raise RuntimeError(
            "Missing DashScope API key. Set DASHSCOPE_API_KEY or configure hospice.cosyvoice.api_key."
        )

    print(f"Region: {args.region}")
    print(f"Endpoint: {customization_url(args.region)}")
    print(f"API key: {mask_secret(api_key)} ({key_source})")
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    resp = requests.post(
        customization_url(args.region),
        headers=headers,
        json=payload,
        timeout=args.timeout,
    )
    print(f"HTTP: {resp.status_code}")
    try:
        data = resp.json()
        print(json.dumps(data, ensure_ascii=False, indent=2))
    except ValueError:
        print(resp.text)
        resp.raise_for_status()
        return {}
    if resp.status_code >= 400:
        raise RuntimeError(data.get("message") or data.get("code") or f"HTTP {resp.status_code}")
    return data


def upload_local_audio_to_oss(args, audio_file):
    try:
        import oss2
    except ImportError as exc:
        raise RuntimeError("oss2 package is not installed. Install with: pip install oss2") from exc

    config = load_yaml(args.config)
    oss_config = find_oss_config(config, args)
    missing = [name for name in ("access_key_id", "access_key_secret", "endpoint", "bucket") if not oss_config.get(name)]
    if missing:
        raise RuntimeError(
            "Missing OSS config: "
            + ", ".join(missing)
            + ". Set ALIYUN_OSS_ACCESS_KEY_ID, ALIYUN_OSS_ACCESS_KEY_SECRET, ALIYUN_OSS_ENDPOINT, ALIYUN_OSS_BUCKET."
        )

    audio_path = Path(audio_file)
    if not audio_path.exists():
        raise RuntimeError(f"Missing audio file: {audio_path}")
    content_type = mimetypes.guess_type(str(audio_path))[0] or "audio/wav"
    object_key = "/".join(
        part.strip("/")
        for part in (
            oss_config["prefix"],
            time.strftime("%Y%m%d"),
            f"{audio_path.stem}-{uuid.uuid4().hex[:10]}{audio_path.suffix.lower()}",
        )
        if part
    )

    endpoint = oss_config["endpoint"]
    if not endpoint.startswith(("http://", "https://")):
        endpoint = f"https://{endpoint}"
    print(f"OSS endpoint: {endpoint}")
    print(f"OSS bucket: {oss_config['bucket']}")
    print(f"OSS object: {object_key}")

    auth = oss2.Auth(oss_config["access_key_id"], oss_config["access_key_secret"])
    bucket = oss2.Bucket(auth, endpoint, oss_config["bucket"])
    bucket.put_object_from_file(object_key, str(audio_path), headers={"Content-Type": content_type})
    signed_url = bucket.sign_url("GET", object_key, args.oss_expires)
    print(f"Signed audio URL expires in: {args.oss_expires}s")
    print(f"Signed audio URL: {signed_url}")
    return signed_url


def command_clone(args):
    if not args.audio_url:
        raise RuntimeError("clone requires --audio-url. Alibaba Cloud requires a public audio URL.")
    input_data = {
        "action": "create_voice",
        "target_model": args.model,
        "prefix": clean_prefix(args.prefix),
        "url": args.audio_url,
        "language_hints": [args.language],
    }
    if args.max_prompt_audio_length is not None:
        input_data["max_prompt_audio_length"] = args.max_prompt_audio_length
    if args.enable_preprocess:
        input_data["enable_preprocess"] = True

    payload = {"model": "voice-enrollment", "input": input_data}
    data = post_customization(args, payload)
    voice_id = (data.get("output") or {}).get("voice_id")
    if voice_id:
        print(f"Voice ID: {voice_id}")
    return data


def command_clone_local(args):
    args.audio_url = upload_local_audio_to_oss(args, args.audio_file)
    return command_clone(args)


def command_clone_local_and_wait(args):
    args.audio_url = upload_local_audio_to_oss(args, args.audio_file)
    return command_clone_and_wait(args)


def command_design(args):
    input_data = {
        "action": "create_voice",
        "target_model": args.model,
        "voice_prompt": args.voice_prompt,
        "preview_text": args.preview_text,
        "prefix": clean_prefix(args.prefix),
        "language_hints": [args.language],
    }
    payload = {
        "model": "voice-enrollment",
        "input": input_data,
        "parameters": {
            "sample_rate": args.sample_rate,
            "response_format": args.response_format,
        },
    }
    data = post_customization(args, payload)
    output = data.get("output") or {}
    voice_id = output.get("voice_id")
    if voice_id:
        print(f"Voice ID: {voice_id}")
    preview = output.get("preview_audio") or {}
    preview_data = preview.get("data")
    if preview_data and args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(base64.b64decode(preview_data))
        print(f"Preview audio: {output_path}")
    return data


def command_query(args):
    payload = {
        "model": "voice-enrollment",
        "input": {
            "action": "query_voice",
            "voice_id": args.voice_id,
        },
    }
    return post_customization(args, payload)


def command_list(args):
    input_data = {
        "action": "list_voice",
        "page_size": args.page_size,
        "page_index": args.page_index,
    }
    if args.prefix:
        input_data["prefix"] = clean_prefix(args.prefix)
    payload = {"model": "voice-enrollment", "input": input_data}
    return post_customization(args, payload)


def configure_dashscope(args):
    config = load_yaml(args.config)
    api_key, key_source = find_api_key(config, args.api_key)
    if not api_key:
        raise RuntimeError(
            "Missing DashScope API key. Set DASHSCOPE_API_KEY or configure hospice.cosyvoice.api_key."
        )
    try:
        import dashscope
    except ImportError as exc:
        raise RuntimeError("dashscope package is not installed. Install with: pip install dashscope") from exc

    dashscope.api_key = api_key
    dashscope.base_websocket_api_url = WS_BASES[args.region]
    dashscope.base_http_api_url = HTTP_BASES[args.region]
    print(f"Region: {args.region}")
    print(f"WebSocket: {WS_BASES[args.region]}")
    print(f"API key: {mask_secret(api_key)} ({key_source})")
    return dashscope


def command_synth(args):
    configure_dashscope(args)
    try:
        from dashscope.audio.tts_v2 import SpeechSynthesizer
    except ImportError as exc:
        raise RuntimeError("dashscope.audio.tts_v2.SpeechSynthesizer is unavailable in this dashscope version.") from exc

    print(f"Model: {args.model}")
    print(f"Voice: {args.voice_id}")
    print(f"Text: {args.text}")
    additional_params = {}
    if args.instruction:
        additional_params["instruction"] = args.instruction
        print(f"Instruction: {args.instruction}")
    if args.enable_markdown_filter:
        additional_params["enable_markdown_filter"] = True
    synthesizer = SpeechSynthesizer(
        model=args.model,
        voice=args.voice_id,
        speech_rate=args.speech_rate,
        volume=args.volume,
        additional_params=additional_params or None,
    )
    audio = synthesizer.call(args.text)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(audio)
    print(f"Request ID: {synthesizer.get_last_request_id()}")
    try:
        print(f"First package delay: {synthesizer.get_first_package_delay()} ms")
    except Exception:
        pass
    print(f"Audio output: {output_path}")
    return {"output": str(output_path)}


def command_clone_and_wait(args):
    data = command_clone(args)
    voice_id = (data.get("output") or {}).get("voice_id")
    if not voice_id:
        raise RuntimeError("Create voice response did not include output.voice_id")
    for index in range(args.poll_attempts):
        print(f"Polling {index + 1}/{args.poll_attempts}: {voice_id}")
        query_args = argparse.Namespace(**vars(args))
        query_args.voice_id = voice_id
        result = command_query(query_args)
        status = (result.get("output") or {}).get("status")
        if status == "OK":
            print("Voice is ready.")
            return result
        if status == "UNDEPLOYED":
            raise RuntimeError("Voice was rejected: UNDEPLOYED")
        time.sleep(args.poll_interval)
    raise RuntimeError("Voice did not become ready before polling timed out.")


def build_parser():
    parser = argparse.ArgumentParser(description="Test Alibaba Cloud Bailian CosyVoice.")
    parser.add_argument("--config", default=DEFAULT_CONFIG)
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--region", choices=("cn", "intl"), default="cn")
    parser.add_argument("--timeout", type=int, default=60)

    subparsers = parser.add_subparsers(dest="command", required=True)

    clone = subparsers.add_parser("clone", help="Create a cloned voice from a public audio URL.")
    clone.add_argument("--audio-url", required=True)
    clone.add_argument("--model", default=DEFAULT_MODEL)
    clone.add_argument("--prefix", default=DEFAULT_PREFIX)
    clone.add_argument("--language", default="zh")
    clone.add_argument("--max-prompt-audio-length", type=float, default=20.0)
    clone.add_argument("--enable-preprocess", action="store_true")
    clone.set_defaults(func=command_clone)

    clone_wait = subparsers.add_parser("clone-and-wait", help="Create a voice and poll until ready.")
    clone_wait.add_argument("--audio-url", required=True)
    clone_wait.add_argument("--model", default=DEFAULT_MODEL)
    clone_wait.add_argument("--prefix", default=DEFAULT_PREFIX)
    clone_wait.add_argument("--language", default="zh")
    clone_wait.add_argument("--max-prompt-audio-length", type=float, default=20.0)
    clone_wait.add_argument("--enable-preprocess", action="store_true")
    clone_wait.add_argument("--poll-attempts", type=int, default=30)
    clone_wait.add_argument("--poll-interval", type=int, default=10)
    clone_wait.set_defaults(func=command_clone_and_wait)

    clone_local = subparsers.add_parser("clone-local", help="Upload a local audio file to OSS, then create a cloned voice.")
    clone_local.add_argument("--audio-file", required=True)
    clone_local.add_argument("--model", default=DEFAULT_MODEL)
    clone_local.add_argument("--prefix", default=DEFAULT_PREFIX)
    clone_local.add_argument("--language", default="zh")
    clone_local.add_argument("--max-prompt-audio-length", type=float, default=20.0)
    clone_local.add_argument("--enable-preprocess", action="store_true")
    clone_local.add_argument("--oss-access-key-id", default=None)
    clone_local.add_argument("--oss-access-key-secret", default=None)
    clone_local.add_argument("--oss-endpoint", default=None)
    clone_local.add_argument("--oss-bucket", default=None)
    clone_local.add_argument("--oss-prefix", default=None)
    clone_local.add_argument("--oss-expires", type=int, default=3600)
    clone_local.set_defaults(func=command_clone_local)

    clone_local_wait = subparsers.add_parser(
        "clone-local-and-wait",
        help="Upload a local audio file to OSS, create a cloned voice, and poll until ready.",
    )
    clone_local_wait.add_argument("--audio-file", required=True)
    clone_local_wait.add_argument("--model", default=DEFAULT_MODEL)
    clone_local_wait.add_argument("--prefix", default=DEFAULT_PREFIX)
    clone_local_wait.add_argument("--language", default="zh")
    clone_local_wait.add_argument("--max-prompt-audio-length", type=float, default=20.0)
    clone_local_wait.add_argument("--enable-preprocess", action="store_true")
    clone_local_wait.add_argument("--poll-attempts", type=int, default=30)
    clone_local_wait.add_argument("--poll-interval", type=int, default=10)
    clone_local_wait.add_argument("--oss-access-key-id", default=None)
    clone_local_wait.add_argument("--oss-access-key-secret", default=None)
    clone_local_wait.add_argument("--oss-endpoint", default=None)
    clone_local_wait.add_argument("--oss-bucket", default=None)
    clone_local_wait.add_argument("--oss-prefix", default=None)
    clone_local_wait.add_argument("--oss-expires", type=int, default=3600)
    clone_local_wait.set_defaults(func=command_clone_local_and_wait)

    design = subparsers.add_parser("design", help="Create a voice by text description and save preview audio.")
    design.add_argument("--model", default=DEFAULT_MODEL)
    design.add_argument("--prefix", default="warm")
    design.add_argument("--language", default="zh")
    design.add_argument("--voice-prompt", default="温柔亲切的中年女性声音，说话自然清晰，适合陪伴老人聊天。")
    design.add_argument("--preview-text", default="您好，我是小暖，今天我会一直陪着您。")
    design.add_argument("--sample-rate", type=int, default=24000)
    design.add_argument("--response-format", default="wav", choices=("wav", "mp3", "pcm"))
    design.add_argument("--output", default="main/xiaozhi-server/test/output/cosyvoice_design_preview.wav")
    design.set_defaults(func=command_design)

    query = subparsers.add_parser("query", help="Query a voice by voice_id.")
    query.add_argument("--voice-id", required=True)
    query.set_defaults(func=command_query)

    list_cmd = subparsers.add_parser("list", help="List created voices.")
    list_cmd.add_argument("--prefix", default=None)
    list_cmd.add_argument("--page-index", type=int, default=0)
    list_cmd.add_argument("--page-size", type=int, default=10)
    list_cmd.set_defaults(func=command_list)

    synth = subparsers.add_parser("synth", help="Synthesize text with a CosyVoice voice_id.")
    synth.add_argument("--voice-id", required=True)
    synth.add_argument("--model", default=DEFAULT_MODEL)
    synth.add_argument("--text", default="小花发来消息说，今天晚上会来看您。")
    synth.add_argument("--output", default=DEFAULT_OUTPUT)
    synth.add_argument("--instruction", default=None, help="Dialect/emotion instruction, e.g. 请用四川话表达。")
    synth.add_argument("--speech-rate", type=float, default=1.0)
    synth.add_argument("--volume", type=int, default=50)
    synth.add_argument("--enable-markdown-filter", action="store_true")
    synth.set_defaults(func=command_synth)

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    try:
        args.func(args)
    except Exception as exc:
        print(f"ERROR: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
