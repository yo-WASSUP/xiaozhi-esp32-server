"""
情感解析模块 - 从 LLM 输出中提取隐藏的情感标签
"""
import re
import json
from config.logger import setup_logging

TAG = __name__
logger = setup_logging()


def parse_emotion(text: str) -> tuple:
    """
    从 LLM 回复中解析 <!--emotion:{"mood":"xxx","intensity":0.x}--> 标签
    
    Returns:
        (clean_text, emotion_data)
        - clean_text: 去掉情感标签后的纯文本
        - emotion_data: dict {"mood": str, "intensity": float} 或 None
    """
    pattern = r'<!--emotion:(.*?)-->'
    match = re.search(pattern, text)
    
    if match:
        try:
            emotion_data = json.loads(match.group(1))
            clean_text = re.sub(pattern, '', text).strip()
            logger.bind(tag=TAG).debug(
                f"情感解析: mood={emotion_data.get('mood')}, "
                f"intensity={emotion_data.get('intensity')}"
            )
            return clean_text, emotion_data
        except json.JSONDecodeError:
            logger.bind(tag=TAG).warning(f"情感标签 JSON 解析失败: {match.group(1)}")
            clean_text = re.sub(pattern, '', text).strip()
            return clean_text, None
    
    return text, None
