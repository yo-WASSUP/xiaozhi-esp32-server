import queue
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from core.dignity.runtime import (
    _speak_dignity_reply,
    start_dignity_mode,
    stop_dignity_mode,
)
from core.handle.intentHandler import speak_txt
from core.utils.dialogue import Dialogue, Message


class DignityChatIsolationTest(unittest.IsolatedAsyncioTestCase):
    async def test_stopping_dignity_removes_only_mode_local_dialogue(self):
        dialogue = Dialogue()
        dialogue.put(Message(role="system", content="ordinary prompt"))
        dialogue.put(Message(role="user", content="ordinary question"))
        conn = SimpleNamespace(
            dialogue=dialogue,
            dignity_active=False,
            dignity_state=None,
            dignity_debug_state=None,
            dignity_patient_id=None,
            dignity_decision_model=None,
            dignity_dialogue_start_index=None,
            session_id="session-1",
            logger=MagicMock(),
            websocket=SimpleNamespace(send=AsyncMock()),
        )

        with patch(
            "core.dignity.runtime._apply_persisted_memory",
            side_effect=lambda _conn, state: state,
        ), patch(
            "core.dignity.runtime._load_dignity_document_source",
            return_value={},
        ), patch(
            "core.dignity.runtime.send_dignity_event",
            new=AsyncMock(),
        ), patch("core.dignity.runtime._write_dignity_log"):
            await start_dignity_mode(conn)

            dialogue.put(Message(role="user", content="dignity patient text"))
            dialogue.put(Message(role="assistant", content="dignity reply"))
            await stop_dignity_mode(conn)

        self.assertFalse(conn.dignity_active)
        self.assertIsNone(conn.dignity_dialogue_start_index)
        self.assertEqual(
            [message.content for message in dialogue.dialogue],
            ["ordinary prompt", "ordinary question"],
        )

    def test_dignity_tts_does_not_record_into_ordinary_dialogue(self):
        conn = SimpleNamespace(sentence_id=None)

        with patch("core.handle.intentHandler.speak_txt") as speak_txt:
            _speak_dignity_reply(conn, "dignity reply")

        speak_txt.assert_called_once_with(
            conn,
            "dignity reply",
            record_dialogue=False,
        )

    def test_speak_txt_can_play_without_mutating_dialogue(self):
        tts = SimpleNamespace(
            tts_text_queue=queue.Queue(),
            tts_one_sentence=MagicMock(),
        )
        dialogue = SimpleNamespace(put=MagicMock())
        conn = SimpleNamespace(
            sentence_id="sentence-1",
            tts=tts,
            dialogue=dialogue,
            tts_MessageText="",
        )

        speak_txt(conn, "dignity reply", record_dialogue=False)

        self.assertEqual(conn.tts_MessageText, "dignity reply")
        self.assertEqual(tts.tts_text_queue.qsize(), 2)
        tts.tts_one_sentence.assert_called_once()
        dialogue.put.assert_not_called()


if __name__ == "__main__":
    unittest.main()
