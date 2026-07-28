from __future__ import annotations

import asyncio
import base64
import gzip
import json
import os
import struct
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import websockets
from aiohttp import web
from dotenv import dotenv_values


SUITE_ROOT = Path(__file__).resolve().parents[1]


PROVIDERS = {
    "openai": {
        "name": "GPT Realtime 2.1",
        "folder": "gpt-realtime-2.1",
        "input_rate": 24_000,
        "output_rate": 24_000,
    },
    "qwen": {
        "name": "Qwen3.5 Omni Realtime",
        "folder": "qwen3.5-omni-realtime",
        "input_rate": 16_000,
        "output_rate": 24_000,
    },
    "doubao": {
        "name": "Doubao S2S-O",
        "folder": "doubao-s2s-o",
        "input_rate": 16_000,
        "output_rate": 24_000,
    },
}


class ProviderConfigError(RuntimeError):
    pass


def load_provider_env(provider: str) -> dict[str, str]:
    folder = PROVIDERS[provider]["folder"]
    file_values = {
        key: value or ""
        for key, value in dotenv_values(SUITE_ROOT / folder / ".env").items()
    }
    return {**file_values, **os.environ}


def required(config: dict[str, str], name: str) -> str:
    value = config.get(name, "").strip()
    if not value:
        folder = PROVIDERS_BY_ENV[name]
        raise ProviderConfigError(f"缺少 {name}，请填写 {folder}\\.env")
    return value


PROVIDERS_BY_ENV = {
    "OPENAI_API_KEY": "gpt-realtime-2.1",
    "DASHSCOPE_API_KEY": "qwen3.5-omni-realtime",
    "QWEN_WORKSPACE_ID": "qwen3.5-omni-realtime",
    "DOUBAO_API_KEY": "doubao-s2s-o",
}


def provider_statuses() -> list[dict[str, Any]]:
    statuses: list[dict[str, Any]] = []
    for provider, meta in PROVIDERS.items():
        config = load_provider_env(provider)
        if provider == "openai":
            configured = bool(config.get("OPENAI_API_KEY", "").strip())
            model = config.get("OPENAI_REALTIME_MODEL", "gpt-realtime-2.1")
        elif provider == "qwen":
            has_endpoint = bool(
                config.get("QWEN_WORKSPACE_ID", "").strip()
                or config.get("QWEN_REALTIME_URL", "").strip()
            )
            configured = bool(config.get("DASHSCOPE_API_KEY", "").strip()) and has_endpoint
            model = config.get("QWEN_REALTIME_MODEL", "qwen3.5-omni-plus-realtime")
        else:
            configured = bool(config.get("DOUBAO_API_KEY", "").strip())
            model = config.get("DOUBAO_REALTIME_MODEL", "1.2.1.1")

        statuses.append(
            {
                "id": provider,
                "name": meta["name"],
                "configured": configured,
                "model": model.strip(),
                "input_rate": meta["input_rate"],
                "output_rate": meta["output_rate"],
            }
        )
    return statuses


