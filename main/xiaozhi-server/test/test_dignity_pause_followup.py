import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from core.dignity.runtime import (
    handle_dignity_turn_if_active,
    pause_dignity_mode,
    prompt_dignity_after_silence,
    resume_dignity_mode,
)
from core.dignity.voice_commands import detect_dignity_session_command


def build_connection():
    return SimpleNamespace(
        dignity_active=True,
        dignity_state=None,
        dignity_paused=False,
        dignity_pause_reason="",
        dignity_paused_at="",
        dignity_silence_prompt_count=0,
        websocket=AsyncMock(),
        session_id="session-1",
        config={},
    )


class DignitySessionCommandTests(unittest.TestCase):
    def test_detects_pause_and_resume_phrases(self):
        pause = detect_dignity_session_command(
            "小暖，我有点累了，想休息一下。",
            paused=False,
        )
        resume = detect_dignity_session_command(
            "我休息好了，我们继续聊吧。",
            paused=True,
        )

        self.assertEqual(pause["action"], "pause")
        self.assertEqual(resume["action"], "resume")

    def test_does_not_pause_when_patient_says_they_are_not_tired(self):
        command = detect_dignity_session_command(
            "我不累，不用休息，我们继续聊。",
            paused=False,
        )

        self.assertIsNone(command)


class DignityPauseAndFollowupTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.conn = build_connection()
        self.log_patch = patch("core.dignity.runtime._write_dignity_log")
        self.robot_patch = patch(
            "core.dignity.runtime.send_robot_action_event",
            new=AsyncMock(),
        )
        self.speak_patch = patch(
            "core.dignity.runtime._speak_dignity_reply",
            new=Mock(),
        )
        self.log_patch.start()
        self.robot_patch.start()
        self.speak = self.speak_patch.start()

    async def asyncTearDown(self):
        self.speak_patch.stop()
        self.robot_patch.stop()
        self.log_patch.stop()

    def dignity_events(self):
        return [
            json.loads(call.args[0])
            for call in self.conn.websocket.send.await_args_list
        ]

    async def test_pause_and_resume_preserve_session(self):
        await pause_dignity_mode(
            self.conn,
            {"source": "patient_button", "reason": "patient_request"},
        )

        self.assertTrue(self.conn.dignity_active)
        self.assertTrue(self.conn.dignity_paused)
        self.assertEqual(self.dignity_events()[-1]["event"], "mode_paused")

        await resume_dignity_mode(self.conn, {"source": "patient_button"})

        self.assertTrue(self.conn.dignity_active)
        self.assertFalse(self.conn.dignity_paused)
        self.assertEqual(self.conn.dignity_silence_prompt_count, 0)
        self.assertEqual(self.dignity_events()[-1]["event"], "mode_resumed")

    async def test_two_silence_prompts_then_automatic_pause(self):
        await prompt_dignity_after_silence(self.conn)
        await prompt_dignity_after_silence(self.conn)
        await prompt_dignity_after_silence(self.conn)

        events = self.dignity_events()
        self.assertEqual(
            [event["event"] for event in events],
            ["silence_prompt", "silence_prompt", "mode_paused"],
        )
        self.assertEqual(events[0]["data"]["silence_prompt_count"], 1)
        self.assertEqual(events[1]["data"]["silence_prompt_count"], 2)
        self.assertTrue(events[2]["data"]["paused"])
        self.assertTrue(self.conn.dignity_paused)
        self.assertEqual(self.speak.call_count, 3)

    async def test_paused_session_ignores_talk_and_accepts_resume_command(self):
        self.conn.dignity_paused = True
        with patch(
            "core.dignity.runtime.send_stt_message",
            new=AsyncMock(),
        ) as send_stt, patch(
            "core.dignity.runtime.resume_dignity_mode",
            new=AsyncMock(),
        ) as resume:
            handled = await handle_dignity_turn_if_active(self.conn, "旁边的人在说话")
            self.assertTrue(handled)
            send_stt.assert_not_awaited()
            resume.assert_not_awaited()

            handled = await handle_dignity_turn_if_active(self.conn, "小暖，我们继续访谈")
            self.assertTrue(handled)
            send_stt.assert_awaited_once()
            resume.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
