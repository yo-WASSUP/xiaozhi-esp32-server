import asyncio
import io
import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from core.api.hospice.voice import HospiceVoiceMixin
from core.handle.helloHandle import handleHelloMessage
from core.providers.tts.huoshan_double_stream import TTSProvider as DoubaoTTSProvider
from core.utils.hospice_tts import (
    build_aliyun_cloned_tts_config,
    is_aliyun_cloned_voice_active,
)


class FakeTTS:
    def __init__(self):
        self.conn = None
        self.closed = 0
        self.applied = 0

    async def open_audio_channels(self, conn):
        self.conn = conn

    async def close(self):
        self.closed += 1

    def _apply_hospice_voice_settings(self, conn):
        self.applied += 1


class HospiceTTSConfigTest(unittest.TestCase):
    def test_cloned_voice_uses_aliyun_config_while_default_stays_doubao(self):
        config = {
            "selected_module": {"TTS": "HuoshanDoubleStreamTTS"},
            "TTS": {
                "HuoshanDoubleStreamTTS": {
                    "type": "huoshan_double_stream",
                    "speaker": "doubao-default",
                },
                "AliBLTTS": {
                    "type": "alibl_stream",
                    "api_key": "aliyun-key",
                    "model": "cosyvoice-v2",
                },
            },
        }
        settings = {
            "active": True,
            "provider": "aliyun_cosyvoice",
            "voice_id": "cosyvoice-v3.5-flash-cloned",
            "model": "cosyvoice-v3.5-flash",
        }

        cloned_config = build_aliyun_cloned_tts_config(config, settings)

        self.assertTrue(is_aliyun_cloned_voice_active(settings))
        self.assertEqual(cloned_config["api_key"], "aliyun-key")
        self.assertEqual(cloned_config["private_voice"], settings["voice_id"])
        self.assertEqual(cloned_config["model"], settings["model"])
        self.assertEqual(
            config["selected_module"]["TTS"], "HuoshanDoubleStreamTTS"
        )
        self.assertNotIn("private_voice", config["TTS"]["AliBLTTS"])

    def test_doubao_provider_ignores_aliyun_cloned_voice_id(self):
        provider = DoubaoTTSProvider.__new__(DoubaoTTSProvider)
        provider.base_voice = "doubao-default"
        provider.voice = "doubao-default"
        provider.base_resource_id = "doubao-resource"
        provider.resource_id = "doubao-resource"
        settings_yaml = """
device-1:
  active: true
  provider: aliyun_cosyvoice
  speaker_id: cosyvoice-v3.5-flash-cloned
"""

        with patch(
            "core.providers.tts.huoshan_double_stream.os.path.exists",
            return_value=True,
        ), patch("builtins.open", return_value=io.StringIO(settings_yaml)):
            provider._apply_hospice_voice_settings(
                SimpleNamespace(device_id="device-1")
            )

        self.assertEqual(provider.voice, "doubao-default")
        self.assertEqual(provider.resource_id, "doubao-resource")


class HospiceTTSSwitchTest(unittest.IsolatedAsyncioTestCase):
    async def test_aliyun_clone_forces_patient_app_out_of_doubao_s2s(self):
        websocket = SimpleNamespace(send=AsyncMock())
        conn = SimpleNamespace(
            client_name="",
            config={"realtime_voice": {"doubao_s2s": {"enabled": True}}},
            device_id="device-1",
            voice_mode="cascade",
            realtime_voice=None,
            welcome_msg={},
            websocket=websocket,
        )
        settings = {
            "active": True,
            "provider": "aliyun_cosyvoice",
            "voice_id": "cosyvoice-v3.5-flash-cloned",
        }

        with patch(
            "core.handle.helloHandle.load_hospice_voice_settings",
            return_value=settings,
        ):
            await handleHelloMessage(
                conn,
                {"device_name": "patient-app", "voice_mode": "doubao_s2s"},
            )

        self.assertEqual(conn.voice_mode, "cascade")
        self.assertIsNone(conn.realtime_voice)
        self.assertEqual(websocket.send.await_count, 2)
        mode_event = json.loads(websocket.send.await_args_list[1].args[0])
        self.assertEqual(mode_event["mode"], "cascade")
        self.assertEqual(mode_event["requested_mode"], "doubao_s2s")
        self.assertIn("克隆音色", mode_event["reason"])

    async def test_online_device_switches_to_clone_and_back_to_default(self):
        default_tts = FakeTTS()
        default_tts.conn = object()
        clone_tts = FakeTTS()
        conn = SimpleNamespace(
            tts=default_tts,
            config={"selected_module": {"TTS": "HuoshanDoubleStreamTTS"}},
            loop=asyncio.get_running_loop(),
        )
        voice_settings = {
            "active": True,
            "provider": "aliyun_cosyvoice",
            "voice_id": "cosyvoice-v3.5-flash-cloned",
        }
        mixin = HospiceVoiceMixin()

        with patch(
            "core.api.hospice.voice.ConnectionHandler.get_active_connection",
            return_value=conn,
        ), patch(
            "core.api.hospice.voice.create_aliyun_cloned_tts",
            return_value=clone_tts,
        ):
            applied = await mixin._apply_voice_settings_to_active_connection(
                "device-1", voice_settings
            )

        self.assertTrue(applied)
        self.assertIs(conn.tts, clone_tts)
        self.assertIs(conn._hospice_default_tts, default_tts)
        self.assertEqual(clone_tts.applied, 1)
        self.assertIs(clone_tts.conn, conn)
        self.assertEqual(default_tts.closed, 1)

        with patch(
            "core.api.hospice.voice.ConnectionHandler.get_active_connection",
            return_value=conn,
        ):
            applied = await mixin._apply_voice_settings_to_active_connection(
                "device-1", {}
            )

        self.assertTrue(applied)
        self.assertIs(conn.tts, default_tts)
        self.assertEqual(clone_tts.closed, 1)


if __name__ == "__main__":
    unittest.main()
