import json
import gzip
import uuid
import asyncio
import time
import websockets
import opuslib_next
from core.providers.asr.base import ASRProviderBase
from config.logger import setup_logging
from core.providers.asr.dto.dto import InterfaceType

TAG = __name__
logger = setup_logging()


class ASRProvider(ASRProviderBase):
    def __init__(self, config, delete_audio_file):
        super().__init__()
        self.interface_type = InterfaceType.STREAM
        self.config = config
        self.text = ""
        self.decoder = opuslib_next.Decoder(16000, 1)
        self.asr_ws = None
        self.forward_task = None
        self.connect_lock = asyncio.Lock()
        self.stream_ready = False
        self.is_processing = False  # 添加处理状态标志

        # 配置参数
        self.appid = str(config.get("appid"))
        self.cluster = config.get("cluster")
        self.access_token = config.get("access_token")
        self.boosting_table_name = config.get("boosting_table_name", "")
        self.correct_table_name = config.get("correct_table_name", "")
        self.output_dir = config.get("output_dir", "tmp/")
        self.delete_audio_file = delete_audio_file

        # 火山引擎ASR配置
        enable_multilingual = config.get("enable_multilingual", False)
        self.enable_multilingual = False if str(enable_multilingual).lower() == 'false' else True
        if self.enable_multilingual:
            self.ws_url = "wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_nostream"
        else:
            self.ws_url = "wss://openspeech.bytedance.com/api/v3/sauc/bigmodel"
        self.ws_url = config.get("ws_url") or self.ws_url
        self.resource_id = config.get("resource_id", "volc.bigasr.sauc.duration")
        self.uid = config.get("uid", "streaming_asr_service")
        self.workflow = config.get(
            "workflow", "audio_in,resample,partition,vad,fe,decode,itn,nlu_punctuate"
        )
        self.result_type = config.get("result_type", "single")
        self.format = config.get("format", "pcm")
        self.codec = config.get("codec", "pcm")
        self.rate = config.get("sample_rate", 16000)
        # language参数仅在多语种模式(bigmodel_nostream)下有效
        self.language = config.get("language") if self.enable_multilingual else None
        self.bits = config.get("bits", 16)
        self.channel = config.get("channel", 1)
        self.auth_method = config.get("auth_method", "token")
        self.secret = config.get("secret", "access_secret")
        end_window_size = config.get("end_window_size")
        self.end_window_size = int(end_window_size) if end_window_size else 200

    async def open_audio_channels(self, conn):
        await super().open_audio_channels(conn)

    async def receive_audio(self, conn, audio, audio_have_voice):
        # 先调用父类方法处理基础逻辑
        await super().receive_audio(conn, audio, audio_have_voice)

        # 如果本次有声音，且之前没有建立连接
        if audio_have_voice and not self.stream_ready:
            await self.prepare_stream(conn)

        # 发送当前音频数据
        if self.asr_ws and self.is_processing and self.stream_ready:
            try:
                pcm_frame = self._decode_audio(conn, audio)
                payload = gzip.compress(pcm_frame)
                audio_request = bytearray(self.generate_audio_default_header())
                audio_request.extend(len(payload).to_bytes(4, "big"))
                audio_request.extend(payload)
                await self.asr_ws.send(audio_request)
            except Exception as e:
                logger.bind(tag=TAG).info(f"发送音频数据时发生错误: {e}")

    async def prepare_stream(self, conn):
        """提前建立流式 ASR；主页唤醒后调用，避免吞掉首句开头。"""
        async with self.connect_lock:
            if self.asr_ws is not None and self.is_processing and self.stream_ready:
                return True
            try:
                self.is_processing = True
                connect_started = time.monotonic()
                headers = self.token_auth() if self.auth_method == "token" else None
                logger.bind(tag=TAG).info(f"正在连接ASR服务: {self.resource_id}")
                self.asr_ws = await websockets.connect(
                    self.ws_url,
                    additional_headers=headers,
                    max_size=1000000000,
                    ping_interval=None,
                    ping_timeout=None,
                    close_timeout=10,
                )

                request_params = self.construct_request(str(uuid.uuid4()))
                payload_bytes = gzip.compress(json.dumps(request_params).encode())
                full_client_request = self.generate_header()
                full_client_request.extend(len(payload_bytes).to_bytes(4, "big"))
                full_client_request.extend(payload_bytes)
                await self.asr_ws.send(full_client_request)

                init_res = await asyncio.wait_for(self.asr_ws.recv(), timeout=10)
                result = self.parse_response(init_res)
                if "code" in result and result["code"] != 1000:
                    error = result.get("payload_msg", {}).get("error", "未知错误")
                    raise RuntimeError(f"ASR服务初始化失败: {error}")
                self.stream_ready = True
                logger.bind(tag=TAG).debug(
                    f"ASR就绪: {(time.monotonic() - connect_started) * 1000:.0f}ms"
                )

                self.forward_task = asyncio.create_task(self._forward_asr_results(conn))
                for cached_audio in conn.asr_audio[-10:-1]:
                    pcm_frame = self._decode_audio(conn, cached_audio)
                    payload = gzip.compress(pcm_frame)
                    audio_request = bytearray(self.generate_audio_default_header())
                    audio_request.extend(len(payload).to_bytes(4, "big"))
                    audio_request.extend(payload)
                    await self.asr_ws.send(audio_request)
                return True
            except asyncio.CancelledError:
                if self.asr_ws:
                    await self.asr_ws.close()
                    self.asr_ws = None
                self.stream_ready = False
                self.is_processing = False
                raise
            except Exception as e:
                logger.bind(tag=TAG).error(f"建立ASR连接失败: {str(e)}")
                if hasattr(e, "__cause__") and e.__cause__:
                    logger.bind(tag=TAG).error(f"错误原因: {str(e.__cause__)}")
                if self.asr_ws:
                    await self.asr_ws.close()
                    self.asr_ws = None
                self.stream_ready = False
                self.is_processing = False
                return False

    def _decode_audio(self, conn, audio):
        return audio if conn.audio_format == "pcm" else self.decoder.decode(audio, 960)

    async def handle_voice_stop(self, conn, asr_audio_task):
        stopped_at = getattr(conn, "client_voice_stop_time", 0)
        if stopped_at:
            logger.bind(tag=TAG).debug(
                f"ASR最终结果: 本地判停后 {max(0, time.time() - stopped_at) * 1000:.0f}ms"
            )
        await super().handle_voice_stop(conn, asr_audio_task)

    async def _forward_asr_results(self, conn):
        try:
            while self.asr_ws and not conn.stop_event.is_set():
                # 获取当前连接的音频数据
                audio_data = conn.asr_audio
                try:
                    response = await self.asr_ws.recv()
                    result = self.parse_response(response)
                    if "code" in result:
                        raise RuntimeError(f"ASR服务错误: {result}")

                    if "payload_msg" in result:
                        payload = result["payload_msg"]
                        # 检查是否是错误码1013（无有效语音）
                        if "code" in payload and payload["code"] == 1013:
                            # 静默处理，不记录错误日志
                            continue

                        if "result" in payload:
                            if result.get("is_last"):
                                final_text = payload["result"].get("text", "")
                                if self.result_type == "full":
                                    self.text = final_text
                                elif final_text and not self.text.endswith(final_text):
                                    self.text += final_text
                                if self.text and audio_data:
                                    await self.handle_voice_stop(conn, audio_data.copy())
                                break
                            utterances = payload["result"].get("utterances", [])
                            # 检查duration和空文本的情况
                            if (
                                not self.enable_multilingual # 注意：多语种模式不返回中间结果，需要等待最终结果
                                and payload.get("audio_info", {}).get("duration", 0) > 2000
                                and not utterances
                                and not payload["result"].get("text")
                                and conn.client_listen_mode != "manual"
                            ):
                                logger.bind(tag=TAG).error(f"识别文本：空")
                                self.text = ""
                                if audio_data:  # 已有明确识别结果时，不按音频包数丢弃短句
                                    await self.handle_voice_stop(conn, audio_data)
                                break

                            # 专门处理没有文本的识别结果（手动模式下可能已经识别完成但是没松按键）
                            elif not payload["result"].get("text") and not utterances:
                                # 多语种模式会持续返回空文本，直到最后返回完整结果，所以需要排除
                                if self.enable_multilingual:
                                    continue

                                if conn.client_listen_mode == "manual" and conn.client_voice_stop and len(audio_data) > 0:
                                    logger.bind(tag=TAG).debug("消息结束收到停止信号，触发处理")
                                    await self.handle_voice_stop(conn, audio_data)
                                    break

                            for utterance in utterances:
                                if utterance.get("definite", False):
                                    current_text = utterance["text"]

                                    # 手动模式下累积识别结果
                                    if conn.client_listen_mode == "manual":
                                        if self.result_type == "full":
                                            self.text = payload["result"].get("text", current_text)
                                        elif self.text:
                                            self.text += current_text
                                        else:
                                            self.text = current_text

                                        # 在接收消息中途时收到停止信号
                                        if conn.client_voice_stop and len(audio_data) > 0:
                                            logger.bind(tag=TAG).debug("消息中途收到停止信号，触发处理")
                                            await self.handle_voice_stop(conn, audio_data)
                                        break
                                    else:
                                        # 自动模式下直接覆盖
                                        self.text = current_text
                                        if audio_data:  # 已有明确识别结果时，不按音频包数丢弃短句
                                            await self.handle_voice_stop(conn, audio_data)
                                    break
                        elif "error" in payload:
                            error_msg = payload.get("error", "未知错误")
                            logger.bind(tag=TAG).error(f"ASR服务返回错误: {error_msg}")
                            break

                except websockets.ConnectionClosed:
                    logger.bind(tag=TAG).info("ASR服务连接已关闭")
                    self.is_processing = False
                    break
                except Exception as e:
                    logger.bind(tag=TAG).error(f"处理ASR结果时发生错误: {str(e)}")
                    if hasattr(e, "__cause__") and e.__cause__:
                        logger.bind(tag=TAG).error(f"错误原因: {str(e.__cause__)}")
                    self.is_processing = False
                    break

        except Exception as e:
            logger.bind(tag=TAG).error(f"ASR结果转发任务发生错误: {str(e)}")
            if hasattr(e, "__cause__") and e.__cause__:
                logger.bind(tag=TAG).error(f"错误原因: {str(e.__cause__)}")
        finally:
            if self.asr_ws:
                await self.asr_ws.close()
                self.asr_ws = None
            self.stream_ready = False
            self.is_processing = False
            # 重置所有音频相关状态
            conn.reset_audio_states()
            if (
                getattr(conn, "hospice_home_rearm_asr", False)
                and getattr(conn, "hospice_home_listening", False)
            ):
                conn.hospice_home_rearm_asr = False
                conn.hospice_home_prepare_task = asyncio.create_task(
                    self.prepare_stream(conn)
                )

    def stop_ws_connection(self):
        if self.asr_ws:
            asyncio.create_task(self.asr_ws.close())
            self.asr_ws = None
        self.stream_ready = False
        self.is_processing = False

    async def _send_stop_request(self):
        """发送最后一个音频帧以通知服务器结束"""
        if self.asr_ws:
            try:
                # 发送结束标记的音频帧（gzip压缩的空数据）
                empty_payload = gzip.compress(b"")
                last_audio_request = bytearray(self.generate_last_audio_default_header())
                last_audio_request.extend(len(empty_payload).to_bytes(4, "big"))
                last_audio_request.extend(empty_payload)
                await self.asr_ws.send(last_audio_request)
                logger.bind(tag=TAG).debug("已发送结束音频帧")
            except Exception as e:
                logger.bind(tag=TAG).debug(f"发送结束音频帧时出错: {e}")

    def construct_request(self, reqid):
        req = {
            "user": {"uid": self.uid},
            "request": {
                "model_name": "bigmodel",
                "enable_itn": True,
                "enable_punc": True,
                "enable_ddc": self.config.get("enable_ddc", False),
                "enable_nonstream": self.config.get("enable_nonstream", False),
                # 短语音开头可能较弱，按官方建议在流起始阶段强制按有声处理。
                "force_to_speech_time": int(
                    self.config.get("force_to_speech_time", 1000)
                ),
                "reqid": reqid,
                "workflow": self.workflow,
                "show_utterances": True,
                "result_type": self.result_type,
                "sequence": 1,
                "end_window_size": self.end_window_size,
            },
            "audio": {
                "format": self.format,
                "codec": self.codec,
                "rate": self.rate,
                "bits": self.bits,
                "channel": self.channel,
                "sample_rate": self.rate,
            },
        }
        corpus = {key: value for key, value in {
            "boosting_table_name": self.boosting_table_name,
            "correct_table_name": self.correct_table_name,
        }.items() if value}
        if corpus:
            req["request"]["corpus"] = corpus

        # language参数仅在多语种模式下添加
        if self.enable_multilingual and self.language:
            req["audio"]["language"] = self.language

        return req

    def token_auth(self):
        return {
            "X-Api-App-Key": self.appid,
            "X-Api-Access-Key": self.access_token,
            "X-Api-Resource-Id": self.resource_id,
            "X-Api-Connect-Id": str(uuid.uuid4()),
        }

    def generate_header(
        self,
        version=0x01,
        message_type=0x01,
        message_type_specific_flags=0x00,
        serial_method=0x01,
        compression_type=0x01,
        reserved_data=0x00,
        extension_header: bytes = b"",
    ):
        header = bytearray()
        header_size = int(len(extension_header) / 4) + 1
        header.append((version << 4) | header_size)
        header.append((message_type << 4) | message_type_specific_flags)
        header.append((serial_method << 4) | compression_type)
        header.append(reserved_data)
        header.extend(extension_header)
        return header

    def generate_audio_default_header(self):
        return self.generate_header(
            version=0x01,
            message_type=0x02,
            message_type_specific_flags=0x00,
            serial_method=0x00,
            compression_type=0x01,
        )

    def generate_last_audio_default_header(self):
        return self.generate_header(
            version=0x01,
            message_type=0x02,
            message_type_specific_flags=0x02,
            serial_method=0x00,
            compression_type=0x01,
        )

    def parse_response(self, res: bytes) -> dict:
        if len(res) < 4:
            raise ValueError("ASR response header is truncated")
        offset = (res[0] & 0x0F) * 4
        message_type, flags = res[1] >> 4, res[1] & 0x0F
        serialization, compression = res[2] >> 4, res[2] & 0x0F
        result = {"is_last": bool(flags & 2)}

        def read_int(signed=False):
            nonlocal offset
            if offset + 4 > len(res):
                raise ValueError("ASR response is truncated")
            value = int.from_bytes(res[offset:offset + 4], "big", signed=signed)
            offset += 4
            return value

        if offset < 4 or offset > len(res):
            raise ValueError("Invalid ASR header size")
        if message_type == 0x0F:
            result["code"] = read_int()
        elif message_type == 0x09:
            if flags & 1:
                result["sequence"] = read_int(signed=True)
        else:
            raise ValueError(f"Unexpected ASR message type: {message_type}")
        size = read_int()
        if offset + size != len(res):
            raise ValueError("ASR payload length mismatch")
        payload = res[offset:]
        if compression == 1:
            payload = gzip.decompress(payload)
        elif compression != 0:
            raise ValueError(f"Unsupported ASR compression: {compression}")
        result["payload_msg"] = json.loads(payload) if serialization == 1 else {
            "error": payload.decode("utf-8", errors="replace")
        }
        return result

    async def speech_to_text(self, opus_data, session_id, audio_format, artifacts=None):
        result = self.text
        self.text = ""  # 清空text
        return result, None

    async def close(self):
        """资源清理方法"""
        if self.asr_ws:
            await self.asr_ws.close()
            self.asr_ws = None
        self.stream_ready = False
        if self.forward_task:
            self.forward_task.cancel()
            try:
                await self.forward_task
            except asyncio.CancelledError:
                pass
            self.forward_task = None
        self.is_processing = False
        
        # 显式释放decoder资源
        if hasattr(self, 'decoder') and self.decoder is not None:
            try:
                del self.decoder
                self.decoder = None
                logger.bind(tag=TAG).debug("Doubao decoder resources released")
            except Exception as e:
                logger.bind(tag=TAG).debug(f"释放Doubao decoder资源时出错: {e}")
