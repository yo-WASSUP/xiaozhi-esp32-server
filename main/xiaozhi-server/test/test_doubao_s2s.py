import unittest
from unittest.mock import AsyncMock

from core.providers.realtime.doubao_s2s import (
    EVENT_TTS_AUDIO,
    MESSAGE_AUDIO_SERVER,
    SERIALIZATION_NONE,
    DoubaoS2SClient,
    build_event_frame,
    build_system_role,
    clean_realtime_text,
    parse_server_frame,
)


class DoubaoS2SProtocolTests(unittest.TestCase):
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

    def test_system_role_inherits_patient_prompt_and_locks_identity(self):
        role = build_system_role(
            "你正在陪伴一位需要关怀的老年患者。",
            "回答自然简洁。",
        )

        self.assertIn("老年患者", role)
        self.assertIn("回答自然简洁", role)
        self.assertIn("名字是“小暖”", role)
        self.assertIn("不要自称豆包", role)


if __name__ == "__main__":
    unittest.main()
