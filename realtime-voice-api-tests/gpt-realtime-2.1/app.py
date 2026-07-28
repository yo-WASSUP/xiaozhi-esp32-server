from __future__ import annotations

import asyncio
import base64
import json
import os
import sys
import time
from pathlib import Path

import websockets

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common_audio import (  # noqa: E402
    PcmMicrophone,
    PcmPlayer,
    load_script_env,
    require_env,
    run_until_one_stops,
)


INPUT_RATE = 24_000
OUTPUT_RATE = 24_000


async def send_microphone(websocket: websockets.ClientConnection, microphone: PcmMicrophone) -> None:
    while True:
        audio = await microphone.read()
        await websocket.send(
            json.dumps(
                {
                    "type": "input_audio_buffer.append",
                    "audio": base64.b64encode(audio).decode("ascii"),
                }
            )
        )


async def receive_events(websocket: websockets.ClientConnection, player: PcmPlayer) -> None:
    response_started_at: float | None = None
    first_audio_seen = False

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
        elif event_type == "input_audio_buffer.speech_stopped":
            response_started_at = time.perf_counter()
            print("[用户] 话轮结束")
        elif event_type == "conversation.item.input_audio_transcription.completed":
            print(f"[用户转写] {event.get('transcript', '')}")
        elif event_type == "conversation.item.input_audio_transcription.failed":
            print(f"[转写失败] {json.dumps(event.get('error', {}), ensure_ascii=False)}")
        elif event_type == "response.output_audio.delta":
            if response_started_at is not None and not first_audio_seen:
                latency_ms = int((time.perf_counter() - response_started_at) * 1000)
                print(f"[首包延迟] {latency_ms} ms")
                first_audio_seen = True
            player.enqueue(base64.b64decode(event.get("delta", "")))
        elif event_type == "response.output_audio_transcript.delta":
            print(event.get("delta", ""), end="", flush=True)
        elif event_type == "response.output_audio_transcript.done":
            transcript = event.get("transcript", "")
            if transcript:
                print(f"\n[助手完整转写] {transcript}")
            else:
                print()
        elif event_type == "response.done":
            response = event.get("response", {})
            status = response.get("status", "")
            print(f"[响应结束] status={status}, 本地缓冲={player.queued_ms} ms")
        elif event_type == "error":
            raise RuntimeError(json.dumps(event.get("error", event), ensure_ascii=False))


async def main() -> None:
    load_script_env(__file__)
    api_key = require_env("OPENAI_API_KEY")
    model = os.getenv("OPENAI_REALTIME_MODEL", "gpt-realtime-2.1").strip()
    voice = os.getenv("OPENAI_REALTIME_VOICE", "marin").strip()
    instructions = os.getenv(
        "OPENAI_REALTIME_INSTRUCTIONS",
        "你是一名自然、简洁的中文语音助手。",
    ).strip()

    url = f"wss://api.openai.com/v1/realtime?model={model}"
    headers = {"Authorization": f"Bearer {api_key}"}

    async with websockets.connect(
        url,
        additional_headers=headers,
        max_size=None,
        ping_interval=20,
        ping_timeout=20,
    ) as websocket:
        await websocket.send(
            json.dumps(
                {
                    "type": "session.update",
                    "session": {
                        "type": "realtime",
                        "model": model,
                        "output_modalities": ["audio"],
                        "instructions": instructions,
                        "audio": {
                            "input": {
                                "format": {"type": "audio/pcm", "rate": INPUT_RATE},
                                "transcription": {
                                    "model": "gpt-4o-mini-transcribe",
                                    "language": "zh",
                                },
                                "turn_detection": {
                                    "type": "semantic_vad",
                                    "eagerness": "auto",
                                    "create_response": True,
                                    "interrupt_response": True,
                                },
                            },
                            "output": {
                                "format": {
                                    "type": "audio/pcm",
                                    "rate": OUTPUT_RATE,
                                },
                                "voice": voice,
                            },
                        },
                    },
                },
                ensure_ascii=False,
            )
        )

        print(f"[连接] OpenAI {model}，输入/输出 PCM16 24 kHz")
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
