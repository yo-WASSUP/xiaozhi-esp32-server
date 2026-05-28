from __future__ import annotations

from copy import deepcopy
from functools import lru_cache
from typing import Any, Optional

from langgraph.graph import END, StateGraph

from core.dignity.engine.config import (
    STAGE_ORDER,
    STAGE_QUESTIONS,
    STAGES,
)
from core.dignity.engine.model import OpenAIJsonDecisionModel
from core.dignity.engine.replies import sanitize_reply
from core.dignity.engine.rules import (
    choose_active_stage,
    normalize_decision,
    pick_stage_reply,
    should_auto_advance_stage,
)
from core.dignity.engine.state_updates import initial_dignity_memory, initial_emotion_state
from core.dignity.engine.types import (
    DecisionModel,
    DignityDecision,
    DignityState,
    StageDefinition,
    StageId,
)


def build_initial_state(
    session_id: str = "dignity-text-engine",
    decision_model: Optional[DecisionModel] = None,
) -> DignityState:
    return {
        "session_id": session_id,
        "patient_text": "",
        "current_stage": "rapport",
        "stage_index": 0,
        "turn_count": 0,
        "followup_count": 0,
        "strategy": "continue_deeper",
        "reply": STAGE_QUESTIONS["rapport"][0],
        "emotion_state": initial_emotion_state(),
        "dignity_memory": initial_dignity_memory(),
        "transcript": [],
        "decision_model": decision_model or OpenAIJsonDecisionModel.from_config_file(),
    }


def run_text_turn(state: Optional[DignityState], patient_text: str) -> DignityState:
    graph = build_graph()
    initial_state = copy_state(state) if state else build_initial_state()
    initial_state["patient_text"] = patient_text.strip()
    return graph.invoke(initial_state)


@lru_cache(maxsize=1)
def build_graph() -> Any:
    graph_builder = StateGraph(DignityState)
    graph_builder.add_node("generate_reply_with_memory", generate_reply_with_memory)
    graph_builder.add_node("record_turn", record_turn)

    graph_builder.set_entry_point("generate_reply_with_memory")
    graph_builder.add_edge("generate_reply_with_memory", "record_turn")
    graph_builder.add_edge("record_turn", END)
    return graph_builder.compile()


def generate_reply_with_memory(state: DignityState) -> DignityState:
    next_state = copy_state(state)
    next_state["turn_count"] = int(next_state.get("turn_count", 0)) + 1
    model = next_state.get("decision_model")
    decision: DignityDecision = {
        "stage": next_state.get("current_stage", "rapport"),
        "strategy": "continue_deeper",
        "should_advance_stage": False,
        "reply": "",
    }

    if model and hasattr(model, "decide_and_reply"):
        try:
            decision = model.decide_and_reply(next_state)
        except Exception:
            pass

    normalized = normalize_decision(decision)
    next_state["strategy"] = normalized["strategy"]
    next_state["reply"] = normalized["reply"]
    next_state["emotion_state"] = normalized["emotion_state"]
    next_state = apply_decision_metadata(next_state, normalized)
    next_state["reply"] = sanitize_reply(next_state, next_state.get("reply", ""))
    if not next_state["reply"]:
        next_state["reply"] = pick_stage_reply(next_state) or STAGES[
            int(next_state.get("stage_index", 0))
        ].default_question
    return next_state


def apply_decision_metadata(state: DignityState, decision: DignityDecision) -> DignityState:
    next_state = copy_state(state)
    decision = normalize_decision(decision)
    strategy = decision["strategy"]
    if should_auto_advance_stage(next_state, decision):
        decision["should_advance_stage"] = True
    stage_id = choose_active_stage(next_state, decision)
    stage_index = STAGE_ORDER.index(stage_id)

    stage_changed = stage_index != int(next_state.get("stage_index", 0))
    next_state["current_stage"] = stage_id
    next_state["stage_index"] = stage_index
    next_state["followup_count"] = (
        0 if stage_changed else int(next_state.get("followup_count", 0)) + 1
    )
    next_state["strategy"] = strategy
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
            "emotion_state": next_state.get("emotion_state", {}),
        }
    )
    next_state["transcript"] = transcript
    return next_state


def copy_state(state: DignityState) -> DignityState:
    next_state = dict(state)
    next_state["transcript"] = list(state.get("transcript", []))
    next_state["emotion_state"] = deepcopy(state.get("emotion_state", initial_emotion_state()))
    next_state["dignity_memory"] = deepcopy(state.get("dignity_memory", initial_dignity_memory()))
    return next_state


__all__ = [
    "DecisionModel",
    "DignityDecision",
    "DignityState",
    "OpenAIJsonDecisionModel",
    "STAGE_ORDER",
    "STAGES",
    "StageDefinition",
    "StageId",
    "build_graph",
    "build_initial_state",
    "normalize_decision",
    "run_text_turn",
]
