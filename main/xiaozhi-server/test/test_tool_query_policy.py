import unittest

from core.providers.tools.query_policy import (
    filter_weather_context_for_query,
    filter_tool_calls_for_query,
    filter_tools_for_query,
)


WEATHER_TOOL = {
    "type": "function",
    "function": {"name": "get_weather", "description": "查询天气"},
}
OTHER_TOOL = {
    "type": "function",
    "function": {"name": "robot_base_get_status", "description": "查询底盘状态"},
}


class ToolQueryPolicyTests(unittest.TestCase):
    def test_weather_tool_is_only_available_for_explicit_weather_questions(self):
        for query in ("查询一下天气", "成都天气怎么样？", "今天多少度？", "明天会下雨吗？"):
            with self.subTest(query=query):
                tools = filter_tools_for_query([WEATHER_TOOL, OTHER_TOOL], query)
                self.assertEqual(
                    [tool["function"]["name"] for tool in tools],
                    ["get_weather", "robot_base_get_status"],
                )

        for query in ("别讲这个了。", "讲个笑话吧。", "我喜欢下雨天。", "今天天气真不错。"):
            with self.subTest(query=query):
                tools = filter_tools_for_query([WEATHER_TOOL, OTHER_TOOL], query)
                self.assertEqual(
                    [tool["function"]["name"] for tool in tools],
                    ["robot_base_get_status"],
                )

    def test_weather_call_is_rejected_when_current_message_did_not_ask_weather(self):
        calls = [
            {"id": "weather", "name": "get_weather", "arguments": "{}"},
            {"id": "status", "name": "robot_base_get_status", "arguments": "{}"},
        ]

        allowed = filter_tool_calls_for_query(calls, "别讲这个了。")

        self.assertEqual([call["name"] for call in allowed], ["robot_base_get_status"])

    def test_weather_question_inside_speaker_json_is_allowed(self):
        query = '{"speaker":"张三","content":"查询一下成都天气"}'

        tools = filter_tools_for_query([WEATHER_TOOL], query)

        self.assertEqual([tool["function"]["name"] for tool in tools], ["get_weather"])

    def test_non_weather_message_hides_proactive_weather_memory_for_this_turn(self):
        memory = (
            "居住地: 成都\n"
            "陪伴建议:\n"
            "- 可主动提及天气情况\n"
            "- 喜欢听老歌\n"
        )

        filtered = filter_weather_context_for_query(memory, "别讲这个了。")
        weather_query_context = filter_weather_context_for_query(memory, "成都天气怎么样？")

        self.assertNotIn("主动提及天气", filtered)
        self.assertIn("喜欢听老歌", filtered)
        self.assertEqual(weather_query_context, memory)


if __name__ == "__main__":
    unittest.main()
