def get_system_prompt_for_function(functions: str) -> str:
    """
    生成系统提示信息（精简版，适用于语音对话场景）
    :param functions: 可用的函数列表
    :return: 系统提示信息
    """

    SYSTEM_PROMPT = f"""你可以使用以下工具:
{functions}

调用工具时用JSON格式回复:
<tool_call>
{{"name": "工具名", "arguments": {{"参数": "值"}}}}
</tool_call>

如不需要调用工具，直接回复用户。回复要简洁。
"""

    return SYSTEM_PROMPT