class BrowserBridge:
    def __init__(self, websocket: web.WebSocketResponse) -> None:
        self.websocket = websocket
        self._send_lock = asyncio.Lock()
        self.in_speech = False
        self.speech_started_at: float | None = None
        self.turn_ended_at: float | None = None
        self.first_audio_sent = False
        self.response_started_at: float | None = None

    async def send_json(self, event_type: str, **data: Any) -> None:
        if self.websocket.closed:
            return
        async with self._send_lock:
            if not self.websocket.closed:
                await self.websocket.send_json({"type": event_type, **data})

    async def ready(
        self,
        provider: str,
        model: str,
        input_rate: int,
        output_rate: int,
    ) -> None:
        await self.send_json(
            "ready",
            provider=provider,
            model=model,
            input_rate=input_rate,
            output_rate=output_rate,
        )

    async def status(self, state: str, detail: str = "") -> None:
        await self.send_json("status", state=state, detail=detail)

    async def speech_started(self) -> None:
        if self.in_speech:
            return
        self.in_speech = True
        self.speech_started_at = time.perf_counter()
        self.turn_ended_at = None
        self.first_audio_sent = False
        await self.send_json("speech_started")

    async def speech_stopped(self) -> None:
        now = time.perf_counter()
        utterance_ms = None
        if self.speech_started_at is not None:
            utterance_ms = int((now - self.speech_started_at) * 1000)
        self.in_speech = False
        self.turn_ended_at = now
        self.first_audio_sent = False
        await self.send_json("speech_stopped", utterance_ms=utterance_ms)

    async def transcript(
        self,
        role: str,
        text: str,
        *,
        final: bool,
        delta: bool = False,
    ) -> None:
        if text:
            await self.send_json(
                "transcript",
                role=role,
                text=text,
                final=final,
                delta=delta,
            )

    async def response_started(self) -> None:
        self.response_started_at = time.perf_counter()
        await self.send_json("response_started")

    async def send_audio(self, audio: bytes) -> None:
        if not audio or self.websocket.closed:
            return
        if not self.first_audio_sent:
            self.first_audio_sent = True
            if self.turn_ended_at is not None:
                first_audio_ms = int((time.perf_counter() - self.turn_ended_at) * 1000)
                await self.send_json("latency", first_audio_ms=first_audio_ms)
        async with self._send_lock:
            if not self.websocket.closed:
                await self.websocket.send_bytes(audio)

    async def response_done(self, status: str = "completed") -> None:
        response_ms = None
        if self.turn_ended_at is not None:
            response_ms = int((time.perf_counter() - self.turn_ended_at) * 1000)
        await self.send_json(
            "response_done",
            status=status,
            response_ms=response_ms,
        )


async def run_tasks(*coroutines: Any) -> None:
    tasks = [asyncio.create_task(coro) for coro in coroutines]
    try:
        done, _ = await asyncio.wait(
            tasks,
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in done:
            task.result()
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


class OpenAIProvider:
    provider_id = "openai"
    input_rate = 24_000
    output_rate = 24_000

    def __init__(self) -> None:
        config = load_provider_env(self.provider_id)
        self.api_key = required(config, "OPENAI_API_KEY")
        self.model = config.get("OPENAI_REALTIME_MODEL", "gpt-realtime-2.1").strip()
        self.voice = config.get("OPENAI_REALTIME_VOICE", "marin").strip()
        self.instructions = config.get(
            "OPENAI_REALTIME_INSTRUCTIONS",
            "你是一名自然、简洁、有同理心的中文语音助手。",
        ).strip()

    async def run(
        self,
        audio_queue: asyncio.Queue[bytes],
        bridge: BrowserBridge,
    ) -> None:
        url = f"wss://api.openai.com/v1/realtime?model={self.model}"
        async with websockets.connect(
            url,
            additional_headers={"Authorization": f"Bearer {self.api_key}"},
            max_size=None,
            ping_interval=20,
            ping_timeout=20,
        ) as upstream:
            await upstream.send(
                json.dumps(
                    {
                        "type": "session.update",
                        "session": {
                            "type": "realtime",
                            "model": self.model,
                            "output_modalities": ["audio"],
                            "instructions": self.instructions,
                            "audio": {
                                "input": {
                                    "format": {
                                        "type": "audio/pcm",
                                        "rate": self.input_rate,
                                    },
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
                                        "rate": self.output_rate,
                                    },
                                    "voice": self.voice,
                                },
                            },
                        },
                    },
                    ensure_ascii=False,
                )
            )
            await self._wait_until_ready(upstream)
            await bridge.ready(
                self.provider_id,
                self.model,
                self.input_rate,
                self.output_rate,
            )
            await run_tasks(
                self._send_audio(upstream, audio_queue),
                self._receive(upstream, bridge),
            )

    async def _wait_until_ready(self, upstream: websockets.ClientConnection) -> None:
        while True:
            event = json.loads(await upstream.recv())
            if event.get("type") == "session.updated":
                return
            if event.get("type") == "error":
                raise RuntimeError(
                    json.dumps(event.get("error", event), ensure_ascii=False)
                )

    async def _send_audio(
        self,
        upstream: websockets.ClientConnection,
        audio_queue: asyncio.Queue[bytes],
    ) -> None:
        while True:
            audio = await audio_queue.get()
            await upstream.send(
                json.dumps(
                    {
                        "type": "input_audio_buffer.append",
                        "audio": base64.b64encode(audio).decode("ascii"),
                    }
                )
            )

    async def _receive(
        self,
        upstream: websockets.ClientConnection,
        bridge: BrowserBridge,
    ) -> None:
        async for raw_message in upstream:
            if not isinstance(raw_message, str):
                continue
            event = json.loads(raw_message)
            event_type = event.get("type", "")
            if event_type == "input_audio_buffer.speech_started":
                await bridge.speech_started()
            elif event_type == "input_audio_buffer.speech_stopped":
                await bridge.speech_stopped()
            elif event_type == "conversation.item.input_audio_transcription.completed":
                await bridge.transcript(
                    "user",
                    event.get("transcript", ""),
                    final=True,
                )
            elif event_type == "response.created":
                await bridge.response_started()
            elif event_type == "response.output_audio.delta":
                await bridge.send_audio(base64.b64decode(event.get("delta", "")))
            elif event_type == "response.output_audio_transcript.delta":
                await bridge.transcript(
                    "assistant",
                    event.get("delta", ""),
                    final=False,
                    delta=True,
                )
            elif event_type == "response.output_audio_transcript.done":
                await bridge.transcript(
                    "assistant",
                    event.get("transcript", ""),
                    final=True,
                )
            elif event_type == "response.done":
                response = event.get("response", {})
                await bridge.response_done(response.get("status", "completed"))
            elif event_type == "error":
                raise RuntimeError(
                    json.dumps(event.get("error", event), ensure_ascii=False)
                )


