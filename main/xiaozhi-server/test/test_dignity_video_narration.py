import unittest

from core.dignity.video.renderer import _resolve_narration_tts_provider


class DignityVideoNarrationTests(unittest.TestCase):
    def test_uses_explicit_narration_provider(self):
        config = {
            "selected_module": {"TTS": "HuoshanDoubleStreamTTS"},
            "hospice": {"life_review_narration_tts": "AliBLTTS"},
            "TTS": {
                "HuoshanDoubleStreamTTS": {"type": "huoshan_double_stream"},
                "AliBLTTS": {"type": "alibl_stream"},
            },
        }

        self.assertEqual(_resolve_narration_tts_provider(config), "AliBLTTS")

    def test_prefers_cosyvoice_for_narration_when_not_explicitly_configured(self):
        config = {
            "selected_module": {"TTS": "HuoshanDoubleStreamTTS"},
            "TTS": {
                "HuoshanDoubleStreamTTS": {"type": "huoshan_double_stream"},
                "AliBLTTS": {"type": "alibl_stream"},
            },
        }

        self.assertEqual(_resolve_narration_tts_provider(config), "AliBLTTS")

    def test_rejects_unknown_explicit_provider(self):
        config = {
            "hospice": {"life_review_narration_tts": "MissingTTS"},
            "TTS": {},
        }

        with self.assertRaisesRegex(ValueError, "MissingTTS"):
            _resolve_narration_tts_provider(config)


if __name__ == "__main__":
    unittest.main()
