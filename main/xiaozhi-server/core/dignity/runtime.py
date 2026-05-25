from __future__ import annotations

import asyncio
import json
import re
import uuid
from datetime import datetime
from pathlib import Path
from time import perf_counter
from typing import Any, Dict, Optional

from core.dignity.engine.acceptance_cases import ACCEPTANCE_CASES
from core.dignity.engine.graph import (
    STRATEGY_TO_ROUTE,
    DignityState,
    build_initial_state,
    normalize_decision,
    run_text_turn,
)
from core.dignity.engine.prompts import (
    DIGNITY_MEMORY_UPDATE_SYSTEM_PROMPT,
    DIGNITY_REPLY_WITH_MEMORY_SYSTEM_PROMPT,
    DIGNITY_DOCUMENT_SYSTEM_PROMPT,
    build_dignity_memory_update_user_prompt,
    build_dignity_document_user_prompt,
    build_memory_reply_user_prompt,
)
from core.dignity.engine.state_updates import merge_dignity_memory
from core.handle.sendAudioHandle import send_stt_message
from core.utils.dialogue import Message
from core.utils.util import extract_json_from_string

TAG = __name__
SERVER_ROOT = Path(__file__).resolve().parents[2]
LOG_DIR = SERVER_ROOT / "data" / "dignity_logs"
MEMORY_DIR = SERVER_ROOT / "data" / "dignity_memory"


class ConnectionLLMDecisionModel:
    """Adapter backed by the active xiaozhi-server LLM provider."""

    def __init__(self, conn):
        self.conn = conn

    def decide_and_reply(self, state: DignityState):
        if not getattr(self.conn, "llm", None):
            raise RuntimeError("Dignity interview requires an initialized LLM")

        content = self.conn.llm.response_no_stream(
            DIGNITY_REPLY_WITH_MEMORY_SYSTEM_PROMPT,
            build_memory_reply_user_prompt(state),
            temperature=0.2,
        )
        decision = _loads_json_object(content)
        self.last_raw_content = content
        self.last_raw_decision = decision
        return normalize_decision(decision)

    def update_dignity_memory(self, state: DignityState):
        if not getattr(self.conn, "llm", None):
            raise RuntimeError("Dignity interview requires an initialized LLM")

        content = self.conn.llm.response_no_stream(
            DIGNITY_MEMORY_UPDATE_SYSTEM_PROMPT,
            build_dignity_memory_update_user_prompt(state),
            temperature=0,
        )
        memory = _loads_json_object(content)
        self.last_raw_memory_content = content
        self.last_raw_memory = memory
        return memory

    def generate_dignity_document(self, memory: Dict[str, Any]):
        if not getattr(self.conn, "llm", None):
            raise RuntimeError("Dignity document generation requires an initialized LLM")

        content = self.conn.llm.response_no_stream(
            DIGNITY_DOCUMENT_SYSTEM_PROMPT,
            build_dignity_document_user_prompt(memory),
            temperature=0.2,
        )
        self.last_raw_document_content = content
        return content or ""


def _loads_json_object(content: str) -> Dict[str, Any]:
    text = (content or "").strip()
    if not text:
        return {}
    try:
        value = json.loads(text)
        return value if isinstance(value, dict) else {}
    except json.JSONDecodeError:
        extracted = extract_json_from_string(text)
        if not extracted:
            raise
        value = json.loads(extracted)
        return value if isinstance(value, dict) else {}


def _ensure_dignity_runtime(conn) -> None:
    if not hasattr(conn, "dignity_active"):
        conn.dignity_active = False
    if not hasattr(conn, "dignity_state"):
        conn.dignity_state = None
    if not hasattr(conn, "dignity_debug_state"):
        conn.dignity_debug_state = None
    if not hasattr(conn, "dignity_patient_id"):
        conn.dignity_patient_id = None
    if not hasattr(conn, "dignity_decision_model"):
        conn.dignity_decision_model = None


