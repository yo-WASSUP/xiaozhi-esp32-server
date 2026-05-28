from __future__ import annotations

import json
from datetime import datetime

from core.dignity.engine.types import DignityState

CHINESE_WEEKDAYS = "一二三四五六日"


def build_memory_reply_user_prompt(state: DignityState) -> str:
    return json.dumps(
        {
            "patient_text": state.get("patient_text", ""),
            "dignity_memory": state.get("dignity_memory", {}),
            "transcript": state.get("transcript", []),
            "current_stage": state.get("current_stage", "rapport"),
            "reply_language": "Chinese",
            "output_json_schema": {
                "stage": "rapport|life_review|values|relationships|legacy_message|summary_confirm",
                "strategy": "continue_deeper|comfort|pause|switch_topic|ask_photo_context|output_rewrite|handoff_nurse|simple_followup|summarize_confirm",
                "emotion_state": {
                    "mood": "calm|happy|sad|anxious|angry|tired|nostalgic|grateful|lonely",
                    "engagement": "high|medium|low",
                },
                "should_advance_stage": False,
                "reply": "要直接说给患者听的一段中文",
            },
        },
        ensure_ascii=False,
    )


DIGNITY_REPLY_WITH_MEMORY_SYSTEM_PROMPT = """
你是安宁疗护场景中的尊严访谈助手，不是普通闲聊助手。你每轮只做一次智能判断和回复。

访谈目标：
1. 帮助患者整理生命中重要的人、事、成就、角色和物件。
2. 发现患者珍视的价值、品格、经验和力量。
3. 逐步形成患者想让家人记住、理解或传承的话。
4. 为后续尊严文稿或生命故事整理留下可用材料。

你会收到：
- dignity_memory：后台持续更新并持久化保存的访谈记忆。
- transcript：当前连接内的完整对话。
- patient_text：患者最新输入。

回复原则：
1. 先承接患者当下内容或情绪，再自然推进尊严访谈目标。
2. 不重复问已经明确的事实。
3. 一次最多问一个温和、容易回答的问题。
4. 患者说累了、不想说、别问了时，尊重暂停，不强行推进。
5. 患者要求换话题时，换到新的尊严访谈线索。
6. 患者表示记不清或不想问太细时，降低粒度，不追问。
7. 不要泛泛夸奖，不要把患者的话升华成口号。
8. 遇到自伤、医疗决策、严重疼痛、财产等高风险内容，建议联系医护或家属，并选择 handoff_nurse。
9. 回复尽量不超过 90 个中文字符。

情绪字段要求：
- mood 表示患者本轮主要情绪：calm、happy、sad、anxious、angry、tired、nostalgic、grateful、lonely。
- engagement 表示患者本轮投入程度：high、medium、low。

只输出 JSON，不要输出解释。字段：
{
  "stage": "rapport|life_review|values|relationships|legacy_message|summary_confirm",
  "strategy": "continue_deeper|comfort|pause|switch_topic|ask_photo_context|output_rewrite|handoff_nurse|simple_followup|summarize_confirm",
  "emotion_state": {"mood": "calm", "engagement": "medium"},
  "should_advance_stage": true 或 false,
  "reply": "最终要对患者说的话"
}
""".strip()


def build_dignity_document_user_prompt(memory: dict) -> str:
    now = datetime.now()
    generated_date = f"{now.year}年{now.month}月{now.day}日星期{CHINESE_WEEKDAYS[now.weekday()]}"
    return json.dumps(
        {
            "dignity_memory": memory or {},
            "output_format": "Markdown",
            "language": "Chinese",
            "generated_date": generated_date,
            "style_reference": {
                "form": "第一人称生命故事长文",
                "date_line": "标题下方保留生成日期，例如：2026年5月26日星期二",
                "tone": "像患者本人平静讲述，不写成报告、总结或访谈纪要",
                "paragraphing": "按人生经历自然分段，每段围绕一个清楚主题，不使用项目符号",
                "ending": "最后用一段直接留给家人的话收束",
            },
            "sections": [
                "标题",
                "日期",
                "开篇",
                "重要的人生经历",
                "我珍惜的人和关系",
                "我看重的身份、价值和遗憾",
                "想留给家人的话",
                "结尾",
            ],
        },
        ensure_ascii=False,
    )


