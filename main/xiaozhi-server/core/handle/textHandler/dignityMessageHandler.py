from typing import Any, Dict
import time

from core.dignity.runtime import (
    confirm_dignity_document,
    generate_dignity_document,
    reset_dignity_debug,
    run_dignity_debug_turn,
    send_dignity_event,
    start_dignity_mode,
    stop_dignity_mode,
    update_dignity_memory,
)
from core.handle.textMessageHandler import TextMessageHandler
from core.handle.textMessageType import TextMessageType

TAG = __name__


class DignityTextMessageHandler(TextMessageHandler):
    """尊严疗法模式控制消息处理器"""

    @property
    def message_type(self) -> TextMessageType:
        return TextMessageType.DIGNITY

    async def handle(self, conn, msg_json: Dict[str, Any]) -> None:
        conn.last_activity_time = time.time() * 1000
        action = (msg_json.get("action") or "").strip().lower()
        if action == "start":
            await start_dignity_mode(conn, msg_json)
            return
        if action == "stop":
            await stop_dignity_mode(conn)
            return
        if action == "debug_turn":
            await run_dignity_debug_turn(conn, msg_json.get("text", ""))
            return
        if action == "debug_reset":
            await reset_dignity_debug(conn)
            return
        if action == "generate_document":
            await generate_dignity_document(conn, msg_json)
            return
        if action == "confirm_document":
            await confirm_dignity_document(conn, msg_json)
            return
        if action == "update_memory":
            await update_dignity_memory(conn, msg_json)
            return

        conn.logger.bind(tag=TAG).warning(f"未知尊严疗法动作: {action}")
        await send_dignity_event(
            conn,
            "error",
            {"message": f"未知尊严疗法动作: {action or 'empty'}"},
        )
