import unittest

from core.connection_parts.chat import (
    _StreamingStageDirectionFilter,
    _strip_leading_stage_directions,
)


class StageDirectionFilterTest(unittest.TestCase):
    def test_removes_leading_stage_direction(self):
        text = "（温和地笑着）您是想把字调大一点哈？"
        self.assertEqual(
            _strip_leading_stage_directions(text),
            "您是想把字调大一点哈？",
        )

    def test_preserves_meaningful_parenthetical(self):
        text = "（这只是一个建议）您可以先问问护士。"
        self.assertEqual(_strip_leading_stage_directions(text), text)

    def test_filters_stage_direction_split_across_stream_chunks(self):
        stream_filter = _StreamingStageDirectionFilter()
        chunks = ["（温", "和地笑着）您是", "想把字调大一点哈？"]

        spoken = "".join(stream_filter.feed(chunk) for chunk in chunks)
        spoken += stream_filter.flush()

        self.assertEqual(spoken, "您是想把字调大一点哈？")

    def test_preserves_unclosed_parenthetical_on_flush(self):
        stream_filter = _StreamingStageDirectionFilter()
        self.assertEqual(stream_filter.feed("（这句话还没说完"), "")
        self.assertEqual(stream_filter.flush(), "（这句话还没说完")


if __name__ == "__main__":
    unittest.main()
