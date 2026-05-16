from ..base import MemoryProviderBase, logger
import time
import json
import os
import yaml
from config.config_loader import get_project_dir
from config.manage_api_client import generate_and_save_chat_summary
import asyncio
from core.utils.util import check_model_key


short_term_memory_prompt = """
你是一个保守的对话记忆整理器。你的任务是把用户明确说过、以后对陪伴有帮助的信息整理成简洁记忆。

严格规则：
1. 只记录用户明确说过的事实，不要猜测、推断、补全。
2. 不要创造姓名、姓氏、昵称或尊称。比如没有明确说“叫我唐大爷”，就不能写“唐大爷”。
3. 如果出现矛盾，以用户最新纠正为准，并把被纠正的信息放入“已纠正信息”。
4. 助手说过的话不能当作用户事实。
5. 不记录无关寒暄、测试语句、模型自我介绍。
6. 输出必须是合法 JSON，不要 Markdown，不要解释。

输出结构固定为：
{
  "患者画像": {
    "姓名或称呼": "",
    "年龄": "",
    "居住地": "",
    "健康相关": [],
    "性格与沟通偏好": []
  },
  "家庭关系": [],
  "饮食与生活偏好": [],
  "重要回忆": [],
  "已纠正信息": [],
  "陪伴建议": [],
  "禁止假设": [
    "未知姓名时只称呼“您”",
    "不要编造患者姓名、姓氏、昵称或家属关系"
  ],
  "最近更新时间": "YYYY-MM-DD"
}

字段填写规则：
- 不知道就填空字符串或空数组。
- “姓名或称呼”只有在用户明确说“我叫X”“你叫我X”“我是X”时才填写。
- “陪伴建议”只能基于明确事实生成，比如“可以聊苹果”，不要写没有依据的关怀任务。
"""


def extract_json_data(json_code):
    start = json_code.find("```json")
    # 从start开始找到下一个```结束
    end = json_code.find("```", start + 1)
    # print("start:", start, "end:", end)
    if start == -1 or end == -1:
        try:
            jsonData = json.loads(json_code)
            return json_code
        except Exception as e:
            print("Error:", e)
        return ""
    jsonData = json_code[start + 7 : end]
    return jsonData.strip()


def _memory_to_text(memory):
    if not memory:
        return ""
    if isinstance(memory, (dict, list)):
        return json.dumps(memory, ensure_ascii=False, indent=2)
    return str(memory)


def _parse_memory_json(memory_text):
    try:
        return json.loads(memory_text)
    except Exception:
        return None


TAG = __name__


class MemoryProvider(MemoryProviderBase):
    def __init__(self, config, summary_memory):
        super().__init__(config)
        self.short_memory = ""
        self.save_to_file = True
        self.memory_path = get_project_dir() + "data/.memory.yaml"
        self.load_memory(summary_memory)

    def init_memory(
        self, role_id, llm, summary_memory=None, save_to_file=True, **kwargs
    ):
        super().init_memory(role_id, llm, **kwargs)
        self.save_to_file = save_to_file
        self.load_memory(summary_memory)

    def load_memory(self, summary_memory):
        # api获取到总结记忆后直接返回
        if summary_memory or not self.save_to_file:
            self.short_memory = _memory_to_text(summary_memory)
            return

        all_memory = {}
        if os.path.exists(self.memory_path):
            with open(self.memory_path, "r", encoding="utf-8") as f:
                all_memory = yaml.safe_load(f) or {}
        if self.role_id in all_memory:
            self.short_memory = _memory_to_text(all_memory[self.role_id])

    def save_memory_to_file(self):
        all_memory = {}
        if os.path.exists(self.memory_path):
            with open(self.memory_path, "r", encoding="utf-8") as f:
                all_memory = yaml.safe_load(f) or {}
        all_memory[self.role_id] = (
            _parse_memory_json(self.short_memory) or self.short_memory
        )
        with open(self.memory_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(
                all_memory,
                f,
                allow_unicode=True,
                sort_keys=False,
                default_flow_style=False,
            )

    async def save_memory(self, msgs, session_id=None):
        # 打印使用的模型信息
        model_info = getattr(self.llm, "model_name", str(self.llm.__class__.__name__))
        logger.bind(tag=TAG).debug(f"使用记忆保存模型: {model_info}")
        api_key = getattr(self.llm, "api_key", None)
        memory_key_msg = check_model_key("记忆总结专用LLM", api_key)
        if memory_key_msg:
            logger.bind(tag=TAG).error(memory_key_msg)
        if self.llm is None:
            logger.bind(tag=TAG).error("LLM is not set for memory provider")
            return None

        if len(msgs) < 2:
            return None

        msgStr = ""
        for msg in msgs:
            if msg.role == "user":
                msgStr += f"User: {msg.content}\n"
            elif msg.role == "assistant":
                msgStr += f"Assistant: {msg.content}\n"
        if self.short_memory and len(self.short_memory) > 0:
            msgStr += "历史记忆：\n"
            msgStr += self.short_memory

        # 当前时间
        time_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        msgStr += f"当前时间：{time_str}"

        if self.save_to_file:
            try:
                result = self.llm.response_no_stream(
                    short_term_memory_prompt,
                    msgStr,
                    max_tokens=2000,
                    temperature=0.2,
                )
                json_str = extract_json_data(result)
                memory_data = json.loads(json_str)  # 检查json格式是否正确
                self.short_memory = json.dumps(
                    memory_data,
                    ensure_ascii=False,
                    indent=2,
                )
                self.save_memory_to_file()
            except Exception as e:
                logger.bind(tag=TAG).error(f"Error in saving memory: {e}")
        else:
            # 当save_to_file为False时，调用Java端的聊天记录总结接口
            summary_id = session_id if session_id else self.role_id
            await generate_and_save_chat_summary(summary_id)
        logger.bind(tag=TAG).info(
            f"Save memory successful - Role: {self.role_id}, Session: {session_id}"
        )

        return self.short_memory

    async def query_memory(self, query: str) -> str:
        return self.short_memory
