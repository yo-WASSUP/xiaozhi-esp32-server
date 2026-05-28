from __future__ import annotations

from typing import Dict, List

from core.dignity.engine.types import StageDefinition, StageId

STRATEGY_TO_ROBOT_ACTION: Dict[str, str] = {
    "continue_deeper": "listening",
    "comfort": "comfort",
    "ask_photo_context": "listening",
    "simple_followup": "listening",
    "summarize_confirm": "listening",
    "output_rewrite": "comfort",
    "switch_topic": "pause",
    "pause": "pause",
    "handoff_nurse": "nurse_alert",
}

ROBOT_ACTIONS: List[str] = [
    "idle",
    "listening",
    "comfort",
    "pause",
    "nurse_alert",
    "happy",
]

ROBOT_ACTION_TO_EYE_EXPRESSION: Dict[str, str] = {
    "idle": "calm",
    "listening": "attentive",
    "comfort": "gentle",
    "pause": "calm",
    "nurse_alert": "concern",
    "happy": "warm_smile",
}

STAGE_ORDER: List[StageId] = [
    "rapport",
    "life_review",
    "values",
    "relationships",
    "legacy_message",
    "summary_confirm",
]

STAGES: List[StageDefinition] = [
    StageDefinition(
        stage_id="rapport",
        name="建立关系",
        goal="降低访谈压力，确认患者愿意继续交流。",
        default_question="您好，我是小暖。今天我们不用急着讲很多，我先陪您慢慢聊。您现在感觉还好吗？",
    ),
    StageDefinition(
        stage_id="life_review",
        name="人生回顾",
        goal="引导患者回顾重要经历、转折和记忆线索。",
        default_question="那段经历里，有没有一个画面或一个人让您现在还记得比较清楚？",
    ),
    StageDefinition(
        stage_id="values",
        name="价值提炼",
        goal="帮助患者表达坚持过的价值、品格和人生经验。",
        default_question="如果把这份经历留给家人，您最想让他们记住哪一点？",
    ),
    StageDefinition(
        stage_id="relationships",
        name="重要关系",
        goal="梳理重要关系、感谢、牵挂、和解或未尽之言。",
        default_question="在这些经历里，谁对您来说最重要？",
    ),
    StageDefinition(
        stage_id="legacy_message",
        name="留言祝福",
        goal="形成患者想留给家人、晚辈或重要他人的感谢、祝福、嘱托和原话。",
        default_question="如果给家里人留几句话，您最想先说给谁？",
    ),
    StageDefinition(
        stage_id="summary_confirm",
        name="总结确认",
        goal="复述本轮重点，核对事实、原话、人物关系和下次恢复点。",
        default_question="我刚才听到几个重点，我复述给您听，您看是否准确。",
    ),
]

STAGE_QUESTIONS: Dict[StageId, List[str]] = {
    "rapport": [
        STAGES[0].default_question,
        "在开始前，我想先了解一下，今天聊到什么程度会让您觉得比较舒服？",
    ],
    "life_review": [
        STAGES[1].default_question,
        "回头看，您觉得人生里哪个转折对您影响最大？",
        "那时候您是怎么一步一步走过来的？",
    ],
    "values": [
        "从这段经历里，您觉得自己最珍惜的一种品格是什么？",
        STAGES[2].default_question,
        "困难的时候，是什么支撑着您继续往前走？",
    ],
    "relationships": [
        STAGES[3].default_question,
        "如果这个人现在就在您身边，您最想对他说什么？",
        "有没有哪份感谢、牵挂或祝福，是您希望被好好记下来的？",
    ],
    "legacy_message": [
        STAGES[4].default_question,
        "您对家里人以后有什么祝福或嘱托？",
        "您想对孩子或晚辈说的一句人生经验是什么？",
    ],
    "summary_confirm": [
        STAGES[5].default_question,
        "今天聊到这里可以吗？下次我们可以从哪里接着聊？",
        "今天哪一部分是您最希望被记录下来的？",
    ],
}

BAD_REPLY_PATTERNS = [
    "是不是",
    "像一盏灯",
    "一盏灯",
    "照亮",
    "底色",
    "真让人感动",
    "真让人敬佩",
    "不争不抢",
]
