import unittest
from unittest.mock import patch

from core.robot_actions.contract import ACTION_EXAMPLES
from core.robot_actions.voice_lexicon import build_hardware_vocabulary


class HardwareVoiceVocabularyTests(unittest.TestCase):
    def test_only_enabled_hardware_modules_contribute_hotwords(self):
        config = {
            "hospice": {
                "robot_bed": {"enabled": True},
                "robot_arm": {"enabled": False},
                "robot_aroma": {"enabled": False},
                "robot_base": {"enabled": False},
            }
        }

        vocabulary = build_hardware_vocabulary(config)

        self.assertEqual(vocabulary["床头升高"], 4)
        self.assertEqual(vocabulary["床尾停止运动"], 4)
        self.assertNotIn("挥挥手", vocabulary)
        self.assertNotIn("打开香薰", vocabulary)
        self.assertNotIn("往前走", vocabulary)

    def test_all_direct_voice_hardware_actions_have_hotwords(self):
        config = {
            "hospice": {
                "robot_bed": {"enabled": True},
                "robot_arm": {"enabled": True},
                "robot_aroma": {"enabled": True},
                "robot_base": {"enabled": True},
            }
        }

        vocabulary = build_hardware_vocabulary(config)

        expected_phrases = {
            "停止当前动作",
            "继续动作",
            "往前走",
            "向左转",
            "导航到",
            "回充电桩",
            "挥动左手",
            "安抚一下",
            "恢复原位",
            "打开香薰",
            "关闭香薰",
            "开启放松香薰",
            "床头升高",
            "床尾三档",
            "叫护士",
        }
        self.assertTrue(expected_phrases.issubset(vocabulary))
        self.assertNotIn("开心", vocabulary)
        self.assertNotIn("平静", vocabulary)

    def test_enabled_hardware_action_examples_are_all_asr_hotwords(self):
        config = {
            "hospice": {
                "robot_bed": {"enabled": True},
                "robot_arm": {"enabled": True},
                "robot_aroma": {"enabled": True},
                "robot_base": {"enabled": True},
            }
        }

        vocabulary = build_hardware_vocabulary(config)

        direct_voice_modules = {"system", "base", "arm", "aroma", "bed", "notify"}
        for action_id, examples in ACTION_EXAMPLES.items():
            if action_id.split(".", 1)[0] not in direct_voice_modules:
                continue
            for phrase in examples:
                with self.subTest(action_id=action_id, phrase=phrase):
                    self.assertEqual(vocabulary[phrase], 4)

    def test_configured_vocabulary_is_preserved_and_can_raise_weight(self):
        config = {"hospice": {"robot_bed": {"enabled": True}}}

        vocabulary = build_hardware_vocabulary(
            config,
            {"安宁疗护": 5, "床头升高": 5},
        )

        self.assertEqual(vocabulary["安宁疗护"], 5)
        self.assertEqual(vocabulary["床头升高"], 5)
        self.assertEqual(vocabulary["床头降低"], 4)

    def test_hardware_hotwords_require_robot_voice_actions(self):
        existing = {"安宁疗护": 5}

        without_hospice = build_hardware_vocabulary({}, existing)
        explicitly_disabled = build_hardware_vocabulary(
            {
                "hospice": {
                    "enable_robot_voice_actions": False,
                    "robot_bed": {"enabled": True},
                }
            },
            existing,
        )

        self.assertEqual(without_hospice, existing)
        self.assertEqual(explicitly_disabled, existing)

    def test_qwen_asr_initialization_receives_enabled_hardware_hotwords(self):
        config = {
            "selected_module": {"ASR": "QwenAudioStreamASR"},
            "ASR": {
                "QwenAudioStreamASR": {
                    "type": "aliyunbl_stream",
                    "api_key": "test-key",
                    "model": "qwen-audio-3.0-asr-flash-streaming",
                    "vocabulary": {"安宁疗护": 5},
                }
            },
            "hospice": {"robot_bed": {"enabled": True}},
        }

        with (
            patch("config.logger.check_config_file"),
            patch("config.logger.load_config", return_value={"log": {}}),
        ):
            from core.utils.modules_initialize import initialize_asr

            provider = initialize_asr(config)
        request_vocabulary = provider._build_run_task_message()["payload"][
            "parameters"
        ]["vocabulary"]

        self.assertEqual(provider.vocabulary["安宁疗护"], 5)
        self.assertEqual(provider.vocabulary["床头升高"], 4)
        self.assertEqual(request_vocabulary["床头升高"], 4)
if __name__ == "__main__":
    unittest.main()