class QwenProvider:
    provider_id = "qwen"
    input_rate = 16_000
    output_rate = 24_000

    def __init__(self) -> None:
        config = load_provider_env(self.provider_id)
        self.api_key = required(config, "DASHSCOPE_API_KEY")
        self.model = config.get(
            "QWEN_REALTIME_MODEL",
            "qwen3.5-omni-plus-realtime",
        ).strip()
        self.voice = config.get("QWEN_REALTIME_VOICE", "Ethan").strip()
        self.instructions = config.get(
            "QWEN_REALTIME_INSTRUCTIONS",
            "你是一名自然、简洁、有同理心的中文语音助手。",
        ).strip()
        self.vad_type = config.get("QWEN_VAD_TYPE", "server_vad").strip()
        self.vad_threshold = float(config.get("QWEN_VAD_THRESHOLD", "0.5"))
        self.vad_prefix_padding_ms = int(
            config.get("QWEN_VAD_PREFIX_PADDING_MS", "300")
        )
        self.vad_silence_ms = int(config.get("QWEN_VAD_SILENCE_MS", "500"))
        self.url = self._build_url(config)

    def _build_url(self, config: dict[str, str]) -> str:
        custom_url = config.get("QWEN_REALTIME_URL", "").strip()
        if custom_url:
            parts = urlsplit(custom_url)
            query = dict(parse_qsl(parts.query))
            query["model"] = self.model
            return urlunsplit(
                (parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment)
            )
        workspace_id = required(config, "QWEN_WORKSPACE_ID")
        return (
            f"wss://{workspace_id}.cn-beijing.maas.aliyuncs.com/"
            f"api-ws/v1/realtime?model={self.model}"
        )

    async def run(
        self,
        audio_queue: asyncio.Queue[bytes],
        bridge: BrowserBridge,
    ) -> None:
        async with websockets.connect(
            self.url,
            additional_headers={"Authorization": f"Bearer {self.api_key}"},
            max_size=None,
            ping_interval=20,
            ping_timeout=20,
        ) as upstream:
            await upstream.send(
                json.dumps(
                    {
                        "type": "session.update",
                        "session": {
                            "modalities": ["text", "audio"],
                            "voice": self.voice,
                            "instructions": self.instructions,
                            "input_audio_format": "pcm",
                            "output_audio_format": "pcm",
                            "input_audio_transcription": {
                                "model": "qwen3-asr-flash-realtime"
                            },
                            "turn_detection": {
                                "type": self.vad_type,
                                "threshold": self.vad_threshold,
                                "prefix_padding_ms": self.vad_prefix_padding_ms,
                                "silence_duration_ms": self.vad_silence_ms,
                            },
                        },
                    },
                    ensure_ascii=False,
                )
            )
            await self._wait_until_ready(upstream)
            await bridge.ready(
                self.provider_id,
                self.model,
                self.input_rate,
                self.output_rate,
            )
            await run_tasks(
                self._send_audio(upstream, audio_queue),
                self._receive(upstream, bridge),
            )

    async def _wait_until_ready(self, upstream: websockets.ClientConnection) -> None:
        while True:
            event = json.loads(await upstream.recv())
            if event.get("type") == "session.updated":
                return
            if event.get("type") == "error":
                raise RuntimeError(
                    json.dumps(event.get("error", event), ensure_ascii=False)
                )

    async def _send_audio(
        self,
        upstream: websockets.ClientConnection,
        audio_queue: asyncio.Queue[bytes],
    ) -> None:
        sequence = 0
        while True:
            audio = await audio_queue.get()
            sequence += 1
            await upstream.send(
                json.dumps(
                    {
                        "event_id": f"browser_{sequence}",
                        "type": "input_audio_buffer.append",
                        "audio": base64.b64encode(audio).decode("ascii"),
                    }
                )
            )

    async def _receive(
        self,
        upstream: websockets.ClientConnection,
        bridge: BrowserBridge,
    ) -> None:
        responding = False
        async for raw_message in upstream:
            if not isinstance(raw_message, str):
                continue
            event = json.loads(raw_message)
            event_type = event.get("type", "")
            if event_type == "input_audio_buffer.speech_started":
                await bridge.speech_started()
                if responding:
                    await upstream.send(json.dumps({"type": "response.cancel"}))
            elif event_type == "input_audio_buffer.speech_stopped":
                await bridge.speech_stopped()
            elif event_type == "conversation.item.input_audio_transcription.delta":
                text = f"{event.get('text', '')}{event.get('stash', '')}"
                await bridge.transcript("user", text, final=False)
            elif event_type == "conversation.item.input_audio_transcription.completed":
                text = event.get("transcript", event.get("text", ""))
                await bridge.transcript("user", text, final=True)
            elif event_type == "response.created":
                responding = True
                await bridge.response_started()
            elif event_type == "response.audio.delta":
                await bridge.send_audio(base64.b64decode(event.get("delta", "")))
            elif event_type == "response.audio_transcript.delta":
                await bridge.transcript(
                    "assistant",
                    event.get("delta", ""),
                    final=False,
                    delta=True,
                )
            elif event_type == "response.audio_transcript.done":
                await bridge.transcript(
                    "assistant",
                    event.get("transcript", ""),
                    final=True,
                )
            elif event_type == "response.done":
                responding = False
                response = event.get("response", {})
                await bridge.response_done(response.get("status", "completed"))
            elif event_type == "error":
                raise RuntimeError(
                    json.dumps(event.get("error", event), ensure_ascii=False)
                )


