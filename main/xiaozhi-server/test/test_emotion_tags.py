import asyncio
import concurrent.futures
import queue
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

with (
    patch("config.logger.check_config_file"),
    patch("config.logger.load_config", return_value={"log": {}}),
):
    from core.connection_parts.chat import ChatMixin
    from core.providers.emotion import filter_stream_emotion_tag, parse_emotion
from core.providers.tts.dto.dto import SentenceType
from core.utils.dialogue import Dialogue


class EmotionTagTests(unittest.TestCase):
    def test_emotion_tag_formats_in_stream_and_completed_reply(self):
        reply = "听得清清楚楚的，您说嘛，我一直在这儿听着的。"
        tags = [
            '<!--emotion:{"mood":"calm","intensity":0.5}-->',
            '<!-- emotion: {"mood": "calm", "intensity": 0.5} -->',
            '<!--\n emotion : {\n"mood":"calm", "intensity":0.5\n} -->',
        ]
        for tag in tags:
            for text in (tag + reply, reply + tag):
                with self.subTest(text=text):
                    clean, emotion = parse_emotion(text)
                    self.assertEqual(clean, reply)
                    self.assertEqual(emotion, {"mood": "calm", "intensity": 0.5})
                for split in range(len(text) + 1):
                    with self.subTest(text=text, split=split):
                        self.assertEqual(self._stream([text[:split], text[split:]]), reply)
                with self.subTest(text=text, chunks="characters"):
                    self.assertEqual(self._stream(list(text)), reply)

    def test_preserves_text_and_unrelated_comments(self):
        text = "您好。<!-- note: keep -->1 < 2，继续说。"
        self.assertEqual(self._stream(list(text)), text)
        self.assertEqual(parse_emotion(text), (text, None))

    def test_removes_multiple_tags(self):
        tag = '<!-- emotion: {"mood":"calm","intensity":0.5} -->'
        text = tag + "您好。" + tag + "请坐。"
        self.assertEqual(self._stream(list(text)), "您好。请坐。")
        self.assertEqual(parse_emotion(text)[0], "您好。请坐。")

    def test_hides_incomplete_emotion_tag_from_speech(self):
        self.assertEqual(self._stream(list('您好。<!-- emotion: {"mood":')), "您好。")

    def test_rejects_malformed_emotion_trailer(self):
        reply = "听得见呢，您慢慢说就是，我在这儿陪着您。"
        for trailer in ("{:emotion:calm:0.6", "{:emotion:calm:0.6}"):
            text = reply + trailer
            with self.subTest(trailer=trailer):
                self.assertEqual(parse_emotion(text), (reply, None))
                for split in range(len(text) + 1):
                    self.assertEqual(self._stream([text[:split], text[split:]]), reply)
                self.assertEqual(self._stream(list(text)), reply)

    def test_preserves_speech_after_closed_malformed_tag(self):
        text = "您好。{:emotion:calm:0.6}请慢慢说。"
        self.assertEqual(self._stream(list(text)), "您好。请慢慢说。")
        self.assertEqual(parse_emotion(text), ("您好。请慢慢说。", None))

    def test_incomplete_html_tag_is_hidden_from_stored_reply(self):
        self.assertEqual(parse_emotion('您好。<!-- emotion: {"mood":'), ("您好。", None))

    def test_invalid_json_is_removed_without_emotion_data(self):
        for payload in ('{"mood":}', 'null', '[]', '"calm"'):
            text = "您好。<!-- emotion:" + payload + "-->"
            with self.subTest(payload=payload):
                self.assertEqual(parse_emotion(text), ("您好。", None))
                self.assertEqual(self._stream(list(text)), "您好。")

    def test_preserves_ordinary_braces_and_unfinished_comments(self):
        for text in ('集合 {1, 2}', '{"emotion": "词语"}', '示例 {:note:内容}', '符号 {', '<!-- note:内容'):
            with self.subTest(text=text):
                self.assertEqual(self._stream(list(text)), text)
                self.assertEqual(parse_emotion(text), (text, None))

    def test_chat_routes_only_clean_text_to_speech_display_history_and_storage(self):
        self._assert_chat_outputs_clean_text(storage_fails=False)

    def test_storage_failure_does_not_restore_raw_text_or_duplicate_history(self):
        self._assert_chat_outputs_clean_text(storage_fails=True)

    def _assert_chat_outputs_clean_text(self, storage_fails):
        reply = "听得见呢，您慢慢说就是，我在这儿陪着您。"
        conn = SimpleNamespace(
            logger=Mock(), dialogue=Dialogue(),
            tts=SimpleNamespace(tts_text_queue=queue.Queue()),
            intent_type="none", memory=None, loop=object(),
            session_id="emotion-replay", device_id="test-device",
            config={"hospice": {"enable_logging": True, "symptom_qa": False}},
            llm=SimpleNamespace(
                model_name="replay",
                response=lambda *_: iter(list(reply + "{:emotion:calm:0.6")),
            ),
        )
        storage = Mock()
        if storage_fails:
            storage.log_conversation.side_effect = OSError("storage unavailable")

        def run_immediately(coroutine, _loop):
            future = concurrent.futures.Future()
            future.set_result(asyncio.run(coroutine))
            return future

        with patch("config.logger.check_config_file"), patch(
            "config.logger.load_config", return_value={"log": {}}
        ), patch("core.connection_parts.chat.textUtils.get_emotion", new_callable=AsyncMock), patch(
            "core.connection_parts.chat.send_llm_message", new_callable=AsyncMock
        ) as send_text, patch(
            "core.connection_parts.chat.asyncio.run_coroutine_threadsafe", side_effect=run_immediately
        ), patch("core.api.hospice.storage.get_session_logger", return_value=storage):
            self.assertTrue(ChatMixin.chat(conn, "能听到我说话吗？"))

        messages = list(conn.tts.tts_text_queue.queue)
        self.assertEqual("".join(
            message.content_detail for message in messages
            if message.sentence_type == SentenceType.MIDDLE
        ), reply)
        self.assertEqual(conn.tts_MessageText, reply)
        self.assertEqual([m.content for m in conn.dialogue.dialogue if m.role == "assistant"], [reply])
        send_text.assert_awaited_once_with(conn, reply)
        if not storage_fails:
            storage.log_conversation.assert_any_call(
                "test-device", "emotion-replay", "assistant", reply,
                emotion_mood=None, emotion_intensity=None,
            )

    @staticmethod
    def _stream(chunks):
        spoken = []
        pending = ""
        for chunk in chunks:
            output, pending = filter_stream_emotion_tag(chunk, pending)
            spoken.append(output)
        output, _ = filter_stream_emotion_tag("", pending, final=True)
        spoken.append(output)
        return "".join(spoken)


if __name__ == "__main__":
    unittest.main()
