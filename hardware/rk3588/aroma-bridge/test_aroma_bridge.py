import unittest

from aroma_bridge import _normalize_params


class AromaBridgeParamTests(unittest.TestCase):
    def test_start_uses_defaults(self):
        self.assertEqual(
            _normalize_params("aroma.start", {}),
            {"type": "1", "duration_ms": 60000},
        )

    def test_stop_discards_params(self):
        self.assertEqual(
            _normalize_params(
                "aroma.stop",
                {"type": "3", "duration_ms": 600000},
            ),
            {},
        )

    def test_duration_is_clamped(self):
        self.assertEqual(
            _normalize_params("aroma.start", {"duration_ms": 500})["duration_ms"],
            1000,
        )
        self.assertEqual(
            _normalize_params("aroma.start", {"duration_ms": 1900000})["duration_ms"],
            1800000,
        )

    def test_invalid_type_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "invalid aroma type"):
            _normalize_params("aroma.start", {"type": "9"})

    def test_relax_scene_requires_type_one(self):
        with self.assertRaisesRegex(ValueError, "requires type 1"):
            _normalize_params("aroma.scene_relax", {"type": "2"})

    def test_zero_and_non_integer_duration_are_rejected(self):
        for duration_ms in (0, -1, "1000", True):
            with self.subTest(duration_ms=duration_ms):
                with self.assertRaisesRegex(ValueError, "duration_ms"):
                    _normalize_params("aroma.start", {"duration_ms": duration_ms})


if __name__ == "__main__":
    unittest.main()
