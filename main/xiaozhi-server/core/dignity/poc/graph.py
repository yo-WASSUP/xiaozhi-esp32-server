from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Literal, Optional, Protocol, TypedDict

from langgraph.graph import END, StateGraph
from openai import OpenAI


StageId = Literal[
    "rapport",
    "life_review",
    "values",
    "relationships",
    "legacy_summary",
]

Route = Literal["continue", "pause", "safety"]
RiskLevel = Literal["low", "medium", "high"]

STRATEGY_TO_ROUTE: Dict[str, Route] = {
    "continue_deeper": "continue",
    "comfort": "continue",
    "ask_photo_context": "continue",
    "simple_followup": "continue",
    "summarize_confirm": "continue",
    "output_rewrite": "continue",
    "switch_topic": "pause",
    "pause": "pause",
    "handoff_nurse": "safety",
}

STRATEGY_TO_NEXT_ACTION: Dict[str, str] = {
    "continue_deeper": "ask_followup",
    "comfort": "provide_comfort",
    "ask_photo_context": "record_photo_clue",
    "simple_followup": "ask_simple_followup",
    "summarize_confirm": "summarize_and_confirm",
    "output_rewrite": "boundary_safe_rewrite",
    "switch_topic": "offer_topic_switch",
    "pause": "offer_pause",
    "handoff_nurse": "safety_support",
}

STAGE_ORDER: List[StageId] = [
    "rapport",
    "life_review",
    "values",
    "relationships",
    "legacy_summary",
]


class DignityDecision(TypedDict, total=False):
    stage: StageId
    strategy: str
    risk_level: RiskLevel
    robot_action: str
    reply_direction: str
    memory_fields: List[str]


class DignityState(TypedDict, total=False):
    session_id: str
    patient_text: str
    current_stage: StageId
    stage_index: int
    completed_themes: List[StageId]
    turn_count: int
    route: Route
    risk_level: RiskLevel
    strategy: str
    next_action: str
    reply: str
    eye_expression: str
    stage_goal: str
    robot_action: str
    reply_direction: str
    memory_fields: List[str]
    transcript: List[Dict[str, str]]
    decision_model: "DecisionModel"


class DecisionModel(Protocol):
    def decide(self, state: DignityState) -> DignityDecision:
        pass


@dataclass(frozen=True)
class StageDefinition:
    stage_id: StageId
    name: str
    goal: str
    default_question: str


STAGES: List[StageDefinition] = [
    StageDefinition(
        stage_id="rapport",
        name="建立关系",
        goal="降低访谈压力，确认患者愿意继续交流。",
        default_question="我们可以慢慢来。现在您最想先聊哪一段生活经历？",
    ),
    StageDefinition(
        stage_id="life_review",
        name="人生回顾",
        goal="引导患者回顾重要经历、转折和记忆线索。",
        default_question="那段经历里，有没有一个画面或一个人让您现在还记得很清楚？",
    ),
    StageDefinition(
        stage_id="values",
        name="价值提炼",
        goal="帮助患者表达坚持过的价值、品质和人生经验。",
        default_question="如果把这份经验留给家人，您最想让他们记住哪一句话？",
    ),
    StageDefinition(
        stage_id="relationships",
        name="重要关系",
        goal="梳理重要关系、感谢、牵挂、和解或未尽之言。",
        default_question="如果他/她现在就在您身边，您最想对他说什么？",
    ),
    StageDefinition(
        stage_id="legacy_summary",
        name="尊严文本雏形",
        goal="把前面的内容收束成可复盘、可编辑的尊严文本线索。",
        default_question="这些内容里，哪一条最应该被放在最前面？",
    ),
]


class OpenAIJsonDecisionModel:
    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: Optional[str] = None,
        timeout: float = 30,
    ):
        self.model = model
        self.client = OpenAI(api_key=api_key, base_url=base_url, timeout=timeout)

    @classmethod
    def from_env(cls) -> "OpenAIJsonDecisionModel":
        api_key = os.getenv("DIGNITY_POC_OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError(
                "缺少 LLM API Key。请设置 DIGNITY_POC_OPENAI_API_KEY 或 OPENAI_API_KEY。"
            )
        return cls(
            api_key=api_key,
            model=os.getenv("DIGNITY_POC_MODEL", "gpt-4.1-mini"),
            base_url=os.getenv("DIGNITY_POC_OPENAI_BASE_URL") or os.getenv("OPENAI_BASE_URL"),
            timeout=float(os.getenv("DIGNITY_POC_TIMEOUT", "30")),
        )

    def decide(self, state: DignityState) -> DignityDecision:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": DECISION_SYSTEM_PROMPT},
                {"role": "user", "content": build_decision_user_prompt(state)},
            ],
            response_format={"type": "json_object"},
            temperature=0,
        )
        content = response.choices[0].message.content or "{}"
        decision = json.loads(content)
        return normalize_decision(decision)


