import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from core.handle.receiveAudioHandle import (
    handle_realtime_barge_in,
    is_barge_in_confirmed,
)


class BargeInConfirmationTests(unittest.TestCase):
    def setUp(self):
        self.conn = SimpleNamespace(
            client_is_speaking=True,
            client_listen_mode="auto",
            barge_in_voice_started_at=None,
        )

    def test_requires_half_a_second_of_continuous_voice(self):
        self.assertFalse(is_barge_in_confirmed(self.conn, True, now=10.0))
        self.assertFalse(is_barge_in_confirmed(self.conn, True, now=10.49))
        self.assertTrue(is_barge_in_confirmed(self.conn, True, now=10.5))

    def test_silence_resets_the_confirmation_window(self):
        self.assertFalse(is_barge_in_confirmed(self.conn, True, now=10.0))
        self.assertFalse(is_barge_in_confirmed(self.conn, False, now=10.3))
        self.assertFalse(is_barge_in_confirmed(self.conn, True, now=10.6))
        self.assertFalse(is_barge_in_confirmed(self.conn, True, now=11.09))
        self.assertTrue(is_barge_in_confirmed(self.conn, True, now=11.1))

    def test_manual_mode_never_confirms_barge_in(self):
        self.conn.client_listen_mode = "manual"

        self.assertFalse(is_barge_in_confirmed(self.conn, True, now=10.0))
        self.assertFalse(is_barge_in_confirmed(self.conn, True, now=11.0))

    def test_playback_end_clears_pending_confirmation(self):
        self.assertFalse(is_barge_in_confirmed(self.conn, True, now=10.0))
        self.conn.client_is_speaking = False

        self.assertFalse(is_barge_in_confirmed(self.conn, True, now=10.6))
        self.assertIsNone(self.conn.barge_in_voice_started_at)


class RealtimeBargeInTests(unittest.IsolatedAsyncioTestCase):
    async def test_local_vad_interrupts_realtime_after_confirmation(self):
        logger = SimpleNamespace(bind=lambda **_: SimpleNamespace(info=Mock()))
        conn = SimpleNamespace(
            vad=SimpleNamespace(is_vad=Mock(return_value=True)),
            client_is_speaking=True,
            client_listen_mode="auto",
            barge_in_voice_started_at=10.0,
            last_vad_active=True,
            last_vad_event_at=10.0,
            websocket=SimpleNamespace(send=AsyncMock()),
            session_id="session-1",
            logger=logger,
        )

        with (
            patch("core.handle.receiveAudioHandle.time.monotonic", return_value=10.5),
            patch(
                "core.handle.receiveAudioHandle.handleAbortMessage",
                new=AsyncMock(),
            ) as abort,
        ):
            interrupted = await handle_realtime_barge_in(conn, b"opus")

        self.assertTrue(interrupted)
        abort.assert_awaited_once_with(conn)

    async def test_local_vad_does_not_interrupt_when_ai_is_idle(self):
        conn = SimpleNamespace(
            vad=SimpleNamespace(is_vad=Mock(return_value=True)),
            client_is_speaking=False,
            client_listen_mode="auto",
            barge_in_voice_started_at=None,
            last_vad_active=True,
            last_vad_event_at=10.0,
            websocket=SimpleNamespace(send=AsyncMock()),
            session_id="session-1",
        )

        with patch(
            "core.handle.receiveAudioHandle.handleAbortMessage",
            new=AsyncMock(),
        ) as abort:
            interrupted = await handle_realtime_barge_in(conn, b"opus")

        self.assertFalse(interrupted)
        abort.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