def _get_decision_model(conn):
    _ensure_dignity_runtime(conn)
    if conn.dignity_decision_model is None:
        conn.dignity_decision_model = ConnectionLLMDecisionModel(conn)
    return conn.dignity_decision_model


def _state_payload(state: Optional[DignityState]) -> Dict[str, Any]:
    if not state:
        return {
            "current_stage": "rapport",
            "strategy": "continue_deeper",
            "route": "continue",
            "next_action": "ask_opening_question",
            "robot_action": "listening",
            "eye_expression": "soft_smile",
            "reply": "",
            "emotion_state": {"mood": "calm", "engagement": "medium"},
            "dignity_memory": {},
        }

    decision_model = state.get("decision_model")
    return {
        "current_stage": state.get("current_stage", "rapport"),
        "detected_stage": state.get("detected_stage", state.get("current_stage", "rapport")),
        "strategy": state.get("strategy", "continue_deeper"),
        "route": state.get("route", "continue"),
        "next_action": state.get("next_action", "ask_followup"),
        "robot_action": state.get("robot_action", "listening"),
        "eye_expression": state.get("eye_expression", "attentive"),
        "reply": state.get("reply", ""),
        "should_advance_stage": state.get("should_advance_stage", False),
        "stage_turn_count": state.get("stage_turn_count", 0),
        "followup_count": state.get("followup_count", 0),
        "completed_themes": state.get("completed_themes", []),
        "turn_count": state.get("turn_count", 0),
        "stage_goal": state.get("stage_goal", ""),
        "emotion_state": state.get("emotion_state", {"mood": "calm", "engagement": "medium"}),
        "dignity_memory": state.get("dignity_memory", {}),
        "asked_questions": state.get("asked_questions", []),
        "transcript": state.get("transcript", []),
        "raw_decision": getattr(decision_model, "last_raw_decision", None),
        "raw_llm_content": getattr(decision_model, "last_raw_content", ""),
        "raw_memory": getattr(decision_model, "last_raw_memory", None),
        "raw_memory_content": getattr(decision_model, "last_raw_memory_content", ""),
        "response_latency_ms": state.get("response_latency_ms"),
    }


async def send_dignity_event(conn, event: str, data: Optional[Dict[str, Any]] = None) -> None:
    payload = {
        "type": "dignity",
        "event": event,
        "session_id": conn.session_id,
        "data": data or {},
    }
    await conn.websocket.send(json.dumps(payload, ensure_ascii=False))


def _write_dignity_log(
    conn,
    event: str,
    data: Optional[Dict[str, Any]] = None,
    source: str = "runtime",
) -> None:
    data = data or {}
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        now = datetime.now()
        record = {
            "time": now.isoformat(timespec="seconds"),
            "event": event,
            "input": data.get("patient_text", ""),
            "output": data.get("reply", ""),
        }
        log_path = LOG_DIR / f"{now:%Y%m%d}.jsonl"
        with log_path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as exc:
        logger = getattr(conn, "logger", None)
        if logger:
            logger.bind(tag=TAG).debug(f"尊严访谈日志写入失败: {exc}")


def _memory_key(conn) -> str:
    raw = str(getattr(conn, "dignity_patient_id", None) or "default_patient")
    key = re.sub(r"[^A-Za-z0-9_.-]+", "_", raw).strip("._")
    return key or "default_patient"


def _memory_path(conn) -> Path:
    return MEMORY_DIR / f"{_memory_key(conn)}.json"


def _load_persisted_memory(conn) -> Dict[str, Any]:
    path = _memory_path(conn)
    try:
        if not path.exists():
            return {}
        with path.open("r", encoding="utf-8") as file:
            value = json.load(file)
        return value if isinstance(value, dict) else {}
    except Exception as exc:
        logger = getattr(conn, "logger", None)
        if logger:
            logger.bind(tag=TAG).debug(f"尊严访谈记忆读取失败: {exc}")
        return {}


