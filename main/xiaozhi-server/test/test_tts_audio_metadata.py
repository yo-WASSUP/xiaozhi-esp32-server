import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from core.handle.sendAudioHandle import send_tts_message


class TtsAudioMetadataTests(unittest.IsolatedAsyncioTestCase):
    async def test_standard_tts_start_identifies_opus_output(self):
        websocket = AsyncMock()
        conn = SimpleNamespace(
            websocket=websocket,
            session_id="session-1",
            sentence_id="sentence-1",
            sample_rate=16000,
        )

        await send_tts_message(conn, "start")

        message = json.loads(websocket.send.await_args.args[0])
        self.assertEqual(message["audio_format"], "opus")
        self.assertEqual(message["sample_rate"], 16000)


if __name__ == "__main__":
    unittest.main()
