"""
情感解析模块 - 从 LLM 输出中提取隐藏的情感标签
"""
import re
import json
from config.logger import setup_logging

TAG = __name__
logger = setup_logging()

EMOTION_TAG_PATTERN = re.compile(r'<!--\s*emotion\s*:(.*?)-->', re.DOTALL)
_TAG_DELIMITERS = (("<!--", "-->"), ("{:", "}"))


def filter_stream_emotion_tag(content, pending="", *, final=False):
    """Separate speech from emotion markup, buffering only possible tag prefixes.

    The brace form is malformed model output and is discarded, never parsed as
    emotion data. Confirmed tags without a closing delimiter are dropped at EOF.
    """
    text = pending + content
    output = []
    index = 0
    while index < len(text):
        opener, closer = next(
            (
                (start, end)
                for start, end in _TAG_DELIMITERS
                if text.startswith(start, index)
            ),
            (None, None),
        )
        if opener is None:
            if not final and any(
                start.startswith(text[index:]) for start, _ in _TAG_DELIMITERS
            ):
                return "".join(output), text[index:]
            output.append(text[index])
            index += 1
            continue

        header = text[index + len(opener):].lstrip()
        if not header.startswith("emotion"):
            if not final and "emotion".startswith(header):
                return "".join(output), text[index:]
            output.append(opener)
            index += len(opener)
            continue

        after_name = header[len("emotion"):].lstrip()
        if not after_name and not final:
            return "".join(output), text[index:]
        if not after_name.startswith(":"):
            output.append(opener)
            index += len(opener)
            continue

        tag_end = text.find(closer, index + len(opener))
        if tag_end == -1:
            return "".join(output), "" if final else text[index:]
        index = tag_end + len(closer)

    return "".join(output), ""


def parse_emotion(text: str) -> tuple:
    """
    从 LLM 回复中解析 <!--emotion:{"mood":"xxx","intensity":0.x}--> 标签
    
    Returns:
        (clean_text, emotion_data)
        - clean_text: 去掉情感标签后的纯文本
        - emotion_data: dict {"mood": str, "intensity": float} 或 None
    """
    clean_text, _ = filter_stream_emotion_tag(text, final=True)
    match = EMOTION_TAG_PATTERN.search(text)
    
    if match:
        try:
            emotion_data = json.loads(match.group(1))
            if not isinstance(emotion_data, dict):
                logger.bind(tag=TAG).warning("情感标签 JSON 必须是对象，已从回复中移除")
                return clean_text.strip(), None
            clean_text = clean_text.strip()
            logger.bind(tag=TAG).debug(
                f"情感解析: mood={emotion_data.get('mood')}, "
                f"intensity={emotion_data.get('intensity')}"
            )
            return clean_text, emotion_data
        except json.JSONDecodeError:
            logger.bind(tag=TAG).warning("情感标签 JSON 解析失败，已从回复中移除")
            return clean_text.strip(), None
    
    if clean_text != text:
        logger.bind(tag=TAG).warning("情感标签格式无效或未闭合，已从回复中移除")
        return clean_text.strip(), None
    return text, None