def _save_persisted_memory(conn, memory: Dict[str, Any]) -> None:
    try:
        MEMORY_DIR.mkdir(parents=True, exist_ok=True)
        with _memory_path(conn).open("w", encoding="utf-8") as file:
            json.dump(memory, file, ensure_ascii=False, indent=2)
    except Exception as exc:
        logger = getattr(conn, "logger", None)
        if logger:
            logger.bind(tag=TAG).debug(f"尊严访谈记忆保存失败: {exc}")


def _apply_persisted_memory(conn, state: DignityState) -> DignityState:
    persisted = _load_persisted_memory(conn)
    if persisted:
        state["dignity_memory"] = merge_dignity_memory(state.get("dignity_memory", {}), persisted)
    return state


async def start_dignity_mode(conn, msg_json: Optional[Dict[str, Any]] = None) -> None:
    _ensure_dignity_runtime(conn)
    msg_json = msg_json or {}
    conn.dignity_active = True
    conn.dignity_patient_id = msg_json.get("patient_id") or conn.dignity_patient_id

    if conn.dignity_state is None:
        conn.dignity_state = build_initial_state(
            session_id=conn.session_id,
            decision_model=_get_decision_model(conn),
        )
    conn.dignity_state = _apply_persisted_memory(conn, conn.dignity_state)

    conn.logger.bind(tag=TAG).info("尊严访谈模式已开启")
    payload = _state_payload(conn.dignity_state)
    _write_dignity_log(conn, "mode_started", payload)
    await send_dignity_event(conn, "mode_started", payload)


async def stop_dignity_mode(conn) -> None:
    _ensure_dignity_runtime(conn)
    conn.dignity_active = False
    conn.logger.bind(tag=TAG).info("尊严访谈模式已关闭")
    payload = _state_payload(conn.dignity_state)
    _write_dignity_log(conn, "mode_stopped", payload)
    await send_dignity_event(conn, "mode_stopped", payload)


async def reset_dignity_debug(conn) -> None:
    _ensure_dignity_runtime(conn)
    conn.dignity_debug_state = build_initial_state(
        session_id=f"{conn.session_id}:debug",
        decision_model=_get_decision_model(conn),
    )
    conn.dignity_debug_state = _apply_persisted_memory(conn, conn.dignity_debug_state)
    payload = _state_payload(conn.dignity_debug_state)
    _write_dignity_log(conn, "debug_reset", payload, source="debug")
    await send_dignity_event(conn, "debug_reset", payload)


async def run_dignity_debug_turn(conn, text: str) -> None:
    _ensure_dignity_runtime(conn)
    patient_text = (text or "").strip()
    if not patient_text:
        await send_dignity_event(conn, "error", {"message": "请输入要调试的患者文本。"})
        return

    started_at = perf_counter()
    try:
        loop = asyncio.get_running_loop()
        state = await loop.run_in_executor(
            conn.executor,
            _run_dignity_debug_turn,
            conn,
            patient_text,
        )
    except Exception as exc:
        conn.logger.bind(tag=TAG).error(f"尊严访谈调试处理失败: {exc}")
        await send_dignity_event(conn, "error", {"message": "尊严访谈调试处理失败。"})
        return

    state["response_latency_ms"] = int((perf_counter() - started_at) * 1000)
    conn.dignity_debug_state = state
    payload = _state_payload(state)
    payload["patient_text"] = patient_text
    _write_dignity_log(conn, "debug_turn_result", payload, source="debug")
    await send_dignity_event(conn, "debug_turn_result", payload)
    _schedule_background_state_update(conn, state, "debug")


