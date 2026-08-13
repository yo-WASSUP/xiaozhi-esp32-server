import asyncio
import base64
import gzip
import json
import os
import re
import struct
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

import opuslib_next
import websockets

from core.handle.sendAudioHandle import send_llm_message, send_tts_message


TAG = __name__

ANAN_IDENTITY_GUARD = (
    '你的名字是“安安”，你是患者身边的安宁疗护陪伴助手。'
    '当用户询问你是谁、使用了什么模型或来自哪个平台时，始终以“安安”的身份自然回答。'
    '不要自称豆包、字节跳动、语言模型或其他产品名称。'
)

ANAN_ROBOT_CAPABILITY_GUARD = """
## 真实身份与能力边界（最高优先级）
你是通过患者身边的陪伴机器人与患者语音对话的“安安”。你当前只能倾听、说话、安慰、陪聊和给出简单的口头提醒。

你没有可以拿取或操作物品的手，也不能离开当前位置去完成现实任务。你不能倒水、取物、送物、喂水喂药、扶人或给患者翻身，不能开关门窗、灯光、空调或其他现实物品。你不能自行打电话、发消息、通知医护人员或家属。你没有看见、触摸或确认周围环境和患者身体状况的能力。

绝对不要编造现实动作、感知或执行结果。禁止说“我去帮您……”“我来给您……”“我已经通知……”“我看到……”等超出上述能力的表述。用户要求你完成现实动作时，用一句话坦诚说明你做不到，再建议请身边的家属或医护人员帮忙。

示例：
- 患者说“我口渴了”，回答“听起来您有些口渴。我没法给您倒水，请您叫一下身边的家属或医护人员，好吗？”
- 患者说“帮我翻个身”，回答“我没法扶您翻身，这需要请医护人员来帮您，先别自己用力。”
- 患者说“你陪我说说话”，回答“好的，我在这里听您说。”

当能力是否存在或现实动作是否成功不确定时，一律按“做不到、未执行”处理，不得猜测。
""".strip()

EMOTION_CONTROL_PATTERN = re.compile(
    r"<!--\s*emotion\s*:\s*[\s\S]*?-->",
    re.IGNORECASE,
)


def clean_realtime_text(text: str) -> str:
    return EMOTION_CONTROL_PATTERN.sub("", str(text or "")).strip()


def split_pcm_frames(pcm: bytes, sample_rate: int = 16000, frame_ms: int = 20):
    frame_bytes = sample_rate * frame_ms // 1000 * 2
    return [
        pcm[offset : offset + frame_bytes]
        for offset in range(0, len(pcm), frame_bytes)
    ]


def build_system_role(connection_prompt: str, configured_role: str) -> str:
    parts = [
        str(connection_prompt or "").strip(),
        str(configured_role or "").strip(),
        ANAN_IDENTITY_GUARD,
        ANAN_ROBOT_CAPABILITY_GUARD,
    ]
    return "\n\n".join(part for part in parts if part)

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


