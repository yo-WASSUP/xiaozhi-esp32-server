from __future__ import annotations

import asyncio
import base64
import contextlib
import gzip
import json
import os
import struct
import sys
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import websockets
from websockets.exceptions import ConnectionClosed

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

MESSAGE_FULL_CLIENT = 0x1
MESSAGE_AUDIO_CLIENT = 0x2
MESSAGE_FULL_SERVER = 0x9
MESSAGE_AUDIO_SERVER = 0xB
MESSAGE_ERROR = 0xF
FLAG_WITH_EVENT = 0x4
SERIALIZATION_NONE = 0x0
SERIALIZATION_JSON = 0x1

EVENT_START_CONNECTION = 1
EVENT_FINISH_CONNECTION = 2
EVENT_CONNECTION_STARTED = 50
EVENT_CONNECTION_FAILED = 51
EVENT_CONNECTION_ENDED = 52
EVENT_START_SESSION = 100
EVENT_FINISH_SESSION = 102
EVENT_SESSION_STARTED = 150
EVENT_SESSION_FAILED = 153
EVENT_TASK_AUDIO = 200
EVENT_TTS_STARTED = 350
EVENT_TTS_AUDIO = 352
EVENT_TTS_FINISHED = 359
EVENT_ASR_INFO = 450
EVENT_ASR_RESPONSE = 451
EVENT_ASR_ENDED = 459
EVENT_CHAT_RESPONSE = 550
EVENT_CHAT_ENDED = 559
EVENT_CLIENT_INTERRUPT = 515

NO_SESSION_EVENTS = {
    EVENT_START_CONNECTION,
    EVENT_FINISH_CONNECTION,
    EVENT_CONNECTION_STARTED,
    EVENT_CONNECTION_FAILED,
    EVENT_CONNECTION_ENDED,
}
CONNECT_ID_EVENTS = {
    EVENT_CONNECTION_STARTED,
    EVENT_CONNECTION_FAILED,
    EVENT_CONNECTION_ENDED,
}


@dataclass
class ServerFrame:
    message_type: int
    flags: int
    serialization: int
    compression: int
    event: int | None
    session_id: str
    connect_id: str
    error_code: int | None
    payload: bytes


def build_event_frame(
    message_type: int,
    event: int,
    session_id: str = "",
    payload: bytes = b"",
    serialization: int = SERIALIZATION_JSON,
) -> bytes:
    frame = bytearray((0x11, (message_type << 4) | FLAG_WITH_EVENT, serialization << 4, 0))
    frame.extend(struct.pack(">i", event))
    if event not in NO_SESSION_EVENTS:
        encoded_session = session_id.encode("utf-8")
        frame.extend(struct.pack(">I", len(encoded_session)))
        frame.extend(encoded_session)
    frame.extend(struct.pack(">I", len(payload)))
    frame.extend(payload)
    return bytes(frame)


def build_json_frame(event: int, session_id: str, body: dict[str, Any]) -> bytes:
    body.setdefault("session_id", session_id)
    payload = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return build_event_frame(MESSAGE_FULL_CLIENT, event, session_id, payload, SERIALIZATION_JSON)


def parse_server_frame(data: bytes) -> ServerFrame:
    if len(data) < 8:
        raise RuntimeError(f"豆包响应帧过短: {len(data)}")

    header_size = (data[0] & 0x0F) * 4
    message_type = (data[1] >> 4) & 0x0F
    flags = data[1] & 0x0F
    serialization = (data[2] >> 4) & 0x0F
    compression = data[2] & 0x0F
    offset = header_size

    if flags in (1, 2, 3) and message_type != MESSAGE_AUDIO_CLIENT:
        offset += 4

    event: int | None = None
    session_id = ""
    connect_id = ""
    if flags & FLAG_WITH_EVENT:
        event = struct.unpack_from(">i", data, offset)[0]
        offset += 4
        if event not in NO_SESSION_EVENTS:
            length = struct.unpack_from(">I", data, offset)[0]
            offset += 4
            session_id = data[offset : offset + length].decode("utf-8")
            offset += length
        if event in CONNECT_ID_EVENTS:
            length = struct.unpack_from(">I", data, offset)[0]
            offset += 4
            connect_id = data[offset : offset + length].decode("utf-8")
            offset += length

    error_code: int | None = None
    if message_type == MESSAGE_ERROR:
        error_code = struct.unpack_from(">I", data, offset)[0]
        offset += 4

    payload_size = struct.unpack_from(">I", data, offset)[0]
    offset += 4
    payload = data[offset : offset + payload_size]
    if len(payload) != payload_size:
        raise RuntimeError(f"豆包响应负载不完整: {len(payload)}/{payload_size}")
    if compression == 1:
        payload = gzip.decompress(payload)

    return ServerFrame(
        message_type=message_type,
        flags=flags,
        serialization=serialization,
        compression=compression,
        event=event,
        session_id=session_id,
        connect_id=connect_id,
        error_code=error_code,
        payload=payload,
    )


