import unittest

from bed_bridge import SUPPORTED_BED_ACTIONS, _validate_command


class BedBridgeCommandTests(unittest.TestCase):
    def test_all_protocol_actions_are_supported(self):
        self.assertEqual(len(SUPPORTED_BED_ACTIONS), 14)
        for action_id in SUPPORTED_BED_ACTIONS:
            with self.subTest(action_id=action_id):
                self.assertEqual(
                    _validate_command({"action_id": action_id, "params": {}}),
                    action_id,
                )

    def test_head_and_feet_reset_are_supported(self):
        for action_id in ("bed.head.reset", "bed.feet.reset"):
            with self.subTest(action_id=action_id):
                self.assertEqual(
                    _validate_command({"action_id": action_id, "params": {}}),
                    action_id,
                )

    def test_unknown_action_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "unsupported bed action_id"):
            _validate_command({"action_id": "bed.head.4", "params": {}})

    def test_non_empty_params_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "empty JSON object"):
            _validate_command({"action_id": "bed.head.up", "params": {"step": 10}})


if __name__ == "__main__":
    unittest.main()
