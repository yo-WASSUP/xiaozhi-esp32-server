import unittest

from core.providers.realtime.doubao_s2s import (
    EVENT_TTS_AUDIO,
    MESSAGE_AUDIO_SERVER,
    SERIALIZATION_NONE,
    DoubaoS2SClient,
    build_event_frame,
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


if __name__ == "__main__":
    unittest.main()
