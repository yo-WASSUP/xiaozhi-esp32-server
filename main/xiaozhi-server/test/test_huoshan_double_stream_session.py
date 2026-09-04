import asyncio
import concurrent.futures
import queue
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from core.providers.tts.dto.dto import ContentType, SentenceType, TTSMessageDTO
from core.providers.tts.huoshan_double_stream import TTSProvider


class HuoshanDoubleStreamSessionTests(unittest.TestCase):
    def test_new_session_restores_client_start_marker(self):
        provider = object.__new__(TTSProvider)
        provider.tts_audio_first_sentence = False
        provider.tts_text_queue = queue.Queue()
        provider.enable_ws_reuse = True
        provider.before_stop_play_files = []
        provider._first_audio_received = False
        provider._session_start_time = None
        stop_event = threading.Event()
        provider.conn = SimpleNamespace(
            stop_event=stop_event,
            client_abort=False,
            sentence_id="new-session",
            loop=object(),
        )

        async def start_session(_session_id):
            stop_event.set()

        provider.start_session = start_session
        provider.tts_text_queue.put(
            TTSMessageDTO(
                sentence_id="new-session",
                sentence_type=SentenceType.FIRST,
                content_type=ContentType.ACTION,
            )
        )

        def run_immediately(coroutine, _loop=None, **_kwargs):
            future = concurrent.futures.Future()
            future.set_result(asyncio.run(coroutine))
            return future

        with patch(
            "core.providers.tts.huoshan_double_stream.asyncio.run_coroutine_threadsafe",
            side_effect=run_immediately,
        ):
            provider.tts_text_priority_thread()

        self.assertTrue(provider.tts_audio_first_sentence)


if __name__ == "__main__":
    unittest.main()