def build_initial_state(
    session_id: str = "dignity-text-poc",
    decision_model: Optional[DecisionModel] = None,
) -> DignityState:
    return {
        "session_id": session_id,
        "patient_text": "",
        "current_stage": "rapport",
        "stage_index": 0,
        "completed_themes": [],
        "turn_count": 0,
        "route": "continue",
        "risk_level": "low",
        "strategy": "continue_deeper",
        "next_action": "ask_opening_question",
        "reply": STAGES[0].default_question,
        "eye_expression": "soft_smile",
        "stage_goal": STAGES[0].goal,
        "robot_action": "listening",
        "reply_direction": "",
        "memory_fields": [],
        "transcript": [],
        "decision_model": decision_model or OpenAIJsonDecisionModel.from_env(),
    }


def run_text_turn(state: Optional[DignityState], patient_text: str) -> DignityState:
    graph = build_graph()
    initial_state = copy_state(state) if state else build_initial_state()
    initial_state["patient_text"] = patient_text.strip()
    return graph.invoke(initial_state)


def build_graph() -> Any:
    graph_builder = StateGraph(DignityState)
    graph_builder.add_node("llm_decide", llm_decide)
    graph_builder.add_node("apply_decision", apply_decision)
    graph_builder.add_node("generate_reply", generate_reply)
    graph_builder.add_node("record_turn", record_turn)

    graph_builder.set_entry_point("llm_decide")
    graph_builder.add_edge("llm_decide", "apply_decision")
    graph_builder.add_edge("apply_decision", "generate_reply")
    graph_builder.add_edge("generate_reply", "record_turn")
    graph_builder.add_edge("record_turn", END)
    return graph_builder.compile()


def llm_decide(state: DignityState) -> DignityState:
    next_state = copy_state(state)
    next_state["turn_count"] = int(next_state.get("turn_count", 0)) + 1
    decision = next_state["decision_model"].decide(next_state)
    normalized = normalize_decision(decision)
    next_state["current_stage"] = normalized["stage"]
    next_state["strategy"] = normalized["strategy"]
    next_state["risk_level"] = normalized["risk_level"]
    next_state["robot_action"] = normalized["robot_action"]
    next_state["reply_direction"] = normalized["reply_direction"]
    next_state["memory_fields"] = normalized["memory_fields"]
    return next_state


def apply_decision(state: DignityState) -> DignityState:
    next_state = copy_state(state)
    decision = normalize_decision(next_state)
    strategy = decision["strategy"]
    stage_id = decision["stage"]
    stage_index = STAGE_ORDER.index(stage_id)

    completed = list(next_state.get("completed_themes", []))
    previous_stage_index = int(next_state.get("stage_index", 0))
    for completed_stage in STAGE_ORDER[previous_stage_index:stage_index]:
        if completed_stage not in completed:
            completed.append(completed_stage)

    route = STRATEGY_TO_ROUTE.get(strategy, "continue")
    next_state["current_stage"] = stage_id
    next_state["stage_index"] = stage_index
    next_state["completed_themes"] = completed
    next_state["route"] = route
    next_state["risk_level"] = decision["risk_level"]
    next_state["strategy"] = strategy
    next_state["next_action"] = STRATEGY_TO_NEXT_ACTION.get(strategy, "ask_followup")
    next_state["robot_action"] = decision["robot_action"]
    next_state["eye_expression"] = robot_action_to_eye_expression(decision["robot_action"])
    next_state["reply_direction"] = decision.get("reply_direction", "")
    next_state["memory_fields"] = decision.get("memory_fields", [])
    next_state["stage_goal"] = STAGES[stage_index].goal
    return next_state


def generate_reply(state: DignityState) -> DignityState:
    next_state = copy_state(state)
    strategy = next_state.get("strategy", "continue_deeper")
    stage = STAGES[int(next_state.get("stage_index", 0))]

    strategy_templates = {
        "handoff_nurse": "我听到这部分已经超过普通访谈范围。我们先暂停，我建议请现场医护或家属一起陪您确认接下来怎么做。",
        "pause": "可以，我们先停在这里。我会记住刚才聊到的位置，等您觉得可以了再继续。",
        "switch_topic": "好的，我们先不继续这个话题。您可以休息一下，也可以换一个更轻一点的话题。",
        "comfort": "我听到这里面有很重的心情。我们不用急着判断对错，可以先慢慢整理您最想表达的部分。",
        "ask_photo_context": "这个线索很重要。我先把它记录下来，后续可以请家属补充照片、物件或人物说明，不需要您现在去找。",
        "output_rewrite": "这个问题需要专业人员一起确认，我不能替您做诊断或重大决定。但我可以帮您整理想表达的担心和问题。",
        "simple_followup": "没关系，我们可以把问题放轻一点。您愿意先从一个容易想起的小片段说起吗？",
        "summarize_confirm": "没关系，我帮您轻轻回顾一下刚才的位置；如果不准确，您可以随时纠正我。",
        "continue_deeper": stage.default_question,
    }

    next_state["reply"] = strategy_templates.get(strategy, stage.default_question)
    return next_state


