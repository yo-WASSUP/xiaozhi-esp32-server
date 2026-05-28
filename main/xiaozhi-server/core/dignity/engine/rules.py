from __future__ import annotations

from typing import Any, Dict

from core.dignity.engine.config import (
    ROBOT_ACTION_TO_EYE_EXPRESSION,
    STAGE_ORDER,
    STAGE_QUESTIONS,
    STAGES,
    STRATEGY_TO_ROBOT_ACTION,
)
from core.dignity.engine.state_updates import normalize_emotion_state
from core.dignity.engine.types import DignityDecision, DignityState, StageId


PAUSE_STRATEGIES = {"pause", "switch_topic"}
SAFETY_STRATEGIES = {"handoff_nurse"}


def normalize_decision(raw_decision: Dict[str, Any]) -> DignityDecision:
    stage = (
        raw_decision.get("stage")
        or raw_decision.get("detected_stage")
        or raw_decision.get("current_stage")
        or "life_review"
    )
    if stage not in STAGE_ORDER:
        stage = "life_review"

    strategy = raw_decision.get("strategy", "continue_deeper")
    if strategy not in STRATEGY_TO_ROBOT_ACTION:
        strategy = "continue_deeper"

    should_advance_stage = raw_decision.get("should_advance_stage", False)
    if not isinstance(should_advance_stage, bool):
        should_advance_stage = str(should_advance_stage).lower() in {"true", "yes", "1", "是"}

    return {
        "stage": stage,
        "strategy": strategy,
        "should_advance_stage": should_advance_stage,
        "reply": str(raw_decision.get("reply", "")).strip(),
        "emotion_state": normalize_emotion_state(raw_decision.get("emotion_state")),
    }


def choose_active_stage(state: DignityState, decision: DignityDecision) -> StageId:
    current_index = int(state.get("stage_index", 0))
    if should_hold_stage(decision["strategy"]):
        return STAGE_ORDER[current_index]
    if not decision.get("should_advance_stage", False):
        return STAGE_ORDER[current_index]
    return STAGE_ORDER[min(current_index + 1, len(STAGE_ORDER) - 1)]


def should_auto_advance_stage(state: DignityState, decision: DignityDecision) -> bool:
    if should_hold_stage(decision["strategy"]):
        return False

    current_stage = state.get("current_stage", "rapport")
    detected_stage = decision.get("stage", current_stage)
    if _stage_index(detected_stage) > _stage_index(current_stage):
        return True

    if current_stage == "rapport" and state.get("turn_count", 0) >= 1:
        return True
    return False


def pick_stage_reply(state: DignityState) -> str:
    stage_id = state.get("current_stage", "rapport")
    questions = STAGE_QUESTIONS.get(stage_id, [STAGES[STAGE_ORDER.index(stage_id)].default_question])
    index = min(int(state.get("followup_count", 0)), len(questions) - 1)
    return questions[index]


def strategy_to_robot_action(strategy: str) -> str:
    return STRATEGY_TO_ROBOT_ACTION.get(strategy, "listening")


def strategy_to_eye_expression(strategy: str) -> str:
    robot_action = strategy_to_robot_action(strategy)
    return ROBOT_ACTION_TO_EYE_EXPRESSION.get(robot_action, "attentive")


def should_hold_stage(strategy: str) -> bool:
    return strategy in PAUSE_STRATEGIES or strategy in SAFETY_STRATEGIES


def _stage_index(stage: StageId | str) -> int:
    try:
        return STAGE_ORDER.index(stage)  # type: ignore[arg-type]
    except ValueError:
        return 0
