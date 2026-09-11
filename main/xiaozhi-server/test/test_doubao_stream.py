import asyncio
import gzip
import json
import struct
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from core.providers.asr.doubao_stream import ASRProvider


def response(body, flags=1, compressed=True):
    payload = json.dumps(body).encode()
    if compressed:
        payload = gzip.compress(payload)
    frame = bytes([0x11, 0x90 | flags, 0x10 | int(compressed), 0])
    if flags & 1:
        frame += struct.pack('>i', -1 if flags & 2 else 1)
    return frame + struct.pack('>I', len(payload)) + payload


class DoubaoStreamTests(unittest.TestCase):
    def setUp(self):
        self.provider = ASRProvider({
            'appid': 'test', 'access_token': 'test-secret',
            'resource_id': 'volc.seedasr.sauc.duration',
            'ws_url': 'wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_async',
            'enable_nonstream': True, 'result_type': 'full',
        }, True)

    def test_v2_resource_and_request_do_not_embed_credentials(self):
        self.assertEqual(self.provider.token_auth()['X-Api-Resource-Id'], 'volc.seedasr.sauc.duration')
        request = self.provider.construct_request('test')
        self.assertNotIn('test-secret', json.dumps(request))
        self.assertEqual(request['request']['model_name'], 'bigmodel')
        self.assertTrue(request['request']['enable_nonstream'])

    def test_compressed_and_uncompressed_with_optional_sequence(self):
        body = {'result': {'text': '你好'}}
        for compressed in (True, False):
            for flags in (0, 1, 2, 3):
                with self.subTest(compressed=compressed, flags=flags):
                    parsed = self.provider.parse_response(response(body, flags, compressed))
                    self.assertEqual(parsed['payload_msg'], body)
                    self.assertEqual(parsed['is_last'], bool(flags & 2))

    def test_error_and_truncated_payload(self):
        payload = gzip.compress(b'{"error":"quota"}')
        frame = bytes([0x11, 0xf0, 0x11, 0]) + struct.pack('>II', 45000001, len(payload)) + payload
        self.assertEqual(self.provider.parse_response(frame)['code'], 45000001)
        with self.assertRaises(ValueError):
            self.provider.parse_response(frame[:-1])

    def test_browser_pcm_is_not_decoded_as_opus(self):
        self.provider.decoder = Mock()
        pcm = bytes(1920)
        self.assertEqual(self.provider._decode_audio(SimpleNamespace(audio_format='pcm'), pcm), pcm)
        self.provider.decoder.decode.assert_not_called()
        self.assertEqual(self.provider.generate_audio_default_header()[2], 0x01)

    def test_short_speech_protection_is_sent(self):
        request = self.provider.construct_request('test')
        self.assertEqual(request['request']['force_to_speech_time'], 1000)


class FinalResultTests(unittest.IsolatedAsyncioTestCase):
    async def test_prepare_stream_connects_before_first_voice(self):
        p = ASRProvider({
            'appid': 'test', 'access_token': 'test-secret',
            'resource_id': 'volc.seedasr.sauc.duration',
            'result_type': 'full',
        }, True)
        websocket = SimpleNamespace(
            send=AsyncMock(),
            recv=AsyncMock(return_value=response({'result': {}})),
            close=AsyncMock(),
        )
        hold = asyncio.Event()

        async def hold_forward(_conn):
            await hold.wait()

        p._forward_asr_results = hold_forward
        conn = SimpleNamespace(asr_audio=[])
        with patch('core.providers.asr.doubao_stream.websockets.connect', AsyncMock(return_value=websocket)) as connect:
            ready = await p.prepare_stream(conn)

        self.assertTrue(ready)
        self.assertTrue(p.stream_ready)
        connect.assert_awaited_once()
        websocket.send.assert_awaited_once()
        hold.set()
        await p.forward_task
        await p.close()

    async def test_short_definite_utterance_is_delivered(self):
        p = ASRProvider({'result_type': 'full'}, True)
        p.asr_ws = SimpleNamespace(
            recv=AsyncMock(side_effect=[
                response({'result': {'text': '打开智能床', 'utterances': [{'text': '打开智能床', 'definite': True}]}}),
                response({'result': {'text': ''}}, 3),
            ]),
            close=AsyncMock(),
        )
        p.handle_voice_stop = AsyncMock()
        conn = SimpleNamespace(stop_event=SimpleNamespace(is_set=lambda: False),
                               asr_audio=[bytes(640)] * 5, reset_audio_states=Mock(),
                               client_listen_mode='auto', client_voice_stop=False)
        await p._forward_asr_results(conn)
        p.handle_voice_stop.assert_awaited()


    async def test_manual_release_delivers_final_text_without_utterances(self):
        p = ASRProvider({'result_type': 'full'}, True)
        p.text = '早期识别'
        p.asr_ws = SimpleNamespace(
            recv=AsyncMock(return_value=response({'result': {'text': '最终识别。'}}, 3)),
            close=AsyncMock(),
        )
        p.handle_voice_stop = AsyncMock()
        conn = SimpleNamespace(stop_event=SimpleNamespace(is_set=lambda: False),
                               asr_audio=[bytes(640)], reset_audio_states=Mock())
        await p._forward_asr_results(conn)
        self.assertEqual(p.text, '最终识别。')
        p.handle_voice_stop.assert_awaited_once()


if __name__ == '__main__':
    unittest.main()