def decode_json_payload(frame: ServerFrame) -> dict[str, Any]:
    if not frame.payload or frame.message_type == MESSAGE_AUDIO_SERVER:
        return {}
    try:
        return json.loads(frame.payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {}


def frame_error(frame: ServerFrame) -> RuntimeError:
    payload = decode_json_payload(frame)
    message = payload.get("message") or payload.get("error") or frame.payload.decode(
        "utf-8", errors="replace"
    )
    return RuntimeError(
        f"豆包 API 错误 event={frame.event} code={frame.error_code}: {message}"
    )


def extract_text(payload: dict[str, Any]) -> str:
    if payload.get("content"):
        return str(payload["content"])
    if payload.get("text"):
        return str(payload["text"])
    asr_info = payload.get("asr_info") or {}
    if asr_info.get("text"):
        return str(asr_info["text"])
    results = payload.get("results") or []
    if results and results[0].get("text"):
        return str(results[0]["text"])
    return ""


async def receive_expected(
    websocket: websockets.ClientConnection, expected_event: int
) -> ServerFrame:
    while True:
        raw_message = await websocket.recv()
        if not isinstance(raw_message, bytes):
            raise RuntimeError(f"豆包返回了非二进制消息: {raw_message}")
        frame = parse_server_frame(raw_message)
        if frame.message_type == MESSAGE_ERROR:
            raise frame_error(frame)
        if frame.event == expected_event:
            return frame
        if frame.event in (EVENT_CONNECTION_FAILED, EVENT_SESSION_FAILED):
            raise frame_error(frame)


async def send_microphone(
    websocket: websockets.ClientConnection,
    microphone: PcmMicrophone,
    session_id: str,
) -> None:
    while True:
        audio = await microphone.read()
        await websocket.send(
            build_event_frame(
                MESSAGE_AUDIO_CLIENT,
                EVENT_TASK_AUDIO,
                session_id,
                audio,
                SERIALIZATION_NONE,
            )
        )


async def receive_events(
    websocket: websockets.ClientConnection,
    player: PcmPlayer,
    session_id: str,
) -> None:
    response_started_at: float | None = None
    first_audio_seen = False
    responding = False
    interrupt_sent = False

    async for raw_message in websocket:
        if not isinstance(raw_message, bytes):
            print(f"[服务端文本] {raw_message}")
            continue

        frame = parse_server_frame(raw_message)
        if frame.message_type == MESSAGE_ERROR:
            raise frame_error(frame)

        event = frame.event
        payload = decode_json_payload(frame)
        text = extract_text(payload)

        if event == EVENT_ASR_INFO:
            if responding and not interrupt_sent:
                dropped_ms = player.clear()
                await websocket.send(build_json_frame(EVENT_CLIENT_INTERRUPT, session_id, {}))
                interrupt_sent = True
                print(f"\n[打断] ASR 检测到用户说话，清除 {dropped_ms} ms 待播放音频")
        elif event == EVENT_ASR_RESPONSE and text:
            print(f"\r[用户转写] {text}", end="", flush=True)
        elif event == EVENT_ASR_ENDED:
            response_started_at = time.perf_counter()
            first_audio_seen = False
            interrupt_sent = False
            print(f"\n[用户完整转写] {text}")
        elif event == EVENT_TTS_STARTED:
            responding = True
            print("[助手] 开始生成语音")
        elif event == EVENT_TTS_AUDIO:
            audio = frame.payload
            if not audio and payload.get("audio"):
                audio = base64.b64decode(payload["audio"])
            if response_started_at is not None and not first_audio_seen:
                latency_ms = int((time.perf_counter() - response_started_at) * 1000)
                print(f"[首包延迟] {latency_ms} ms")
                first_audio_seen = True
            player.enqueue(audio)
        elif event == EVENT_TTS_FINISHED:
            responding = False
            print(f"[语音结束] 本地缓冲={player.queued_ms} ms")
        elif event == EVENT_CHAT_RESPONSE and text:
            print(f"[助手文本] {text}")
        elif event == EVENT_CHAT_ENDED and text:
            print(f"[助手完整文本] {text}")
        elif event == EVENT_SESSION_FAILED:
            raise frame_error(frame)


async def main() -> None:
    load_script_env(__file__)
    api_key = require_env("DOUBAO_API_KEY")

    resource_id = os.getenv("DOUBAO_REALTIME_RESOURCE_ID", "volc.speech.dialog").strip()
    model = os.getenv("DOUBAO_REALTIME_MODEL", "1.2.1.1").strip()
    speaker = os.getenv(
        "DOUBAO_REALTIME_SPEAKER",
        "zh_female_vv_jupiter_bigtts",
    ).strip()
    end_smooth_window_ms = int(
        os.getenv("DOUBAO_END_SMOOTH_WINDOW_MS", "800")
    )
    output_format = os.getenv(
        "DOUBAO_REALTIME_OUTPUT_FORMAT",
        "pcm_s16le",
    ).strip()
    system_role = os.getenv(
        "DOUBAO_REALTIME_SYSTEM_ROLE",
        "你是一名自然、简洁的中文语音助手。",
    ).strip()
    speaking_style = os.getenv("DOUBAO_REALTIME_SPEAKING_STYLE", "自然、温和、简洁").strip()
    url = os.getenv(
        "DOUBAO_REALTIME_URL",
        "wss://openspeech.bytedance.com/api/v3/realtime/dialogue",
    ).strip()

    connect_id = str(uuid.uuid4())
    headers = {
        "X-Api-Key": api_key,
        "X-Api-Resource-Id": resource_id,
        "X-Api-Connect-Id": connect_id,
        "X-Api-Request-Id": connect_id,
    }

    async with websockets.connect(
        url,
        additional_headers=headers,
        max_size=None,
        ping_interval=20,
        ping_timeout=20,
    ) as websocket:
        await websocket.send(
            build_event_frame(
                MESSAGE_FULL_CLIENT,
                EVENT_START_CONNECTION,
                payload=b"{}",
                serialization=SERIALIZATION_JSON,
            )
        )
        await receive_expected(websocket, EVENT_CONNECTION_STARTED)

        requested_session_id = str(uuid.uuid4())
        start_payload = {
            "asr": {
                "language": "zh-CN",
                "audio_info": {
                    "format": "pcm",
                    "sample_rate": INPUT_RATE,
                    "channel": 1,
                },
                "extra": {
                    "end_smooth_window_ms": end_smooth_window_ms,
                    "enable_custom_vad": True,
                    "enable_asr_twopass": False,
                },
            },
            "tts": {
                "speaker": speaker,
                "audio_config": {
                    "channel": 1,
                    "format": output_format,
                    "sample_rate": OUTPUT_RATE,
                },
            },
            "dialog": {
                "system_role": system_role,
                "speaking_style": speaking_style,
                "extra": {
                    "model": model,
                    "enable_loudness_norm": True,
                },
            },
        }
        await websocket.send(
            build_event_frame(
                MESSAGE_FULL_CLIENT,
                EVENT_START_SESSION,
                requested_session_id,
                json.dumps(
                    start_payload,
                    ensure_ascii=False,
                    separators=(",", ":"),
                ).encode("utf-8"),
                SERIALIZATION_JSON,
            )
        )
        session_frame = await receive_expected(websocket, EVENT_SESSION_STARTED)
        session_id = session_frame.session_id or requested_session_id
        print(
            f"[连接] 豆包 S2S-O model={model}，"
            f"输入 PCM16 16 kHz，输出 PCM16 24 kHz，session={session_id}"
        )

        try:
            with PcmMicrophone(INPUT_RATE) as microphone, PcmPlayer(OUTPUT_RATE) as player:
                await run_until_one_stops(
                    send_microphone(websocket, microphone, session_id),
                    receive_events(websocket, player, session_id),
                )
        finally:
            with contextlib.suppress(ConnectionClosed):
                await websocket.send(build_json_frame(EVENT_FINISH_SESSION, session_id, {}))
            with contextlib.suppress(ConnectionClosed):
                await websocket.send(
                    build_event_frame(
                        MESSAGE_FULL_CLIENT,
                        EVENT_FINISH_CONNECTION,
                        payload=b"{}",
                        serialization=SERIALIZATION_JSON,
                    )
                )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[结束] 用户停止测试")
    except Exception as exc:
        print(f"\n[错误] {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
