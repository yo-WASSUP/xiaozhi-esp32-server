import unittest
from types import SimpleNamespace

from core.handle.receiveAudioHandle import is_barge_in_confirmed


class BargeInConfirmationTests(unittest.TestCase):
    def setUp(self):
        self.conn = SimpleNamespace(
            client_is_speaking=True,
            client_listen_mode="auto",
            barge_in_voice_started_at=None,
        )

    def test_requires_three_tenths_of_continuous_voice(self):
        self.assertFalse(is_barge_in_confirmed(self.conn, True, now=10.0))
        self.assertFalse(is_barge_in_confirmed(self.conn, True, now=10.29))
        self.assertTrue(is_barge_in_confirmed(self.conn, True, now=10.3))

    def test_silence_resets_the_confirmation_window(self):
        self.assertFalse(is_barge_in_confirmed(self.conn, True, now=10.0))
        self.assertFalse(is_barge_in_confirmed(self.conn, False, now=10.3))
        self.assertFalse(is_barge_in_confirmed(self.conn, True, now=10.6))
        self.assertFalse(is_barge_in_confirmed(self.conn, True, now=10.89))
        self.assertTrue(is_barge_in_confirmed(self.conn, True, now=10.9))

    def test_manual_mode_never_confirms_barge_in(self):
        self.conn.client_listen_mode = "manual"

        self.assertFalse(is_barge_in_confirmed(self.conn, True, now=10.0))
        self.assertFalse(is_barge_in_confirmed(self.conn, True, now=11.0))

    def test_playback_end_clears_pending_confirmation(self):
        self.assertFalse(is_barge_in_confirmed(self.conn, True, now=10.0))
        self.conn.client_is_speaking = False

        self.assertFalse(is_barge_in_confirmed(self.conn, True, now=10.6))
        self.assertIsNone(self.conn.barge_in_voice_started_at)

if __name__ == "__main__":
    unittest.main()
