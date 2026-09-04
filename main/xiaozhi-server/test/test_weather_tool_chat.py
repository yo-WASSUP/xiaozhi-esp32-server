import asyncio
import concurrent.futures
import queue
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from core.connection_parts.chat import ChatMixin
from core.providers.tts.dto.dto import SentenceType
from core.utils.dialogue import Dialogue, Message
from plugins_func.register import Action, ActionResponse


WEATHER_REPLY = "今天成都多云，32度，有点热。傍晚出去走走倒合适，凉快些嘛。"


class _Logger:
    def bind(self, **_kwargs):
        return self

    def debug(self, *_args, **_kwargs):
        pass

    info = debug
    warning = debug
    error = debug


class _WeatherLLM:
    model_name = "weather-replay"

    def response_with_functions(self, _session_id, _dialogue, functions=None):
        tool_call = SimpleNamespace(
            index=0,
            id="call-weather",
            function=SimpleNamespace(
                name="get_weather",
                arguments='{"location":"成都","lang":"zh_CN"}',
            ),
        )
        return iter(
            [
                ("我帮您看看成都的天气哈。", None),
                (None, [tool_call]),
            ]
        )

    def response(self, _session_id, _dialogue):
        return iter([WEATHER_REPLY])


class _DirectWeatherLLM:
    model_name = "direct-weather-replay"

    def response_with_functions(self, _session_id, _dialogue, functions=None):
        return iter([(WEATHER_REPLY, None)])

    def response(self, _session_id, _dialogue):
        raise AssertionError("direct answer must not trigger a second LLM call")


class _SameChunkWeatherLLM(_WeatherLLM):
    model_name = "same-chunk-weather-replay"

    def response_with_functions(self, _session_id, _dialogue, functions=None):
        tool_call = SimpleNamespace(
            index=0,
            id="call-weather",
            function=SimpleNamespace(
                name="get_weather",
                arguments='{"location":"成都","lang":"zh_CN"}',
            ),
        )
        return iter([("我帮您看看成都的天气哈。", [tool_call])])


class _WeatherToolHandler:
    def get_functions(self):
        return [
            {
                "type": "function",
                "function": {"name": "get_weather", "description": "查询天气"},
            }
        ]

    async def handle_llm_function_call(self, _conn, _tool_call):
        return ActionResponse(Action.REQLLM, result="成都：多云，32℃")


class _ReplayConnection(ChatMixin):
    pass


class WeatherToolChatTests(unittest.TestCase):
    def _run_weather_chat(self, llm):
        conn = _ReplayConnection()
        conn.logger = _Logger()
        conn.dialogue = Dialogue()
        conn.dialogue.put(Message(role="system", content="你是语音助手"))
        conn.tts = SimpleNamespace(tts_text_queue=queue.Queue())
        conn.intent_type = "function_call"
        conn.func_handler = _WeatherToolHandler()
        conn.llm = llm
        conn.memory = None
        conn.loop = object()
        conn.session_id = "session-weather"
        conn.websocket = SimpleNamespace(send=AsyncMock())
        conn.config = {"voiceprint": {}, "hospice": {"enable_logging": False}}
        conn.device_id = "device-weather"
        conn.client_abort = False

        async def no_emotion(_conn, _content):
            return None

        def run_immediately(coroutine, _loop=None, **_kwargs):
            future = concurrent.futures.Future()
            try:
                future.set_result(asyncio.run(coroutine))
            except Exception as exc:
                future.set_exception(exc)
            return future

        with patch(
            "core.connection_parts.chat.textUtils.get_emotion", no_emotion
        ), patch(
            "core.connection_parts.chat.asyncio.run_coroutine_threadsafe",
            side_effect=run_immediately,
        ):
            result = conn.chat("成都的天气怎么样。")

        queued = []
        while not conn.tts.tts_text_queue.empty():
            queued.append(conn.tts.tts_text_queue.get_nowait())
        spoken_text = "".join(
            message.content_detail or ""
            for message in queued
            if message.sentence_type == SentenceType.MIDDLE
        )

        return result, spoken_text

    def test_weather_tool_discards_model_preamble_before_tts(self):
        result, spoken_text = self._run_weather_chat(_WeatherLLM())

        self.assertTrue(result)
        self.assertEqual(spoken_text, WEATHER_REPLY)

    def test_direct_weather_answer_is_released_when_no_tool_is_called(self):
        result, spoken_text = self._run_weather_chat(_DirectWeatherLLM())

        self.assertTrue(result)
        self.assertEqual(spoken_text, WEATHER_REPLY)

    def test_weather_tool_discards_preamble_when_tool_arrives_in_same_chunk(self):
        result, spoken_text = self._run_weather_chat(_SameChunkWeatherLLM())

        self.assertTrue(result)
        self.assertEqual(spoken_text, WEATHER_REPLY)


if __name__ == "__main__":
    unittest.main()