MESSAGE_FULL_CLIENT = 0x1
MESSAGE_AUDIO_CLIENT = 0x2
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
EVENT_TTS_SEGMENT_END = 351
EVENT_TTS_AUDIO = 352
EVENT_TTS_FINISHED = 359
EVENT_ASR_INFO = 450
EVENT_ASR_RESPONSE = 451
EVENT_ASR_ENDED = 459
EVENT_CLIENT_INTERRUPT = 515
EVENT_CHAT_RESPONSE = 550
EVENT_CHAT_ENDED = 559

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
    frame = bytearray(
        (0x11, (message_type << 4) | FLAG_WITH_EVENT, serialization << 4, 0)
    )
    frame.extend(struct.pack(">i", event))
    if event not in NO_SESSION_EVENTS:
        encoded_session = session_id.encode("utf-8")
        frame.extend(struct.pack(">I", len(encoded_session)))
        frame.extend(encoded_session)
    frame.extend(struct.pack(">I", len(payload)))
    frame.extend(payload)
    return bytes(frame)


def build_json_frame(event: int, session_id: str, body: dict[str, Any]) -> bytes:
    payload_body = {**body}
    payload_body.setdefault("session_id", session_id)
    payload = json.dumps(
        payload_body,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return build_event_frame(
        MESSAGE_FULL_CLIENT,
        event,
        session_id,
        payload,
        SERIALIZATION_JSON,
    )


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
    message = (
        payload.get("message")
        or payload.get("error")
        or frame.payload.decode("utf-8", errors="replace")
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
    upstream: websockets.ClientConnection,
    expected_event: int,
) -> ServerFrame:
    while True:
        raw_message = await upstream.recv()
        if not isinstance(raw_message, bytes):
            raise RuntimeError(f"豆包返回了非二进制消息: {raw_message}")
        frame = parse_server_frame(raw_message)
        if frame.message_type == MESSAGE_ERROR:
            raise frame_error(frame)
        if frame.event == expected_event:
            return frame
        if frame.event in (EVENT_CONNECTION_FAILED, EVENT_SESSION_FAILED):
            raise frame_error(frame)


class DoubaoProvider:
    provider_id = "doubao"
    input_rate = 16_000
    output_rate = 24_000

    def __init__(self) -> None:
        config = load_provider_env(self.provider_id)
        self.api_key = required(config, "DOUBAO_API_KEY")
        self.resource_id = config.get(
            "DOUBAO_REALTIME_RESOURCE_ID",
            "volc.speech.dialog",
        ).strip()
        self.model = config.get("DOUBAO_REALTIME_MODEL", "1.2.1.1").strip()
        self.speaker = config.get(
            "DOUBAO_REALTIME_SPEAKER",
            "zh_female_vv_jupiter_bigtts",
        ).strip()
        self.end_smooth_window_ms = int(
            config.get("DOUBAO_END_SMOOTH_WINDOW_MS", "800")
        )
        self.output_format = config.get(
            "DOUBAO_REALTIME_OUTPUT_FORMAT",
            "pcm_s16le",
        ).strip()
        self.system_role = config.get(
            "DOUBAO_REALTIME_SYSTEM_ROLE",
            "你是一名自然、简洁、有同理心的中文语音助手。",
        ).strip()
        self.speaking_style = config.get(
            "DOUBAO_REALTIME_SPEAKING_STYLE",
            "自然、温和、简洁",
        ).strip()
        self.url = config.get(
            "DOUBAO_REALTIME_URL",
            "wss://openspeech.bytedance.com/api/v3/realtime/dialogue",
        ).strip()

    async def run(
        self,
        audio_queue: asyncio.Queue[bytes],
        bridge: BrowserBridge,
    ) -> None:
        connect_id = str(uuid.uuid4())
        headers = {
            "X-Api-Key": self.api_key,
            "X-Api-Resource-Id": self.resource_id,
            "X-Api-Connect-Id": connect_id,
            "X-Api-Request-Id": connect_id,
        }

        async with websockets.connect(
            self.url,
            additional_headers=headers,
            max_size=None,
            ping_interval=20,
            ping_timeout=20,
        ) as upstream:
            await upstream.send(
                build_event_frame(
                    MESSAGE_FULL_CLIENT,
                    EVENT_START_CONNECTION,
                    payload=b"{}",
                    serialization=SERIALIZATION_JSON,
                )
            )
            await receive_expected(upstream, EVENT_CONNECTION_STARTED)

            requested_session_id = str(uuid.uuid4())
            start_payload = {
                "asr": {
                    "language": "zh-CN",
                    "audio_info": {
                        "format": "pcm",
                        "sample_rate": self.input_rate,
                        "channel": 1,
                    },
                    "extra": {
                        "end_smooth_window_ms": self.end_smooth_window_ms,
                        "enable_custom_vad": True,
                        "enable_asr_twopass": False,
                    },
                },
                "tts": {
                    "speaker": self.speaker,
                    "audio_config": {
                        "channel": 1,
                        "format": self.output_format,
                        "sample_rate": self.output_rate,
                    },
                },
                "dialog": {
                    "system_role": self.system_role,
                    "speaking_style": self.speaking_style,
                    "extra": {
                        "model": self.model,
                        "enable_loudness_norm": True,
                    },
                },
            }
            await upstream.send(
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
            session_frame = await receive_expected(upstream, EVENT_SESSION_STARTED)
            session_id = session_frame.session_id or requested_session_id
            await bridge.ready(
                self.provider_id,
                self.model,
                self.input_rate,
                self.output_rate,
            )
            try:
                await run_tasks(
                    self._send_audio(upstream, audio_queue, session_id),
                    self._receive(upstream, bridge, session_id),
                )
            finally:
                try:
                    await upstream.send(
                        build_json_frame(EVENT_FINISH_SESSION, session_id, {})
                    )
                    await upstream.send(
                        build_event_frame(
                            MESSAGE_FULL_CLIENT,
                            EVENT_FINISH_CONNECTION,
                            payload=b"{}",
                            serialization=SERIALIZATION_JSON,
                        )
                    )
                except websockets.ConnectionClosed:
                    pass

    async def _send_audio(
        self,
        upstream: websockets.ClientConnection,
        audio_queue: asyncio.Queue[bytes],
        session_id: str,
    ) -> None:
        while True:
            audio = await audio_queue.get()
            await upstream.send(
                build_event_frame(
                    MESSAGE_AUDIO_CLIENT,
                    EVENT_TASK_AUDIO,
                    session_id,
                    audio,
                    SERIALIZATION_NONE,
                )
            )

    async def _receive(
        self,
        upstream: websockets.ClientConnection,
        bridge: BrowserBridge,
        session_id: str,
    ) -> None:
        responding = False
        interrupt_sent = False
        assistant_text = ""
        assistant_finalized = False
        async for raw_message in upstream:
            if not isinstance(raw_message, bytes):
                continue
            frame = parse_server_frame(raw_message)
            if frame.message_type == MESSAGE_ERROR:
                raise frame_error(frame)
            payload = decode_json_payload(frame)
            text = extract_text(payload)
            event = frame.event

            if event == EVENT_ASR_INFO:
                await bridge.speech_started()
                if responding and not interrupt_sent:
                    await upstream.send(
                        build_json_frame(EVENT_CLIENT_INTERRUPT, session_id, {})
                    )
                    interrupt_sent = True
            elif event == EVENT_ASR_RESPONSE:
                await bridge.speech_started()
                await bridge.transcript("user", text, final=False)
            elif event == EVENT_ASR_ENDED:
                await bridge.speech_stopped()
                await bridge.transcript("user", text, final=True)
                interrupt_sent = False
            elif event == EVENT_TTS_STARTED:
                responding = True
                assistant_text = ""
                assistant_finalized = False
                await bridge.response_started()
            elif event == EVENT_TTS_AUDIO:
                audio = frame.payload
                if not audio and payload.get("audio"):
                    audio = base64.b64decode(payload["audio"])
                await bridge.send_audio(audio)
            elif event == EVENT_TTS_FINISHED:
                responding = False
                if assistant_text and not assistant_finalized:
                    await bridge.transcript(
                        "assistant",
                        assistant_text,
                        final=True,
                    )
                    assistant_finalized = True
                await bridge.response_done()
            elif event == EVENT_CHAT_RESPONSE and text:
                if text.startswith(assistant_text):
                    delta = text[len(assistant_text) :]
                    assistant_text = text
                elif assistant_text.endswith(text):
                    delta = ""
                else:
                    delta = text
                    assistant_text += text
                if delta:
                    await bridge.transcript(
                        "assistant",
                        delta,
                        final=False,
                        delta=True,
                    )
            elif event == EVENT_TTS_SEGMENT_END and text:
                if not assistant_text:
                    assistant_text = text
                    await bridge.transcript(
                        "assistant",
                        text,
                        final=False,
                        delta=True,
                    )
            elif event == EVENT_CHAT_ENDED:
                if text:
                    assistant_text = text
                if assistant_text:
                    await bridge.transcript(
                        "assistant",
                        assistant_text,
                        final=True,
                    )
                    assistant_finalized = True
            elif event == EVENT_SESSION_FAILED:
                raise frame_error(frame)


def create_provider(provider: str) -> OpenAIProvider | QwenProvider | DoubaoProvider:
    if provider == "openai":
        return OpenAIProvider()
    if provider == "qwen":
        return QwenProvider()
    if provider == "doubao":
        return DoubaoProvider()
    raise ProviderConfigError(f"不支持的接口: {provider}")
