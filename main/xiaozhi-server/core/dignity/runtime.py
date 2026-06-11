from __future__ import annotations

import asyncio
import json
import re
import uuid
import zipfile
from datetime import datetime
from pathlib import Path
from time import perf_counter
from typing import Any, Dict, Optional, Tuple
from xml.sax.saxutils import escape

from core.dignity.engine.config import (
    ROBOT_ACTIONS,
)
from core.dignity.engine.graph import (
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
from core.dignity.interview_audio import (
    apply_audio_edits_to_memory,
    merge_and_save_transcript_segments,
)
from core.dignity.engine.rules import strategy_to_eye_expression, strategy_to_robot_action
from core.handle.sendAudioHandle import send_stt_message
from core.utils.dialogue import Message
from core.utils.util import extract_json_from_string

TAG = __name__
SERVER_ROOT = Path(__file__).resolve().parents[2]
LOG_DIR = SERVER_ROOT / "data" / "dignity_logs"
MEMORY_DIR = SERVER_ROOT / "data" / "dignity_memory"
MEDIA_DIR = SERVER_ROOT / "data" / "hospice_media"
DOCUMENT_DIR = MEDIA_DIR / "dignity_documents"
DOCUMENT_SOURCE_DIR = DOCUMENT_DIR / "sources"


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
        strategy = "continue_deeper"
        return {
            "current_stage": "rapport",
            "strategy": strategy,
            "robot_action": "listening",
            "robot_action_enum": ROBOT_ACTIONS,
            "eye_expression": "soft_smile",
            "reply": "",
            "turn_count": 0,
            "followup_count": 0,
            "emotion_state": {"mood": "calm", "engagement": "medium"},
            "dignity_memory": {},
            "transcript": [],
        }

    decision_model = state.get("decision_model")
    strategy = str(state.get("strategy") or "continue_deeper")
    robot_action = _normalize_robot_action(strategy_to_robot_action(strategy))
    current_stage = state.get("current_stage", "rapport")
    return {
        "current_stage": current_stage,
        "strategy": strategy,
        "robot_action": robot_action,
        "robot_action_enum": ROBOT_ACTIONS,
        "eye_expression": strategy_to_eye_expression(strategy),
        "reply": state.get("reply", ""),
        "followup_count": state.get("followup_count", 0),
        "turn_count": state.get("turn_count", 0),
        "emotion_state": state.get("emotion_state", {"mood": "calm", "engagement": "medium"}),
        "dignity_memory": state.get("dignity_memory", {}),
        "transcript": state.get("transcript", []),
        "raw_decision": getattr(decision_model, "last_raw_decision", None),
        "raw_llm_content": getattr(decision_model, "last_raw_content", ""),
        "raw_memory": getattr(decision_model, "last_raw_memory", None),
        "raw_memory_content": getattr(decision_model, "last_raw_memory_content", ""),
        "response_latency_ms": state.get("response_latency_ms"),
    }


def _normalize_robot_action(value: Any) -> str:
    action = str(value or "listening").strip()
    return action if action in ROBOT_ACTIONS else "listening"


async def send_robot_action_event(
    conn,
    source_event: str,
    data: Optional[Dict[str, Any]] = None,
) -> None:
    data = data or {}
    if "robot_action" not in data:
        return
    robot_action = _normalize_robot_action(data.get("robot_action"))
    payload = {
        "type": "client_action",
        "action": "robot_action",
        "source": "dignity",
        "source_event": source_event,
        "session_id": conn.session_id,
        "robot_action": robot_action,
        "robot_action_enum": ROBOT_ACTIONS,
        "eye_expression": data.get("eye_expression", ""),
        "current_stage": data.get("current_stage", ""),
        "strategy": data.get("strategy", ""),
    }
    await conn.websocket.send(json.dumps(payload, ensure_ascii=False))


async def send_dignity_event(conn, event: str, data: Optional[Dict[str, Any]] = None) -> None:
    payload = {
        "type": "dignity",
        "event": event,
        "session_id": conn.session_id,
        "data": data or {},
    }
    await conn.websocket.send(json.dumps(payload, ensure_ascii=False))
    await send_robot_action_event(conn, event, data)


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
    document_source = _load_dignity_document_source(conn)
    if document_source:
        payload.update(document_source)
    _write_dignity_log(conn, "mode_started", payload)
    await send_dignity_event(conn, "mode_started", payload)


async def stop_dignity_mode(conn) -> None:
    _ensure_dignity_runtime(conn)
    conn.dignity_active = False
    conn.logger.bind(tag=TAG).info("尊严访谈模式已关闭")
    payload = _state_payload(conn.dignity_state)
    payload["robot_action"] = "idle"
    payload["eye_expression"] = "calm"
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
    memory = apply_audio_edits_to_memory(_memory_key(conn), memory)

    if not any(isinstance(items, list) and items for items in memory.values()):
        await send_dignity_event(conn, "document_error", {"message": "还没有可生成人生故事的访谈记忆。"})
        return

    await send_dignity_event(conn, "document_started", {})
    try:
        loop = asyncio.get_running_loop()
        document = await loop.run_in_executor(
            conn.executor,
            _run_dignity_document_draft,
            conn,
            memory,
        )
    except Exception as exc:
        conn.logger.bind(tag=TAG).error(f"尊严访谈人生故事生成失败: {exc}")
        await send_dignity_event(conn, "document_error", {"message": "人生故事生成失败。"})
        return

    payload = {
        "patient_id": _memory_key(conn),
        "document": document,
        "document_status": "draft",
        "dignity_memory": memory,
    }
    _save_dignity_document_source(conn, document, "draft")
    _write_dignity_log(conn, "document_generated", {"reply": document[:200]})
    await send_dignity_event(conn, "document_complete", payload)


async def confirm_dignity_document(conn, msg_json: Optional[Dict[str, Any]] = None) -> None:
    _ensure_dignity_runtime(conn)
    msg_json = msg_json or {}
    conn.dignity_patient_id = msg_json.get("patient_id") or conn.dignity_patient_id
    document = (msg_json.get("document") or "").strip()
    if not document:
        await send_dignity_event(conn, "document_error", {"message": "请先生成并确认人生故事内容。"})
        return

    await send_dignity_event(conn, "document_confirm_started", {})
    try:
        loop = asyncio.get_running_loop()
        filename, url = await loop.run_in_executor(
            conn.executor,
            _write_dignity_docx,
            conn,
            document,
        )
    except Exception as exc:
        conn.logger.bind(tag=TAG).error(f"尊严访谈人生故事 Word 保存失败: {exc}")
        await send_dignity_event(conn, "document_error", {"message": "人生故事 Word 保存失败。"})
        return

    payload = {
        "patient_id": _memory_key(conn),
        "document": document,
        "document_status": "confirmed",
        "document_url": url,
        "document_filename": filename,
    }
    _save_dignity_document_source(conn, document, "confirmed", url, filename)
    _write_dignity_log(conn, "document_confirmed", {"reply": document[:200]})
    await send_dignity_event(conn, "document_confirmed", payload)


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
    _save_interview_audio_segments(conn, state)
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
    _save_interview_audio_segments(conn, updated_state)
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
    next_state = run_text_turn(state, patient_text)
    _attach_last_audio_segment(conn, next_state)
    return next_state


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


def _save_interview_audio_segments(conn, state: Optional[DignityState]) -> None:
    if not state:
        return
    try:
        merge_and_save_transcript_segments(_memory_key(conn), state.get("transcript", []))
    except Exception as exc:
        logger = getattr(conn, "logger", None)
        if logger:
            logger.bind(tag=TAG).debug(f"访谈语音审核片段保存失败: {exc}")


def _attach_last_audio_segment(conn, state: DignityState) -> None:
    audio_segment = getattr(conn, "dignity_last_audio_segment", None)
    if not isinstance(audio_segment, dict):
        return
    try:
        delattr(conn, "dignity_last_audio_segment")
    except Exception:
        conn.dignity_last_audio_segment = None
    transcript = state.get("transcript")
    if not isinstance(transcript, list) or not transcript:
        return
    last = transcript[-1]
    if not isinstance(last, dict):
        return
    if audio_segment.get("audio_url"):
        last["audio_url"] = audio_segment.get("audio_url")
    duration = audio_segment.get("duration")
    if isinstance(duration, (int, float)) and duration > 0:
        last["start_time"] = 0
        last["end_time"] = duration


def _run_dignity_document_draft(conn, memory: Dict[str, Any]) -> str:
    model = _get_decision_model(conn)
    return model.generate_dignity_document(memory).strip()


def _write_dignity_docx(conn, markdown_text: str) -> Tuple[str, str]:
    DOCUMENT_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{_memory_key(conn)}_{datetime.now():%Y%m%d_%H%M%S}.docx"
    path = DOCUMENT_DIR / filename

    body_xml = []
    lines = [line.rstrip() for line in (markdown_text or "").splitlines()]
    for line in lines:
        text = line.strip()
        if not text:
            continue
        if text.startswith("# "):
            body_xml.append(_docx_paragraph(text[2:].strip(), style="Title", align="center", font_size=32))
        elif text.startswith("## "):
            body_xml.append(_docx_paragraph(text[3:].strip(), style="Heading1", font_size=26))
        elif re.fullmatch(r"\d{4}年\d{1,2}月\d{1,2}日星期[一二三四五六日天]", text):
            body_xml.append(_docx_paragraph(text, align="center", font_size=20))
        elif text.startswith(("- ", "* ")):
            body_xml.append(_docx_paragraph(f"• {text[2:].strip()}"))
        else:
            body_xml.append(_docx_paragraph(text, first_line_indent=True))

    _write_docx_package(path, "\n".join(body_xml))
    return filename, f"/hospice-media/dignity_documents/{filename}"


def _save_dignity_document_source(
    conn,
    document: str,
    status: str,
    document_url: str = "",
    document_filename: str = "",
) -> None:
    try:
        DOCUMENT_SOURCE_DIR.mkdir(parents=True, exist_ok=True)
        patient_id = _memory_key(conn)
        payload = {
            "patient_id": patient_id,
            "document": document,
            "document_status": status,
            "document_url": document_url,
            "document_filename": document_filename,
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        }
        latest_path = DOCUMENT_SOURCE_DIR / f"{patient_id}_latest.json"
        with latest_path.open("w", encoding="utf-8") as file:
            json.dump(payload, file, ensure_ascii=False, indent=2)
    except Exception as exc:
        logger = getattr(conn, "logger", None)
        if logger:
            logger.bind(tag=TAG).debug(f"人生故事源文件保存失败: {exc}")


def _load_dignity_document_source(conn) -> Dict[str, Any]:
    try:
        latest_path = DOCUMENT_SOURCE_DIR / f"{_memory_key(conn)}_latest.json"
        if not latest_path.exists():
            return {}
        with latest_path.open("r", encoding="utf-8") as file:
            payload = json.load(file) or {}
        document = payload.get("document") or ""
        if not document:
            return {}
        return {
            "document": document,
            "document_status": payload.get("document_status") or "draft",
            "document_url": payload.get("document_url") or "",
            "document_filename": payload.get("document_filename") or "",
            "document_updated_at": payload.get("updated_at") or "",
        }
    except Exception as exc:
        logger = getattr(conn, "logger", None)
        if logger:
            logger.bind(tag=TAG).debug(f"人生故事源文件读取失败: {exc}")
        return {}


def _docx_paragraph(
    text: str,
    style: str = "",
    align: str = "",
    font_size: int = 22,
    first_line_indent: bool = False,
) -> str:
    props = []
    if style:
        props.append(f'<w:pStyle w:val="{style}"/>')
    if align:
        props.append(f'<w:jc w:val="{align}"/>')
    if first_line_indent:
        props.append('<w:ind w:firstLine="440"/>')
    props.append('<w:spacing w:line="360" w:lineRule="auto"/>')
    ppr = f"<w:pPr>{''.join(props)}</w:pPr>"
    safe_text = escape(text)
    return (
        f"<w:p>{ppr}<w:r><w:rPr><w:rFonts w:ascii=\"Microsoft YaHei\" "
        f"w:eastAsia=\"Microsoft YaHei\"/><w:sz w:val=\"{font_size}\"/></w:rPr>"
        f"<w:t xml:space=\"preserve\">{safe_text}</w:t></w:r></w:p>"
    )


def _write_docx_package(path: Path, body_xml: str) -> None:
    document_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    {body_xml}
    <w:sectPr>
      <w:pgSz w:w="11906" w:h="16838"/>
      <w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440" w:header="720" w:footer="720" w:gutter="0"/>
    </w:sectPr>
  </w:body>
</w:document>"""
    content_types = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
  <Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
</Types>"""
    rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>"""
    styles = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/></w:style>
  <w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/><w:basedOn w:val="Normal"/><w:pPr><w:jc w:val="center"/></w:pPr><w:rPr><w:b/><w:sz w:val="32"/></w:rPr></w:style>
  <w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:basedOn w:val="Normal"/><w:rPr><w:b/><w:sz w:val="26"/></w:rPr></w:style>
</w:styles>"""
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as docx:
        docx.writestr("[Content_Types].xml", content_types)
        docx.writestr("_rels/.rels", rels)
        docx.writestr("word/document.xml", document_xml)
        docx.writestr("word/styles.xml", styles)


def _speak_dignity_reply(conn, reply: str) -> None:
    from core.handle.intentHandler import speak_txt

    conn.sentence_id = str(uuid.uuid4().hex)
    conn.dialogue.put(Message(role="user", content=conn.dignity_state.get("patient_text", "")))
    speak_txt(conn, reply)