def record_turn(state: DignityState) -> DignityState:
    next_state = copy_state(state)
    transcript = list(next_state.get("transcript", []))
    transcript.append(
        {
            "patient": next_state.get("patient_text", ""),
            "assistant": next_state.get("reply", ""),
            "stage": next_state.get("current_stage", "rapport"),
            "strategy": next_state.get("strategy", ""),
            "route": next_state.get("route", "continue"),
        }
    )
    next_state["transcript"] = transcript
    return next_state


def copy_state(state: DignityState) -> DignityState:
    next_state = dict(state)
    next_state["completed_themes"] = list(state.get("completed_themes", []))
    next_state["transcript"] = list(state.get("transcript", []))
    next_state["memory_fields"] = list(state.get("memory_fields", []))
    return next_state


def normalize_decision(raw_decision: Dict[str, Any]) -> DignityDecision:
    stage = raw_decision.get("stage") or raw_decision.get("current_stage") or "life_review"
    if stage not in STAGE_ORDER:
        stage = "life_review"

    strategy = raw_decision.get("strategy", "continue_deeper")
    if strategy not in STRATEGY_TO_ROUTE:
        strategy = "continue_deeper"

    risk_level = raw_decision.get("risk_level", "low")
    if risk_level not in {"low", "medium", "high"}:
        risk_level = "low"

    robot_action = raw_decision.get("robot_action", "listening")
    if robot_action not in {"listening", "comfort", "pause", "nurse_alert", "happy"}:
        robot_action = "listening"

    memory_fields = raw_decision.get("memory_fields", [])
    if not isinstance(memory_fields, list):
        memory_fields = []

    return {
        "stage": stage,
        "strategy": strategy,
        "risk_level": risk_level,
        "robot_action": robot_action,
        "reply_direction": str(raw_decision.get("reply_direction", "")),
        "memory_fields": [str(item) for item in memory_fields],
    }


def robot_action_to_eye_expression(robot_action: str) -> str:
    return {
        "listening": "attentive",
        "comfort": "gentle",
        "pause": "calm",
        "nurse_alert": "concern",
        "happy": "warm_smile",
    }.get(robot_action, "attentive")


def build_decision_user_prompt(state: DignityState) -> str:
    recent_transcript = state.get("transcript", [])[-4:]
    return json.dumps(
        {
            "patient_text": state.get("patient_text", ""),
            "current_stage": state.get("current_stage", "rapport"),
            "completed_themes": state.get("completed_themes", []),
            "recent_transcript": recent_transcript,
            "allowed_stage": STAGE_ORDER,
            "allowed_strategy": list(STRATEGY_TO_ROUTE.keys()),
            "allowed_risk_level": ["low", "medium", "high"],
            "allowed_robot_action": ["listening", "comfort", "pause", "nurse_alert", "happy"],
        },
        ensure_ascii=False,
    )


DECISION_SYSTEM_PROMPT = """
你是安宁疗护尊严疗法机器人的对话决策器，只输出 JSON，不输出解释。

目标：
1. 判断患者输入属于哪个尊严疗法阶段。
2. 判断下一步策略、风险等级、机器人动作和回复方向。
3. 遇到自伤、医疗决策、诊断、重大财产决策等边界，必须选择安全策略。
4. 遇到疲惫、拒绝、暂停，必须尊重边界。
5. 遇到照片、奖状、相册、家属补充等线索，应记录为线索，不要求患者立即寻找。

输出 JSON 字段：
{
  "stage": "rapport|life_review|values|relationships|legacy_summary",
  "strategy": "continue_deeper|comfort|pause|switch_topic|ask_photo_context|output_rewrite|handoff_nurse|simple_followup|summarize_confirm",
  "risk_level": "low|medium|high",
  "robot_action": "listening|comfort|pause|nurse_alert|happy",
  "reply_direction": "一句中文，说明接下来回复的方向",
  "memory_fields": ["可选，提取值得记录的字段名"]
}
""".strip()
