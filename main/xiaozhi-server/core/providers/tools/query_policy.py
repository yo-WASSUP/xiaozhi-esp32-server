from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List


_WEATHER_TOPIC = r"(?:天气预报|天气|气温|温度|降雨|降雪|空气质量|湿度|风力)"
_WEATHER_REQUEST_PATTERNS = (
    re.compile(
        rf"(?:查|查询|查一下|看一下|看看|问一下|问下|告诉我|想知道).{{0,10}}{_WEATHER_TOPIC}"
    ),
    re.compile(
        rf"{_WEATHER_TOPIC}.{{0,8}}(?:怎么样|如何|多少|几度|什么情况|好吗|会怎样|吗|嘛|呢)"
    ),
    re.compile(
        r"(?:今天|明天|后天|这两天|最近|外面)?.{0,6}"
        r"(?:多少度|几度|冷不冷|热不热|冷吗|热吗|会不会下雨|会下雨吗|"
        r"下不下雨|有没有雨|要下雨吗|会不会下雪|会下雪吗|要不要带伞)"
    ),
)
_DIRECT_WEATHER_REQUESTS = {
    "天气",
    "天气预报",
    "查天气",
    "查询天气",
    "气温",
    "温度",
}
_WEATHER_CONTEXT_PATTERN = re.compile(
    r"天气|天气预报|气温|温度|下雨|下雪|降雨|降雪|晴天|阴天|多云|风力|湿度|空气质量"
)


def is_tool_allowed_for_query(tool_name: str, query: str | None) -> bool:
    if str(tool_name or "").strip() != "get_weather":
        return True
    text = re.sub(r"[，。！？、；：,.!?;:\s]+", "", str(query or "")).strip()
    if text in _DIRECT_WEATHER_REQUESTS:
        return True
    return any(pattern.search(text) for pattern in _WEATHER_REQUEST_PATTERNS)


def filter_tools_for_query(
    tools: Iterable[Dict[str, Any]], query: str | None
) -> List[Dict[str, Any]]:
    return [
        tool
        for tool in tools or []
        if is_tool_allowed_for_query(
            str((tool.get("function") or {}).get("name") or ""),
            query,
        )
    ]


def filter_tool_calls_for_query(
    calls: Iterable[Dict[str, Any]], query: str | None
) -> List[Dict[str, Any]]:
    return [
        call
        for call in calls or []
        if is_tool_allowed_for_query(str(call.get("name") or ""), query)
    ]


def filter_weather_context_for_query(
    context: str | None, query: str | None
) -> str | None:
    if not context or is_tool_allowed_for_query("get_weather", query):
        return context
    return "".join(
        line
        for line in str(context).splitlines(keepends=True)
        if not _WEATHER_CONTEXT_PATTERN.search(line)
    )
