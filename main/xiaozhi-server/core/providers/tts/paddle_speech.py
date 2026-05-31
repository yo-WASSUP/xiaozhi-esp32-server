import io
import wave
import json
import base64
import asyncio
import time
import websockets
import numpy as np
from datetime import datetime
from config.logger import setup_logging
from core.providers.tts.base import TTSProviderBase



TAG = __name__
logger = setup_logging()


class TTSProvider(TTSProviderBase):
    def __init__(self, config, delete_audio_file):
        super().__init__(config, delete_audio_file)
        self.url = config.get("url", "ws://192.168.1.10:8092/paddlespeech/tts/streaming")
        self.protocol = config.get("protocol", "websocket")
        
        if config.get("private_voice"):
            self.spk_id = int(config.get("private_voice"))
        else:
            self.spk_id = int(config.get("spk_id", "0"))

        speed = config.get("speed", 1.0)
        self.speed = float(speed) if speed else 1.0
        
        volume = config.get("volume", 1.0)
        self.volume = float(volume) if volume else 1.0
        
        self.delete_audio_file = config.get("delete_audio", True)
        if not self.delete_audio_file:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            save_path = config.get("save_path")
            if save_path:
                if not save_path.endswith('.wav'):
                    save_path = f"{save_path}_{timestamp}.wav"
                else:
                    other_path = save_path[:-4]
                    save_path = f"{other_path}_{timestamp}.wav"
                self.save_path = save_path
            else:
                self.save_path = f"./streaming_tts_{timestamp}.wav"
        else:
            self.save_path = None

    async def pcm_to_wav(self, pcm_data: bytes, sample_rate: int = 24000, num_channels: int = 1,
                         bits_per_sample: int = 16) -> bytes:
        """
        将 PCM 数据转换为 WAV 文件并返回字节数据
        :param pcm_data: PCM 数据（原始字节流）
        :param sample_rate: 音频采样率，默认为24000
        :param num_channels: 声道数，默认为单声道
        :param bits_per_sample: 每个样本的位数，默认为16
        :return: WAV 格式的字节数据
        """
        byte_data = np.frombuffer(pcm_data, dtype=np.int16)  # 16位PCM
        wav_io = io.BytesIO()

        with wave.open(wav_io, "wb") as wav_file:
            wav_file.setnchannels(num_channels)
            wav_file.setsampwidth(bits_per_sample // 8)
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(byte_data.tobytes())

        return wav_io.getvalue()

    async def text_to_speak(self, text, output_file):
        if self.protocol == "websocket":
            return await self.text_streaming(text, output_file)
        else:
            raise ValueError("Unsupported protocol. Please use 'websocket' or 'http'.")

    async def text_streaming(self, text, output_file):
        try:
            request_started_at = time.time()
            first_audio_at = None
            # 使用 websockets 异步连接到 WebSocket 服务器
            async with websockets.connect(self.url) as ws:
                # 发送开始请求
                start_request = {
                    "task": "tts",
                    "signal": "start"
                }
                await ws.send(json.dumps(start_request))

                # 接收开始响应并提取 session_id
                start_response = await ws.recv()
                start_response = json.loads(start_response)  # 解析 JSON 响应
                if start_response.get("status") != 0:
                    raise Exception(f"连接失败: {start_response.get('signal')}")

                session_id = start_response.get("session")

                # 发送待合成的文本数据
                data_request = {
                    "text": text,
                    "spk_id": self.spk_id,
                }
                await ws.send(json.dumps(data_request))

                audio_chunks = b""
                timeout_seconds = 60  # 设置超时
                try:
                    while True:
                        response = await asyncio.wait_for(ws.recv(), timeout=timeout_seconds)
                        response = json.loads(response)  # 解析 JSON 响应
                        status = response.get("status")

                        if status == 2:  # 最后一个数据包
                            break
                        else:
                            # 拼接音频数据（base64 编码的 PCM 数据）
                            audio = response.get("audio")
                            if audio:
                                if first_audio_at is None:
                                    first_audio_at = time.time()
                                audio_chunks += base64.b64decode(audio)
                except asyncio.TimeoutError:
                    raise Exception(f"WebSocket 超时：等待音频数据超过 {timeout_seconds} 秒")

                # 将拼接后的 PCM 数据转换为 WAV 格式
                synthesis_finished_at = time.time()
                wav_data = await self.pcm_to_wav(audio_chunks)
                wav_ready_at = time.time()

                # 结束请求
                end_request = {
                    "task": "tts",
                    "signal": "end",
                    "session": session_id  # 会话 ID 必须与开始请求中的一致
                }
                await ws.send(json.dumps(end_request))

                # 接收结束响应避免服务抛出异常
                await ws.recv()

                first_audio_ms = (
                    (first_audio_at - request_started_at) * 1000
                    if first_audio_at
                    else None
                )
                synthesis_ms = (synthesis_finished_at - request_started_at) * 1000
                total_ms = (wav_ready_at - request_started_at) * 1000
                duration_s = len(audio_chunks) / 2 / 24000 if audio_chunks else 0
                llm_to_first_ms = None
                if (
                    getattr(self, "conn", None)
                    and getattr(self.conn, "llm_first_token_time", None)
                    and first_audio_at
                ):
                    llm_to_first_ms = (
                        first_audio_at - self.conn.llm_first_token_time
                    ) * 1000

                latency_parts = []
                if first_audio_ms is not None:
                    latency_parts.append(f"首包: {first_audio_ms:.0f}ms")
                if llm_to_first_ms is not None:
                    latency_parts.append(
                        f"LLM首包到TTS首包: {llm_to_first_ms:.0f}ms"
                    )
                latency_parts.extend(
                    [
                        f"合成: {synthesis_ms:.0f}ms",
                        f"总耗时: {total_ms:.0f}ms",
                        f"音频时长: {duration_s:.2f}s",
                    ]
                )
                logger.bind(tag=TAG).info(
                    f"【PaddleSpeechTTS性能】{', '.join(latency_parts)}, 文本: {(text or '')[:20]}..."
                )

                # 根据配置决定是否保存文件
                if not self.delete_audio_file and self.save_path:
                    with open(self.save_path, "wb") as f:
                        f.write(wav_data)
                    logger.bind(tag=TAG).info(f"音频文件已保存到: {self.save_path}")
                
                # 返回或保存音频数据
                if output_file:
                    with open(output_file, "wb") as file_to_save:
                        file_to_save.write(wav_data)
                else:
                    return wav_data

        except Exception as e:
            raise Exception(f"Error during TTS WebSocket request: {e} while processing text: {text}")
