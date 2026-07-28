import json

TAG = __name__


async def handleAbortMessage(conn):
    conn.logger.bind(tag=TAG).info("Abort message received")
    if (
        getattr(conn, "voice_mode", "cascade") == "doubao_s2s"
        and getattr(conn, "realtime_voice", None) is not None
    ):
        await conn.realtime_voice.interrupt()
        conn.logger.bind(tag=TAG).info("Realtime abort message handled")
        return

    # 设置成打断状态，会自动打断llm、tts任务
    conn.client_abort = True
    conn.clear_queues()
    # 打断客户端说话状态
    await conn.websocket.send(
        json.dumps({"type": "tts", "state": "stop", "session_id": conn.session_id})
    )
    conn.clearSpeakStatus()
    conn.logger.bind(tag=TAG).info("Abort message received-end")
