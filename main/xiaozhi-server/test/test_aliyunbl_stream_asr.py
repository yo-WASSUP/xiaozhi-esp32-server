import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import yaml

with (
    patch("config.logger.check_config_file"),
    patch("config.logger.load_config", return_value={"log": {}}),
):
    from core.providers.asr.aliyunbl_stream import ASRProvider


def build_provider_config(model, **overrides):
    config = {
        "api_key": "test-key",
        "model": model,
        "format": "pcm",
        "sample_rate": 16000,
        "semantic_punctuation_enabled": False,
        "max_sentence_silence": 1200,
        "multi_threshold_mode_enabled": False,
        "punctuation_prediction_enabled": True,
        "language_hints": ["zh"],
        **overrides,
    }
    provider = ASRProvider(config, delete_audio_file=True)
    provider.task_id = "test-task"
    return provider


class AliyunBLStreamASRRequestTests(unittest.TestCase):
    def test_qwen_streaming_request_uses_supported_parameters(self):
        provider = build_provider_config(
            "qwen-audio-3.0-asr-flash-streaming",
            disfluency_removal_enabled=True,
            inverse_text_normalization_enabled=True,
            heartbeat=True,
            speech_noise_threshold=0.1,
            vocabulary={"安宁疗护": 5},
        )

        message = provider._build_run_task_message()
        parameters = message["payload"]["parameters"]

        self.assertEqual(
            message["payload"]["model"],
            "qwen-audio-3.0-asr-flash-streaming",
        )
        self.assertTrue(parameters["heartbeat"])
        self.assertEqual(parameters["speech_noise_threshold"], 0.1)
        self.assertEqual(parameters["vocabulary"], {"安宁疗护": 5})
        self.assertNotIn("disfluency_removal_enabled", parameters)
        self.assertNotIn("inverse_text_normalization_enabled", parameters)

    def test_paraformer_request_keeps_paraformer_parameters(self):
        provider = build_provider_config(
            "paraformer-realtime-v2",
            disfluency_removal_enabled=True,
            inverse_text_normalization_enabled=True,
            speech_noise_threshold=0.1,
            vocabulary={"安宁疗护": 5},
        )

        parameters = provider._build_run_task_message()["payload"]["parameters"]

        self.assertTrue(parameters["disfluency_removal_enabled"])
        self.assertTrue(parameters["inverse_text_normalization_enabled"])
        self.assertNotIn("speech_noise_threshold", parameters)
        self.assertNotIn("vocabulary", parameters)


class AliyunBLStreamASRLifecycleTests(unittest.IsolatedAsyncioTestCase):
    def build_provider(self):
        provider = ASRProvider.__new__(ASRProvider)
        provider.asr_ws = AsyncMock()
        provider.task_id = "test-task"
        provider.task_started = False
        provider.task_terminal = False
        provider.finish_sent = False
        return provider

    async def test_finish_is_not_sent_before_task_started(self):
        provider = self.build_provider()

        await provider._send_finish_task()

        provider.asr_ws.send.assert_not_awaited()
        self.assertFalse(provider.finish_sent)

    async def test_finish_is_sent_only_once(self):
        provider = self.build_provider()
        provider.task_started = True

        await provider._send_finish_task()
        await provider._send_finish_task()

        provider.asr_ws.send.assert_awaited_once()
        message = yaml.safe_load(provider.asr_ws.send.await_args.args[0])
        self.assertEqual(message["header"]["action"], "finish-task")
        self.assertTrue(provider.finish_sent)


class HospiceASRConfigTests(unittest.TestCase):
    def test_example_keeps_paraformer_and_qwen_as_switchable_providers(self):
        config_path = (
            Path(__file__).resolve().parents[1]
            / "data"
            / ".config_hospice.example.yaml"
        )
        config = yaml.safe_load(config_path.read_text(encoding="utf-8"))

        self.assertEqual(
            config["selected_module"]["ASR"],
            "AliyunBLStreamASR",
        )
        self.assertEqual(
            config["ASR"]["AliyunBLStreamASR"]["model"],
            "paraformer-realtime-v2",
        )
        self.assertEqual(
            config["ASR"]["QwenAudioStreamASR"]["model"],
            "qwen-audio-3.0-asr-flash-streaming",
        )
        self.assertEqual(
            config["ASR"]["AliyunBLStreamASR"]["api_key"],
            config["ASR"]["QwenAudioStreamASR"]["api_key"],
        )


class AliyunBLStreamASRLanguageFilterTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.provider = ASRProvider.__new__(ASRProvider)
        self.provider.language_hints = ["zh"]
        self.conn = SimpleNamespace(
            _last_speaker_name="",
            client_voice_stop_time=0,
            dignity_active=False,
            voiceprint_provider=None,
        )

    async def test_pure_english_result_is_discarded(self):
        self.provider.text = "She."

        with patch(
            "core.providers.asr.aliyunbl_stream.startToChat",
            new=AsyncMock(),
        ) as start_to_chat, patch(
            "core.providers.asr.aliyunbl_stream.enqueue_asr_report"
        ) as enqueue_report:
            await self.provider.handle_voice_stop(self.conn, [])

        start_to_chat.assert_not_awaited()
        enqueue_report.assert_not_called()

    async def test_chinese_result_is_forwarded(self):
        self.provider.text = "是的。"

        with patch(
            "core.providers.asr.aliyunbl_stream.startToChat",
            new=AsyncMock(),
        ) as start_to_chat, patch(
            "core.providers.asr.aliyunbl_stream.enqueue_asr_report"
        ) as enqueue_report:
            await self.provider.handle_voice_stop(self.conn, [])

        start_to_chat.assert_awaited_once_with(self.conn, "是的。")
        enqueue_report.assert_called_once_with(self.conn, "是的。", [])

    async def test_short_mixed_fragments_do_not_reach_chat_or_reporting(self):
        for text in ("W辉。", "帮h. ", "嗯 A", "h你好"):
            with self.subTest(text=text):
                self.provider.text = text
                with patch(
                    "core.providers.asr.aliyunbl_stream.startToChat", new=AsyncMock()
                ) as start_to_chat, patch(
                    "core.providers.asr.aliyunbl_stream.enqueue_asr_report"
                ) as enqueue_report:
                    await self.provider.handle_voice_stop(self.conn, [])
                start_to_chat.assert_not_awaited()
                enqueue_report.assert_not_called()
                self.assertEqual(self.provider.text, "")

    async def test_valid_mixed_expressions_and_multilingual_fragments_are_forwarded(self):
        for text, hints in (
            ("WiFi坏了", ["zh"]),
            ("打开 TV", ["zh"]),
            ("维生素C", ["zh"]),
            ("去A1床", ["zh"]),
            ("W辉。", ["zh", "en"]),
        ):
            with self.subTest(text=text, hints=hints):
                self.provider.language_hints = hints
                self.provider.text = text
                with patch(
                    "core.providers.asr.aliyunbl_stream.startToChat", new=AsyncMock()
                ) as start_to_chat, patch(
                    "core.providers.asr.aliyunbl_stream.enqueue_asr_report"
                ):
                    await self.provider.handle_voice_stop(self.conn, [])
                start_to_chat.assert_awaited_once_with(self.conn, text)

    async def test_mixed_chinese_and_english_result_is_forwarded(self):
        self.provider.text = "请检查 WiFi。"

        with patch(
            "core.providers.asr.aliyunbl_stream.startToChat",
            new=AsyncMock(),
        ) as start_to_chat, patch(
            "core.providers.asr.aliyunbl_stream.enqueue_asr_report"
        ) as enqueue_report:
            await self.provider.handle_voice_stop(self.conn, [])

        start_to_chat.assert_awaited_once_with(self.conn, "请检查 WiFi。")
        enqueue_report.assert_called_once_with(self.conn, "请检查 WiFi。", [])

    async def test_english_result_is_forwarded_when_english_is_configured(self):
        self.provider.language_hints = ["zh", "en"]
        self.provider.text = "Hello."

        with patch(
            "core.providers.asr.aliyunbl_stream.startToChat",
            new=AsyncMock(),
        ) as start_to_chat, patch(
            "core.providers.asr.aliyunbl_stream.enqueue_asr_report"
        ) as enqueue_report:
            await self.provider.handle_voice_stop(self.conn, [])

        start_to_chat.assert_awaited_once_with(self.conn, "Hello.")
        enqueue_report.assert_called_once_with(self.conn, "Hello.", [])


if __name__ == "__main__":
    unittest.main()