async def run_dignity_acceptance_cases(conn) -> None:
    _ensure_dignity_runtime(conn)
    await send_dignity_event(conn, "debug_cases_started", {"count": len(ACCEPTANCE_CASES)})

    try:
        loop = asyncio.get_running_loop()
        results = await loop.run_in_executor(conn.executor, _run_acceptance_cases, conn)
    except Exception as exc:
        conn.logger.bind(tag=TAG).error(f"尊严访谈批量用例失败: {exc}")
        await send_dignity_event(conn, "error", {"message": "尊严访谈批量用例运行失败。"})
        return

    passed = sum(1 for item in results if item.get("passed"))
    _write_dignity_log(
        conn,
        "debug_cases_complete",
        {"turn_count": len(results), "reply": f"{passed}/{len(results)}"},
        source="debug",
    )
    await send_dignity_event(
        conn,
        "debug_cases_complete",
        {"count": len(results), "passed": passed, "results": results},
    )


async def generate_dignity_document(conn, msg_json: Optional[Dict[str, Any]] = None) -> None:
    _ensure_dignity_runtime(conn)
    msg_json = msg_json or {}
    conn.dignity_patient_id = msg_json.get("patient_id") or conn.dignity_patient_id
    memory = _load_persisted_memory(conn)
    state_memory = {}
    if conn.dignity_debug_state:
        state_memory = conn.dignity_debug_state.get("dignity_memory", {})
    elif conn.dignity_state:
        state_memory = conn.dignity_state.get("dignity_memory", {})
    if state_memory:
        memory = merge_dignity_memory(memory, state_memory)

    if not any(isinstance(items, list) and items for items in memory.values()):
        await send_dignity_event(conn, "document_error", {"message": "还没有可生成文档的访谈记忆。"})
        return

    await send_dignity_event(conn, "document_started", {})
    try:
        loop = asyncio.get_running_loop()
        document = await loop.run_in_executor(
            conn.executor,
            _run_dignity_document_generation,
            conn,
            memory,
        )
    except Exception as exc:
        conn.logger.bind(tag=TAG).error(f"尊严访谈文档生成失败: {exc}")
        await send_dignity_event(conn, "document_error", {"message": "生命访谈文档生成失败。"})
        return

    payload = {
        "patient_id": _memory_key(conn),
        "document": document,
        "dignity_memory": memory,
    }
    _write_dignity_log(conn, "document_generated", {"reply": document[:200]})
    await send_dignity_event(conn, "document_complete", payload)


async def handle_dignity_turn_if_active(conn, text: str) -> bool:
    _ensure_dignity_runtime(conn)
    if not conn.dignity_active:
        return False

    patient_text = (text or "").strip()
    if not patient_text:
        return True

    started_at = perf_counter()
    await send_stt_message(conn, patient_text)
    conn.client_abort = False

    try:
        loop = asyncio.get_running_loop()
        state = await loop.run_in_executor(
            conn.executor,
            _run_dignity_turn,
            conn,
            patient_text,
        )
    except Exception as exc:
        conn.logger.bind(tag=TAG).error(f"尊严访谈 Graph 处理失败: {exc}")
        await send_dignity_event(
            conn,
            "error",
            {"message": "尊严访谈暂时无法处理，请稍后再试。"},
        )
        return True

    state["response_latency_ms"] = int((perf_counter() - started_at) * 1000)
    conn.dignity_state = state
    payload = _state_payload(state)
    payload["patient_text"] = patient_text

    if payload.get("strategy") == "handoff_nurse":
        _write_dignity_log(conn, "nurse_alert", payload)
        await send_dignity_event(conn, "nurse_alert", payload)
    _write_dignity_log(conn, "turn_result", payload)
    await send_dignity_event(conn, "turn_result", payload)

    _schedule_background_state_update(conn, state, "live")
    reply = (state.get("reply") or "").strip()
    if reply:
        _speak_dignity_reply(conn, reply)
    return True


def _schedule_background_state_update(conn, state: DignityState, target: str) -> None:
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_update_state_in_background(conn, state, target))
    except RuntimeError:
        logger = getattr(conn, "logger", None)
        if logger:
            logger.bind(tag=TAG).debug("尊严访谈后台记忆更新跳过：没有运行中的事件循环")


