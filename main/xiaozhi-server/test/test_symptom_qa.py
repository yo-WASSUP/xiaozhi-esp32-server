import json
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

from core.dignity.symptom_qa import DATA_PATH, load_symptom_qa_entries
from core.dignity.symptom_qa import match_symptom_question
from core.handle.intentHandler import handle_hospice_symptom_qa


class SymptomQaTests(unittest.TestCase):
    def test_generated_json_matches_source_shape(self):
        payload = json.loads(Path(DATA_PATH).read_text(encoding="utf-8"))

        self.assertEqual(payload["source_sheet"], "Sheet1")
        self.assertEqual(payload["source_range"], "A1:D82")
        self.assertEqual(payload["entry_count"], 81)
        self.assertEqual(len(payload["items"]), 81)
        self.assertEqual(len({item["symptom"] for item in payload["items"]}), 15)

    def test_exact_question_returns_source_answer(self):
        match = match_symptom_question("什么是疼痛？")

        self.assertIsNotNone(match)
        self.assertEqual(match.entry.symptom, "疼痛")
        self.assertEqual(match.entry.source_row, 2)
        self.assertTrue(match.entry.answer.startswith("疼痛是一种身体和心里"))
        self.assertEqual(match.match_type, "exact")

    def test_common_spoken_variants_match(self):
        definition = match_symptom_question("小暖，请问疼痛是什么意思呀？")
        action = match_symptom_question("疼痛咋办")
        emergency = match_symptom_question("咯血什么时候需要立即求助")

        self.assertEqual(definition.entry.question, "什么是疼痛？")
        self.assertEqual(action.entry.question, "出现疼痛时我该怎么办？")
        self.assertEqual(emergency.entry.symptom, "咯血")
        self.assertEqual(emergency.entry.question, "什么情况下需要立即求助？")

    def test_ambiguous_or_unrelated_question_falls_through(self):
        self.assertIsNone(match_symptom_question("什么情况下需要立即求助？"))
        self.assertIsNone(match_symptom_question("今天天气怎么样？"))
        self.assertIsNone(match_symptom_question("我今天心情不错"))

    def test_loaded_entries_have_complete_source_metadata(self):
        entries = load_symptom_qa_entries()

        self.assertEqual(len(entries), 81)
        self.assertTrue(all(entry.source_row >= 2 for entry in entries))
        self.assertTrue(all(entry.answer for entry in entries))


class FakeLogger:
    def bind(self, **kwargs):
        return self

    def info(self, message):
        pass

    def warning(self, message):
        pass


class FakeDialogue:
    def __init__(self):
        self.messages = []

    def put(self, message):
        self.messages.append(message)


class FakeConn:
    def __init__(self):
        self.config = {"hospice": {"enable_logging": True}}
        self.logger = FakeLogger()
        self.dialogue = FakeDialogue()
        self.sentence_id = None
        self.client_abort = True


class SymptomQaHandlerTests(unittest.IsolatedAsyncioTestCase):
    async def test_match_is_answered_directly(self):
        conn = FakeConn()

        with (
            patch(
                "core.handle.intentHandler.send_stt_message",
                new_callable=AsyncMock,
            ) as send_stt,
            patch("core.handle.intentHandler.speak_txt", new=Mock()) as speak,
        ):
            handled = await handle_hospice_symptom_qa(conn, "什么是疼痛？")

        self.assertTrue(handled)
        send_stt.assert_awaited_once_with(conn, "什么是疼痛？")
        self.assertTrue(speak.call_args.args[1].startswith("疼痛是一种身体和心里"))
        self.assertEqual(conn.dialogue.messages[0].role, "user")
        self.assertFalse(conn.client_abort)
        self.assertIsNotNone(conn.sentence_id)

    async def test_no_match_continues_normal_chat(self):
        conn = FakeConn()

        with (
            patch(
                "core.handle.intentHandler.send_stt_message",
                new_callable=AsyncMock,
            ) as send_stt,
            patch("core.handle.intentHandler.speak_txt", new=Mock()) as speak,
        ):
            handled = await handle_hospice_symptom_qa(conn, "今天天气怎么样？")

        self.assertFalse(handled)
        send_stt.assert_not_awaited()
        speak.assert_not_called()
        self.assertEqual(conn.dialogue.messages, [])


if __name__ == "__main__":
    unittest.main()