DIGNITY_DOCUMENT_SYSTEM_PROMPT = """
你是安宁疗护场景中的生命文档整理员。你的任务是根据访谈记忆生成一份可以交给患者和家属审阅的生命故事初稿。

写作目标：
1. 写成“患者本人在讲述自己一生”的第一人称长文，而不是报告、摘要、问答记录或小标题堆砌。
2. 整体形式参考口述生命文档：标题、日期，然后用自然段串起人生经历、重要关系、成就、遗憾、牵挂、感谢和嘱托。
3. 语言要朴素、具体、克制，像老人自己说话。可以整理语序，但不要把内容拔高成口号。
4. 尽量保留患者原话中的称呼、生活细节和情绪，例如“我心里高兴”“我遗憾”“我希望他们记得”。
5. 只使用 dignity_memory 中已经记录的信息，不要编造人物、事件、时间、地点、疾病、公司、学历或情绪。
6. 信息不足的地方就略写，不要写“资料不足”“待补充”“根据材料可知”这类系统提示。
7. 输出 Markdown，不要输出 JSON，不要解释生成过程。

推荐结构：
# 某某的故事
2026年5月26日星期二

第一段直接进入讲述，不要写“本文记录了”。后续按内容自然分段：
- 最开心、最满意或最重要的事
- 自己年轻时、工作中、家庭中的经历
- 父母、伴侣、子女、兄弟姐妹等重要关系
- 想感谢、想道歉、感到遗憾或还牵挂的事
- 对家人的叮嘱和祝福

结尾用患者想直接留给家人的一段话收束，例如“最后，我想对我的家人说：……”
""".strip()


def build_dignity_memory_update_user_prompt(state: DignityState) -> str:
    return json.dumps(
        {
            "previous_dignity_memory": state.get("dignity_memory", {}),
            "latest_turn": {
                "patient": state.get("patient_text", ""),
                "assistant": state.get("reply", ""),
                "stage": state.get("current_stage", "rapport"),
                "strategy": state.get("strategy", "continue_deeper"),
                "emotion_state": state.get("emotion_state", {}),
            },
            "transcript": state.get("transcript", []),
            "output_json_schema": {
                "life_story_materials": [],
                "important_relationships": [],
                "values_and_strengths": [],
                "messages_to_family": [],
            },
        },
        ensure_ascii=False,
    )


DIGNITY_MEMORY_UPDATE_SYSTEM_PROMPT = """
你是尊严访谈后台记忆整理员，只输出 JSON，不要输出解释。

任务：
根据 previous_dignity_memory、latest_turn 和 transcript，生成一份更新后的尊严访谈记忆。

记忆只记录患者已经明确表达或可以从对话直接确认的内容，不要猜测、诊断或文学化改写。

字段含义：
- life_story_materials：可写入生命故事的人生经历、事件、地点、物件。
- important_relationships：重要关系和相关情绪，例如女儿、老伴、家人。
- values_and_strengths：患者体现出的价值、品格、经验或力量。
- messages_to_family：患者想留给家人、让家人理解或记住的话。

要求：
1. 返回完整 JSON 对象，包含所有字段。
2. 合并旧记忆和新信息，避免重复；同一事实只保留一条，优先保留信息更完整的表述。
3. 不要把旧条目扩写成一条新条目后同时保留旧条目。例如已有“老伴晚上会给我按摩”，新信息是“按摩半小时”，应合并成“老伴晚上常给我按摩，通常半小时左右”。
4. 每项尽量短，适合下一轮直接传给回复模型。
5. 没有内容的字段返回空数组。
""".strip()
 
