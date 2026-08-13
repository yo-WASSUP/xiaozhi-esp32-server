import asyncio
import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from core.providers.realtime.doubao_s2s import (
    EVENT_ASR_INFO,
    EVENT_ASR_ENDED,
    EVENT_ASR_RESPONSE,
    EVENT_TTS_AUDIO,
    MESSAGE_AUDIO_SERVER,
    MESSAGE_FULL_CLIENT,
    SERIALIZATION_JSON,
    SERIALIZATION_NONE,
    DoubaoS2SClient,
    build_event_frame,
    build_system_role,
    clean_realtime_text,
    parse_server_frame,
    split_pcm_frames,
)


class AsyncFrames:
    def __init__(self, *frames):
        self.frames = iter(frames)

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self.frames)
        except StopIteration as exc:
            raise StopAsyncIteration from exc


class DoubaoS2SProtocolTests(unittest.TestCase):
    def test_pcm_is_split_into_official_20ms_packets(self):
        pcm = bytes(16000 * 2 * 60 // 1000)

        frames = split_pcm_frames(pcm)

        self.assertEqual([len(frame) for frame in frames], [640, 640, 640])

    def test_audio_event_round_trip(self):
        payload = b"\x01\x02\x03\x04"
        frame = build_event_frame(
            MESSAGE_AUDIO_SERVER,
            EVENT_TTS_AUDIO,
            "session-1",
            payload,
            SERIALIZATION_NONE,
        )

        parsed = parse_server_frame(frame)

        self.assertEqual(parsed.message_type, MESSAGE_AUDIO_SERVER)
        self.assertEqual(parsed.event, EVENT_TTS_AUDIO)
        self.assertEqual(parsed.session_id, "session-1")
        self.assertEqual(parsed.payload, payload)

    def test_cumulative_and_delta_text_are_merged_without_duplicates(self):
        merge = DoubaoS2SClient._merge_text

        self.assertEqual(merge("", "您好"), "您好")
        self.assertEqual(merge("您好", "您好呀"), "您好呀")
        self.assertEqual(merge("您好呀", "呀"), "您好呀")
        self.assertEqual(merge("您好", "，今天好吗"), "您好，今天好吗")
        self.assertEqual(merge("我想问一下", "问一下今天的天气"), "我想问一下今天的天气")
        self.assertEqual(merge("今天天气", "天气很好"), "今天天气很好")
        self.assertEqual(
            merge("第一句话。第二句话。", "第二句话。"),
            "第一句话。第二句话。",
        )
        self.assertEqual(
            merge("第一句话。", "第二句话。"),
            "第一句话。第二句话。",
        )
        full = "要得嘛。你今天想不想摆哈龙门阵嘛？比如聊聊以前爱吃的四川小吃。"
        self.assertEqual(merge("爱吃的四川小吃。", full), full)

    def test_chat_and_tts_streams_are_selected_without_cross_stream_splicing(self):
        chat = "要得嘛。你今天想不想摆哈龙门阵嘛？比如聊聊以前爱吃的四川小吃。"
        tts_tail = "爱吃的四川小吃。"

        self.assertEqual(DoubaoS2SClient._select_display_text(chat, tts_tail), chat)

    def test_asr_hypotheses_replace_earlier_revisions(self):
        latest = DoubaoS2SClient._latest_hypothesis

        text = latest("", "我是在")
        text = latest(text, "我是再跟你说一遍看你回复的怎么样")
        text = latest(text, "我是再跟你说一遍，看你回复得怎么样。")

        self.assertEqual(text, "我是再跟你说一遍，看你回复得怎么样。")
        self.assertEqual(latest(text, ""), text)

    def test_emotion_control_comment_is_hidden_from_display_text(self):
        text = '好呀，我会认真听您说的。 <!--emotion: {"mood":"neutral","intensity":0.4}-->'

        self.assertEqual(clean_realtime_text(text), "好呀，我会认真听您说的。")


class DoubaoS2SPcmBridgeTests(unittest.IsolatedAsyncioTestCase):
    async def test_browser_pcm_is_queued_without_opus_decode(self):
        client = DoubaoS2SClient.__new__(DoubaoS2SClient)
        client.closed = False
        client.conn = SimpleNamespace(
            voice_mode="doubao_s2s",
            last_activity_time=0,
            logger=SimpleNamespace(
                bind=lambda **_: SimpleNamespace(warning=lambda *_: None)
            ),
        )
        client.audio_queue = asyncio.Queue(maxsize=4)
        pcm = bytes(640)

        await client.send_pcm(pcm)

        self.assertIs(await client.audio_queue.get(), pcm)

    async def test_doubao_pcm_is_forwarded_directly_to_browser(self):
        websocket = AsyncMock()
        client = DoubaoS2SClient.__new__(DoubaoS2SClient)
        client.conn = SimpleNamespace(client_abort=False, websocket=websocket)
        pcm = b"\x01\x02" * 320

        await client._send_pcm(pcm, end_of_stream=False)

        websocket.send.assert_awaited_once_with(pcm)

    async def test_finished_response_tells_browser_to_drain_pcm(self):
        websocket = AsyncMock()
        client = DoubaoS2SClient.__new__(DoubaoS2SClient)
        client.conn = SimpleNamespace(
            websocket=websocket,
            session_id="session-1",
            clearSpeakStatus=lambda: None,
        )

        await client._finish_client_playback()

        message = json.loads(websocket.send.await_args.args[0])
        self.assertEqual(message["state"], "stop")
        self.assertTrue(message["drain"])


class DoubaoS2SInterruptTests(unittest.IsolatedAsyncioTestCase):
    async def test_interrupt_is_idempotent_and_stops_client_playback(self):
        client = DoubaoS2SClient.__new__(DoubaoS2SClient)
        client.active = True
        client.session_id = "session-1"
        client.interrupt_sent = False
        client._send_frame = AsyncMock()
        client._stop_client_playback = AsyncMock()

        await client.interrupt()
        await client.interrupt()

        client._send_frame.assert_awaited_once()
        client._stop_client_playback.assert_awaited_once()
        self.assertTrue(client.interrupt_sent)

    async def test_asr_info_interrupts_active_response(self):
        frame = build_event_frame(
            MESSAGE_FULL_CLIENT,
            EVENT_ASR_INFO,
            "session-1",
            b"{}",
            SERIALIZATION_JSON,
        )
        client = DoubaoS2SClient.__new__(DoubaoS2SClient)
        client.upstream = AsyncFrames(frame)
        client.responding = True
        client.interrupt_sent = False
        client.conn = SimpleNamespace(
            client_abort=False,
            logger=SimpleNamespace(
                bind=lambda **_: SimpleNamespace(info=lambda *_: None)
            )
        )
        client._send_vad = AsyncMock()
        client.interrupt = AsyncMock()

        await client._receive_loop()

        client._send_vad.assert_awaited_once_with(True)
        client.interrupt.assert_awaited_once()

    async def test_asr_info_clears_buffered_playback_without_interrupt_when_idle(self):
        start_frame = build_event_frame(
            MESSAGE_FULL_CLIENT,
            EVENT_ASR_INFO,
            "session-1",
            b"{}",
            SERIALIZATION_JSON,
        )
        client = DoubaoS2SClient.__new__(DoubaoS2SClient)
        client.upstream = AsyncFrames(start_frame)
        client.responding = False
        client.interrupt_sent = False
        client.conn = SimpleNamespace(
            client_abort=False,
            logger=SimpleNamespace(
                bind=lambda **_: SimpleNamespace(info=lambda *_: None)
            ),
        )
        client._send_vad = AsyncMock()
        client._stop_client_playback = AsyncMock()
        client.interrupt = AsyncMock()

        await client._receive_loop()

        client._send_vad.assert_awaited_once_with(True)
        client._stop_client_playback.assert_awaited_once()
        client.interrupt.assert_not_awaited()

    async def test_asr_response_does_not_duplicate_interrupt(self):
        frame = build_event_frame(
            MESSAGE_FULL_CLIENT,
            EVENT_ASR_RESPONSE,
            "session-1",
            json.dumps({"text": "请停一下"}).encode("utf-8"),
            SERIALIZATION_JSON,
        )
        client = DoubaoS2SClient.__new__(DoubaoS2SClient)
        client.upstream = AsyncFrames(frame)
        client.responding = True
        client.interrupt_sent = False
        client.user_text = ""
        client.conn = SimpleNamespace(
            client_abort=False,
            logger=SimpleNamespace(
                bind=lambda **_: SimpleNamespace(info=lambda *_: None)
            ),
        )
        client._send_vad = AsyncMock()
        client.interrupt = AsyncMock()

        await client._receive_loop()

        client._send_vad.assert_awaited_once_with(True)
        client.interrupt.assert_not_awaited()

    def test_system_role_inherits_patient_prompt_and_locks_identity(self):
        role = build_system_role(
            "你正在陪伴一位需要关怀的老年患者。",
            "回答自然简洁。",
        )

        self.assertIn("老年患者", role)
        self.assertIn("回答自然简洁", role)
        self.assertIn("名字是“安安”", role)
        self.assertIn("不要自称豆包", role)
        self.assertIn("只能倾听、说话、安慰、陪聊", role)
        self.assertIn("不能倒水", role)
        self.assertIn("不能自行打电话", role)
        self.assertIn("一律按“做不到、未执行”处理", role)


class DoubaoS2SDisplayTextTests(unittest.IsolatedAsyncioTestCase):
    async def test_tts_tail_cannot_be_spliced_before_complete_chat_text(self):
        websocket = AsyncMock()
        client = DoubaoS2SClient.__new__(DoubaoS2SClient)
        client.conn = SimpleNamespace(
            client_abort=False,
            websocket=websocket,
            session_id="session-1",
            sentence_id="sentence-1",
        )
        full = "要得嘛。你今天想不想摆哈龙门阵嘛？比如聊聊以前爱吃的四川小吃。"
        client.assistant_chat_text = full
        client.assistant_tts_text = "爱吃的四川小吃。"
        client.assistant_sent_text = ""
        client.assistant_finalized = False

        await client._finalize_assistant_text()

        message = json.loads(websocket.send.await_args.args[0])
        self.assertEqual(message["text"], full)

    async def test_updated_final_text_is_sent_again_after_late_segment(self):
        websocket = AsyncMock()
        client = DoubaoS2SClient.__new__(DoubaoS2SClient)
        client.conn = SimpleNamespace(
            client_abort=False,
            websocket=websocket,
            session_id="session-1",
            sentence_id="sentence-1",
        )
        client.assistant_chat_text = "第一段"
        client.assistant_tts_text = ""
        client.assistant_sent_text = ""
        client.assistant_finalized = False

        await client._finalize_assistant_text()
        client.assistant_chat_text = "第一段，后续完整内容"
        await client._finalize_assistant_text()
        await client._finalize_assistant_text()

        self.assertEqual(websocket.send.await_count, 2)
        first = json.loads(websocket.send.await_args_list[0].args[0])
        final = json.loads(websocket.send.await_args_list[1].args[0])
        self.assertEqual(first["state"], "complete")
        self.assertEqual(final["text"], "第一段，后续完整内容")
        self.assertEqual(final["sentence_id"], "sentence-1")


if __name__ == "__main__":
    unittest.main()