def build_json_frame(event: int, session_id: str, body: dict) -> bytes:
    payload = json.dumps(
        {**body, "session_id": session_id},
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

    event = None
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

    error_code = None
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


def decode_json_payload(frame: ServerFrame) -> dict:
    if not frame.payload or frame.message_type == MESSAGE_AUDIO_SERVER:
        return {}
    try:
        return json.loads(frame.payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {}


def extract_text(payload: dict) -> str:
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


async def receive_expected(upstream, expected_event: int) -> ServerFrame:
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


def _read_env_file(path: str) -> dict[str, str]:
    if not path:
        return {}
    candidate = Path(path)
    if not candidate.is_absolute():
        project_dir = Path(__file__).resolve().parents[3]
        candidate = project_dir / candidate
    if not candidate.exists():
        return {}

    values = {}
    for raw_line in candidate.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip("\"'")
    return values


class DoubaoS2SClient:
    input_rate = 16000
    output_rate = 24000
    frame_size = 960

    def __init__(self, conn, config: dict):
        self.conn = conn
        self.config = config or {}
        file_values = _read_env_file(self.config.get("api_key_env_file", ""))
        self.api_key = (
            os.getenv("DOUBAO_API_KEY")
            or self.config.get("api_key", "")
            or file_values.get("DOUBAO_API_KEY", "")
        ).strip()
        self.resource_id = self.config.get(
            "resource_id", "volc.speech.dialog"
        ).strip()
        self.model = self.config.get("model", "1.2.1.1").strip()
        self.speaker = self.config.get(
            "speaker", "zh_female_vv_jupiter_bigtts"
        ).strip()
        self.url = self.config.get(
            "url", "wss://openspeech.bytedance.com/api/v3/realtime/dialogue"
        ).strip()
        self.output_format = self.config.get("output_format", "pcm_s16le").strip()
        self.end_smooth_window_ms = int(
            self.config.get("end_smooth_window_ms", 800)
        )
        configured_role = (
            self.config.get("system_role")
            or "你是安安，一名温暖、耐心、简洁的中文陪伴助手。"
        )
        connection_prompt = (
            getattr(self.conn, "prompt", "")
            if self.config.get("inherit_connection_prompt", True) is not False
            else ""
        )
        self.system_role = build_system_role(connection_prompt, configured_role)
        self.speaking_style = self.config.get(
            "speaking_style", "自然、温和、简洁，语速稍慢"
        ).strip()

        self.upstream = None
        self.session_id = ""
        self.run_task = None
        self.audio_queue = asyncio.Queue(maxsize=64)
        self.send_lock = asyncio.Lock()
        self.opus_decoder = opuslib_next.Decoder(self.input_rate, 1)
        self.active = False
        self.closed = False
        self.responding = False
        self.interrupt_sent = False
        self.user_text = ""
        self.assistant_chat_text = ""
        self.assistant_tts_text = ""
        self.assistant_finalized = False
        self.assistant_sent_text = ""

    def start(self):
        if self.run_task is None or self.run_task.done():
            self.run_task = asyncio.create_task(self._run())

    async def _run(self):
        if not self.api_key or self.api_key.startswith("你的"):
            await self._activate_fallback("未配置豆包端到端 API Key")
            return

        connect_id = str(uuid.uuid4())
        headers = {
            "X-Api-Key": self.api_key,
            "X-Api-Resource-Id": self.resource_id,
            "X-Api-Connect-Id": connect_id,
            "X-Api-Request-Id": connect_id,
        }
        try:
            self.upstream = await websockets.connect(
                self.url,
                additional_headers=headers,
                max_size=None,
                ping_interval=20,
                ping_timeout=20,
                open_timeout=10,
                close_timeout=3,
            )
            await self._send_frame(
                build_event_frame(
                    MESSAGE_FULL_CLIENT,
                    EVENT_START_CONNECTION,
                    payload=b"{}",
                    serialization=SERIALIZATION_JSON,
                )
            )
            await asyncio.wait_for(
                receive_expected(self.upstream, EVENT_CONNECTION_STARTED),
                timeout=10,
            )

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
            await self._send_frame(
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
            session_frame = await asyncio.wait_for(
                receive_expected(self.upstream, EVENT_SESSION_STARTED),
                timeout=10,
            )
            self.session_id = session_frame.session_id or requested_session_id
            self.active = True
            self.conn.logger.bind(tag=TAG).info(
                f"豆包端到端会话已连接: model={self.model}, speaker={self.speaker}"
            )
            await self._notify_mode("doubao_s2s")
            await self._run_streams()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            if not self.closed:
                self.conn.logger.bind(tag=TAG).error(f"豆包端到端会话失败: {exc}")
                await self._activate_fallback(str(exc))
        finally:
            self.active = False
            if self.upstream is not None:
                try:
                    await self.upstream.close()
                except Exception:
                    pass
                self.upstream = None

    async def _run_streams(self):
        sender = asyncio.create_task(self._send_audio_loop())
        receiver = asyncio.create_task(self._receive_loop())
        tasks = (sender, receiver)
        try:
            done, _ = await asyncio.wait(
                tasks,
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in done:
                task.result()
            if not self.closed:
                raise RuntimeError("豆包端到端连接已结束")
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    async def send_opus(self, opus_packet: bytes):
        if self.closed or self.conn.voice_mode != "doubao_s2s":
            return
        try:
            pcm = self.opus_decoder.decode(opus_packet, self.frame_size)
        except Exception as exc:
            self.conn.logger.bind(tag=TAG).warning(f"患者端 Opus 解码失败: {exc}")
            return
        self.conn.last_activity_time = time.time() * 1000
        for frame in split_pcm_frames(pcm, self.input_rate, 20):
            self._queue_input_pcm(frame)

    async def send_pcm(self, pcm: bytes):
        if self.closed or self.conn.voice_mode != "doubao_s2s" or not pcm:
            return
        if len(pcm) % 2:
            self.conn.logger.bind(tag=TAG).warning(
                f"患者端 PCM16 字节数无效: {len(pcm)}"
            )
            return
        self.conn.last_activity_time = time.time() * 1000
        self._queue_input_pcm(pcm)

    def _queue_input_pcm(self, pcm: bytes):
        try:
            self.audio_queue.put_nowait(pcm)
        except asyncio.QueueFull:
            try:
                self.audio_queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
            self.audio_queue.put_nowait(pcm)

    async def interrupt(self):
        if not self.active or not self.session_id or self.interrupt_sent:
            return
        self.interrupt_sent = True
        await self._send_frame(
            build_json_frame(EVENT_CLIENT_INTERRUPT, self.session_id, {})
        )
        await self._stop_client_playback()

    async def _send_audio_loop(self):
        while not self.closed:
            audio = await self.audio_queue.get()
            await self._send_frame(
                build_event_frame(
                    MESSAGE_AUDIO_CLIENT,
                    EVENT_TASK_AUDIO,
                    self.session_id,
                    audio,
                    SERIALIZATION_NONE,
                )
            )

    async def _receive_loop(self):
        async for raw_message in self.upstream:
            if not isinstance(raw_message, bytes):
                continue
            frame = parse_server_frame(raw_message)
            if frame.message_type == MESSAGE_ERROR:
                raise frame_error(frame)

            payload = decode_json_payload(frame)
            text = extract_text(payload)
            event = frame.event

            if event == EVENT_ASR_INFO:
                await self._send_vad(True)
                if self.responding and not self.interrupt_sent:
                    self.conn.logger.bind(tag=TAG).info(
                        "豆包ASRInfo确认用户开口，立即打断当前回答"
                    )
                    await self.interrupt()
                elif not self.responding:
                    await self._stop_client_playback()
            elif event == EVENT_ASR_RESPONSE:
                self.user_text = self._latest_hypothesis(self.user_text, text)
                await self._send_vad(True)
            elif event == EVENT_ASR_ENDED:
                self.user_text = self._latest_hypothesis(self.user_text, text)
                await self._send_vad(False)
                if self.user_text:
                    await self._send_text("stt", self.user_text)
                self.user_text = ""
                self.interrupt_sent = False
            elif event == EVENT_TTS_STARTED:
                self.responding = True
                self.interrupt_sent = False
                self.assistant_chat_text = ""
                self.assistant_tts_text = ""
                self.assistant_finalized = False
                self.assistant_sent_text = ""
                self.conn.client_abort = False
                self.conn.client_is_speaking = True
                self.conn.sentence_id = uuid.uuid4().hex
                await send_tts_message(self.conn, "start")
            elif event == EVENT_TTS_AUDIO:
                audio = frame.payload
                if not audio and payload.get("audio"):
                    audio = base64.b64decode(payload["audio"])
                await self._send_pcm(audio, end_of_stream=False)
            elif event == EVENT_CHAT_RESPONSE and text:
                self.assistant_chat_text = self._merge_text(
                    self.assistant_chat_text,
                    text,
                )
            elif event == EVENT_TTS_SEGMENT_END and text:
                self.assistant_tts_text = self._merge_text(
                    self.assistant_tts_text,
                    text,
                )
            elif event == EVENT_CHAT_ENDED:
                if text:
                    self.assistant_chat_text = self._merge_text(
                        self.assistant_chat_text,
                        text,
                    )
                await self._finalize_assistant_text()
            elif event == EVENT_TTS_FINISHED:
                await self._finalize_assistant_text()
                self.responding = False
                if self.conn.client_abort:
                    self.conn.clearSpeakStatus()
                else:
                    await self._finish_client_playback()
            elif event == EVENT_SESSION_FAILED:
                raise frame_error(frame)

    async def _send_pcm(self, pcm: bytes, end_of_stream: bool):
        del end_of_stream
        if self.conn.client_abort:
            return
        if pcm:
            await self.conn.websocket.send(pcm)

    async def _finish_client_playback(self):
        await self.conn.websocket.send(
            json.dumps(
                {
                    "type": "tts",
                    "state": "stop",
                    "drain": True,
                    "session_id": self.conn.session_id,
                }
            )
        )
        self.conn.clearSpeakStatus()

    async def _finalize_assistant_text(self):
        clean_text = self._select_display_text(
            getattr(self, "assistant_chat_text", ""),
            getattr(self, "assistant_tts_text", ""),
        )
        if (
            clean_text
            and clean_text != getattr(self, "assistant_sent_text", "")
            and not self.conn.client_abort
        ):
            await send_llm_message(self.conn, clean_text)
            self.assistant_sent_text = clean_text
            self.assistant_finalized = True

    async def _send_text(self, message_type: str, text: str):
        clean_text = clean_realtime_text(text)
        if not clean_text:
            return
        await self.conn.websocket.send(
            json.dumps(
                {
                    "type": message_type,
                    "text": clean_text,
                    "session_id": self.conn.session_id,
                },
                ensure_ascii=False,
            )
        )

    async def _send_vad(self, active: bool):
        await self.conn.websocket.send(
            json.dumps(
                {
                    "type": "vad",
                    "active": active,
                    "source": "doubao_s2s",
                    "session_id": self.conn.session_id,
                },
                ensure_ascii=False,
            )
        )

    async def _stop_client_playback(self):
        self.conn.client_abort = True
        if (
            hasattr(self.conn, "audio_rate_controller")
            and self.conn.audio_rate_controller
        ):
            self.conn.audio_rate_controller.reset()
        await self.conn.websocket.send(
            json.dumps(
                {
                    "type": "tts",
                    "state": "stop",
                    "session_id": self.conn.session_id,
                }
            )
        )
        self.conn.clearSpeakStatus()

    async def _activate_fallback(self, reason: str):
        self.active = False
        self.conn.voice_mode = "cascade"
        await self._notify_mode("cascade", reason)

    async def _notify_mode(self, mode: str, reason: str = ""):
        try:
            await self.conn.websocket.send(
                json.dumps(
                    {
                        "type": "voice_mode",
                        "mode": mode,
                        "requested_mode": "doubao_s2s",
                        "reason": reason,
                        "session_id": self.conn.session_id,
                    },
                    ensure_ascii=False,
                )
            )
        except Exception:
            pass

    async def _send_frame(self, frame: bytes):
        if self.upstream is None:
            raise RuntimeError("豆包端到端连接尚未建立")
        async with self.send_lock:
            await self.upstream.send(frame)

    @staticmethod
    def _latest_hypothesis(current: str, incoming: str) -> str:
        latest = str(incoming or "").strip()
        return latest or current

    @staticmethod
    def _merge_text(current: str, incoming: str) -> str:
        if not incoming:
            return current
        if not current:
            return incoming
        if incoming.startswith(current):
            return incoming
        if current in incoming:
            return incoming
        if incoming in current:
            return current
        max_overlap = min(len(current), len(incoming))
        for overlap in range(max_overlap, 0, -1):
            if current[-overlap:] == incoming[:overlap]:
                return current + incoming[overlap:]
        return current + incoming

    @staticmethod
    def _select_display_text(chat_text: str, tts_text: str) -> str:
        chat = clean_realtime_text(chat_text)
        tts = clean_realtime_text(tts_text)
        if not chat:
            return tts
        if not tts:
            return chat
        if chat in tts:
            return tts
        if tts in chat:
            return chat
        return chat if len(chat) >= len(tts) else tts

    async def close(self):
        if self.closed:
            return
        self.closed = True
        if self.active and self.upstream is not None and self.session_id:
            try:
                await self._send_frame(
                    build_json_frame(EVENT_FINISH_SESSION, self.session_id, {})
                )
                await self._send_frame(
                    build_event_frame(
                        MESSAGE_FULL_CLIENT,
                        EVENT_FINISH_CONNECTION,
                        payload=b"{}",
                        serialization=SERIALIZATION_JSON,
                    )
                )
            except Exception:
                pass
        if self.run_task and not self.run_task.done():
            self.run_task.cancel()
            try:
                await self.run_task
            except asyncio.CancelledError:
                pass
        if self.upstream is not None:
            try:
                await self.upstream.close()
            except Exception:
                pass
            self.upstream = None