async def _update_state_in_background(conn, state: DignityState, target: str) -> None:
    try:
        loop = asyncio.get_running_loop()
        updated_state = await loop.run_in_executor(
            conn.executor,
            _run_background_state_update,
            conn,
            state,
        )
    except Exception as exc:
        logger = getattr(conn, "logger", None)
        if logger:
            logger.bind(tag=TAG).debug(f"尊严访谈后台记忆更新失败: {exc}")
        return

    current_state = conn.dignity_debug_state if target == "debug" else conn.dignity_state
    if current_state and int(current_state.get("turn_count", 0)) > int(updated_state.get("turn_count", 0)):
        return

    if target == "debug":
        conn.dignity_debug_state = updated_state
        event = "debug_state_updated"
    else:
        conn.dignity_state = updated_state
        event = "state_updated"

    payload = _state_payload(updated_state)
    payload["patient_text"] = updated_state.get("patient_text", "")
    await send_dignity_event(conn, event, payload)


def _run_dignity_turn(conn, patient_text: str) -> DignityState:
    state = conn.dignity_state
    if state is None:
        state = build_initial_state(
            session_id=conn.session_id,
            decision_model=_get_decision_model(conn),
        )
        state = _apply_persisted_memory(conn, state)
    else:
        state["decision_model"] = _get_decision_model(conn)
    return run_text_turn(state, patient_text)


def _run_dignity_debug_turn(conn, patient_text: str) -> DignityState:
    state = conn.dignity_debug_state
    if state is None:
        state = build_initial_state(
            session_id=f"{conn.session_id}:debug",
            decision_model=_get_decision_model(conn),
        )
        state = _apply_persisted_memory(conn, state)
    else:
        state["decision_model"] = _get_decision_model(conn)
    return run_text_turn(state, patient_text)


def _run_background_state_update(conn, state: DignityState) -> DignityState:
    next_state = dict(state)
    next_state["transcript"] = list(state.get("transcript", []))
    next_state["decision_model"] = _get_decision_model(conn)
    model = next_state["decision_model"]
    memory_update = model.update_dignity_memory(next_state)
    if isinstance(memory_update, dict):
        if isinstance(memory_update.get("dignity_memory"), dict):
            memory_update = memory_update["dignity_memory"]
        next_state["dignity_memory"] = merge_dignity_memory(
            next_state.get("dignity_memory", {}),
            memory_update,
        )
        _save_persisted_memory(conn, next_state["dignity_memory"])
    return next_state


def _run_dignity_document_generation(conn, memory: Dict[str, Any]) -> str:
    model = _get_decision_model(conn)
    return model.generate_dignity_document(memory).strip()


def _run_acceptance_cases(conn):
    results = []
    for case in ACCEPTANCE_CASES:
        state = build_initial_state(
            session_id=f"{conn.session_id}:{case['case_id']}",
            decision_model=_get_decision_model(conn),
        )
        state = run_text_turn(state, case["patient_text"])
        strategy = state.get("strategy", "")
        expected_strategies = case.get("expected_strategy", [])
        expected_route = STRATEGY_TO_ROUTE.get(strategy, "continue")
        expected_stage = case.get("expected_stage")
        passed = (
            (state.get("current_stage") == expected_stage or state.get("detected_stage") == expected_stage)
            and strategy in expected_strategies
        )
        results.append(
            {
                "case_id": case["case_id"],
                "patient_text": case["patient_text"],
                "passed": passed,
                "expected": {
                    "stage": case.get("expected_stage"),
                    "strategy": expected_strategies,
                    "route": expected_route,
                },
                "actual": _state_payload(state),
            }
        )
    return results


def _speak_dignity_reply(conn, reply: str) -> None:
    from core.handle.intentHandler import speak_txt

    conn.sentence_id = str(uuid.uuid4().hex)
    conn.dialogue.put(Message(role="user", content=conn.dignity_state.get("patient_text", "")))
    speak_txt(conn, reply)
