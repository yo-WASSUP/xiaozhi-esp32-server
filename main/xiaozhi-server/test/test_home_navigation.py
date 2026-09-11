"""首页语音导航规则回归测试，无外部服务依赖。"""
import importlib.util
from pathlib import Path
import unittest
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

spec = importlib.util.spec_from_file_location(
    "patient_actions", Path(__file__).resolve().parents[1] / "core/api/hospice/patient_actions.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class HomeNavigationTests(unittest.TestCase):
    def test_all_six_modules_and_aliases(self):
        for app_id, phrases in module.HOME_APP_PHRASES.items():
            for phrase in phrases:
                for prefix in ("", "打开", "安安，请帮我打开"):
                    with self.subTest(phrase=prefix + phrase):
                        self.assertEqual(module.detect_home_app(prefix + phrase), app_id)
        self.assertEqual(module.detect_home_app("我想说说话"), "voice")

    def test_negation_conversation_and_ambiguous_commands_stay_home(self):
        for text in ("不要打开智能床", "别进入芳香疗法", "我不想聊聊天", "数字疗法是什么", "打开家属消息和智能床", "返回首页", "", "今天天气很好"):
            with self.subTest(text=text):
                self.assertIsNone(module.detect_home_app(text))

    def test_existing_actions_are_unchanged(self):
        self.assertEqual(module.detect_patient_action("接电话")["action"], "accept_call")
        self.assertEqual(module.detect_patient_action("播放家属消息")["action"], "read_family_messages")


class HomeWindowTests(unittest.IsolatedAsyncioTestCase):
    async def test_wakeup_prepares_stream_immediately(self):
        spec = importlib.util.spec_from_file_location(
            "home_window_prepare", Path(__file__).resolve().parents[1] / "core/api/hospice/home_navigation.py"
        )
        window = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(window)
        prepare_stream = AsyncMock(return_value=True)
        conn = SimpleNamespace(
            asr=SimpleNamespace(prepare_stream=prepare_stream, stop_ws_connection=Mock()),
            reset_audio_states=Mock(),
        )

        window.start_home_listening(conn)
        await asyncio.sleep(0)

        prepare_stream.assert_awaited_once_with(conn)
        self.assertEqual(window.HOME_LISTEN_SECONDS, 20)
        await window.stop_home_listening(conn)

    async def test_server_deadline_closes_asr_and_cannot_be_extended(self):
        spec = importlib.util.spec_from_file_location(
            "home_window", Path(__file__).resolve().parents[1] / "core/api/hospice/home_navigation.py"
        )
        window = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(window)
        window.HOME_LISTEN_SECONDS = 0.02
        conn = SimpleNamespace(asr=SimpleNamespace(stop_ws_connection=Mock()), reset_audio_states=Mock())
        window.start_home_listening(conn)
        timer = conn.hospice_home_timer
        window.start_home_listening(conn)
        self.assertIs(timer, conn.hospice_home_timer)
        await asyncio.sleep(0.05)
        self.assertFalse(conn.hospice_home_listening)
        conn.asr.stop_ws_connection.assert_called_once()
        conn.reset_audio_states.assert_called_once()
        window.start_home_listening(conn)
        await window.stop_home_listening(conn)
        self.assertFalse(conn.hospice_home_listening)
        self.assertIsNone(conn.hospice_home_timer)


if __name__ == "__main__":
    unittest.main()
