from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Literal, Protocol, TypedDict


StageId = Literal[
    "rapport",
    "life_review",
    "values",
    "relationships",
    "legacy_message",
    "summary_confirm",
]

Route = Literal["continue", "pause", "safety"]


class DignityDecision(TypedDict, total=False):
    stage: StageId
    strategy: str
    should_advance_stage: bool
    reply: str
    emotion_state: Dict[str, Any]


class DignityState(TypedDict, total=False):
    session_id: str
    patient_text: str
    current_stage: StageId
    detected_stage: StageId
    stage_index: int
    completed_themes: List[StageId]
    turn_count: int
    stage_turn_count: int
    followup_count: int
    route: Route
    strategy: str
    next_action: str
    reply: str
    should_advance_stage: bool
    eye_expression: str
    stage_goal: str
    robot_action: str
    emotion_state: Dict[str, Any]
    dignity_memory: Dict[str, List[Any]]
    asked_questions: List[str]
    transcript: List[Dict[str, str]]
    decision_model: "DecisionModel"


class DecisionModel(Protocol):
    def decide_and_reply(self, state: DignityState) -> DignityDecision:
        pass

    def update_dignity_memory(self, state: DignityState) -> Dict[str, Any]:
        pass


@dataclass(frozen=True)
class StageDefinition:
    stage_id: StageId
    name: str
    goal: str
    default_question: str
