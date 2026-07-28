from __future__ import annotations

import asyncio
import base64
import json
import os
import sys
import time
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import websockets

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common_audio import (  # noqa: E402
    PcmMicrophone,
    PcmPlayer,
    load_script_env,
    require_env,
    run_until_one_stops,
)


INPUT_RATE = 16_000
OUTPUT_RATE = 24_000


def build_url(model: str) -> str:
    custom_url = os.getenv("QWEN_REALTIME_URL", "").strip()
    if custom_url:
        parts = urlsplit(custom_url)
        query = dict(parse_qsl(parts.query))
        query["model"] = model
        return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))

    workspace_id = require_env("QWEN_WORKSPACE_ID")
    return (
        f"wss://{workspace_id}.cn-beijing.maas.aliyuncs.com/"
        f"api-ws/v1/realtime?model={model}"
    )


async def send_microphone(websocket: websockets.ClientConnection, microphone: PcmMicrophone) -> None:
    sequence = 0
    while True:
        audio = await microphone.read()
        sequence += 1
        await websocket.send(
            json.dumps(
                {
                    "event_id": f"mic_{sequence}",
                    "type": "input_audio_buffer.append",
                    "audio": base64.b64encode(audio).decode("ascii"),
                }
            )
        )


async def receive_events(websocket: websockets.ClientConnection, player: PcmPlayer) -> None:
    response_started_at: float | None = None
    first_audio_seen = False
    responding = False

    async for raw_message in websocket:
        if not isinstance(raw_message, str):
            continue
        event = json.loads(raw_message)
        event_type = event.get("type", "")

        if event_type == "session.updated":
            print("[会话] 配置已生效，可以开始说话")
        elif event_type == "input_audio_buffer.speech_started":
            dropped_ms = player.clear()
            first_audio_seen = False
            print(f"\n[打断] 检测到用户说话，清除 {dropped_ms} ms 待播放音频")
            if responding:
                await websocket.send(json.dumps({"type": "response.cancel"}))
        elif event_type == "input_audio_buffer.speech_stopped":
            response_started_at = time.perf_counter()
            print("[用户] 话轮结束")
        elif event_type == "conversation.item.input_audio_transcription.delta":
            text = event.get("text", "")
            stash = event.get("stash", "")
            print(f"\r[用户转写] {text}{stash}", end="", flush=True)
        elif event_type == "conversation.item.input_audio_transcription.completed":
            print(f"\n[用户完整转写] {event.get('transcript', event.get('text', ''))}")
        elif event_type == "response.created":
            responding = True
        elif event_type == "response.audio.delta":
            if response_started_at is not None and not first_audio_seen:
                latency_ms = int((time.perf_counter() - response_started_at) * 1000)
                print(f"[首包延迟] {latency_ms} ms")
                first_audio_seen = True
            player.enqueue(base64.b64decode(event.get("delta", "")))
        elif event_type == "response.audio_transcript.delta":
            print(event.get("delta", ""), end="", flush=True)
        elif event_type == "response.audio_transcript.done":
            transcript = event.get("transcript", "")
            if transcript:
                print(f"\n[助手完整转写] {transcript}")
            else:
                print()
        elif event_type == "response.done":
            responding = False
            response = event.get("response", {})
            print(f"[响应结束] status={response.get('status', '')}, 本地缓冲={player.queued_ms} ms")
        elif event_type == "error":
            raise RuntimeError(json.dumps(event.get("error", event), ensure_ascii=False))


async def main() -> None:
    load_script_env(__file__)
    api_key = require_env("DASHSCOPE_API_KEY")
    model = os.getenv("QWEN_REALTIME_MODEL", "qwen3.5-omni-plus-realtime").strip()
    voice = os.getenv("QWEN_REALTIME_VOICE", "Ethan").strip()
    instructions = os.getenv(
        "QWEN_REALTIME_INSTRUCTIONS",
        "你是一名自然、简洁的中文语音助手。",
    ).strip()
    vad_type = os.getenv("QWEN_VAD_TYPE", "server_vad").strip()
    vad_threshold = float(os.getenv("QWEN_VAD_THRESHOLD", "0.5"))
    vad_prefix_padding_ms = int(os.getenv("QWEN_VAD_PREFIX_PADDING_MS", "300"))
    vad_silence_ms = int(os.getenv("QWEN_VAD_SILENCE_MS", "500"))

    async with websockets.connect(
        build_url(model),
        additional_headers={"Authorization": f"Bearer {api_key}"},
        max_size=None,
        ping_interval=20,
        ping_timeout=20,
    ) as websocket:
        await websocket.send(
            json.dumps(
                {
                    "type": "session.update",
                    "session": {
                        "modalities": ["text", "audio"],
                        "voice": voice,
                        "instructions": instructions,
                        "input_audio_format": "pcm",
                        "output_audio_format": "pcm",
                        "input_audio_transcription": {
                            "model": "qwen3-asr-flash-realtime"
                        },
                        "turn_detection": {
                            "type": vad_type,
                            "threshold": vad_threshold,
                            "prefix_padding_ms": vad_prefix_padding_ms,
                            "silence_duration_ms": vad_silence_ms,
                        },
                    },
                },
                ensure_ascii=False,
            )
        )

        print(f"[连接] Qwen {model}，输入 PCM16 16 kHz，输出 PCM16 24 kHz")
        with PcmMicrophone(INPUT_RATE) as microphone, PcmPlayer(OUTPUT_RATE) as player:
            await run_until_one_stops(
                send_microphone(websocket, microphone),
                receive_events(websocket, player),
            )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[结束] 用户停止测试")
    except Exception as exc:
        print(f"\n[错误] {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
