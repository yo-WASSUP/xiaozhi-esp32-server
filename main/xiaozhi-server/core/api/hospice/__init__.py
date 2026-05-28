"""Hospice family/patient REST API route registration."""
from aiohttp import web
from config.logger import setup_logging

from core.api.hospice.handler import HospiceFamilyHandler

TAG = __name__
logger = setup_logging()


def register_hospice_routes(app: web.Application, config: dict):
    handler = HospiceFamilyHandler(config)

    routes = [
        web.get("/api/hospice/summary/today", handler.handle_summary_today),
        web.get("/api/hospice/summary/history", handler.handle_summary_history),
        web.get("/api/hospice/emotion/today", handler.handle_emotion_today),
        web.get("/api/hospice/emotion/trend", handler.handle_emotion_trend),
        web.post("/api/hospice/message", handler.handle_send_message),
        web.get("/api/hospice/messages", handler.handle_get_messages),
        web.get("/api/hospice/config", handler.handle_client_config),
        web.post("/api/hospice/tts/speak", handler.handle_tts_speak),
        web.post("/api/hospice/tts/stop", handler.handle_tts_stop),
        web.get("/api/hospice/voice-clone/config", handler.handle_voice_clone_config),
        web.post("/api/hospice/voice-clone/train", handler.handle_voice_clone_train),
        web.get("/api/hospice/voice-clone/status", handler.handle_voice_clone_status),
        web.get("/api/hospice/voice-clone/list", handler.handle_voice_clone_list),
        web.delete("/api/hospice/voice-clone/delete", handler.handle_voice_clone_delete),
        web.post("/api/hospice/voice-clone/activate", handler.handle_voice_clone_activate),
        web.get("/api/hospice/contacts", handler.handle_get_contacts),
        web.post("/api/hospice/thread/read", handler.handle_mark_thread_read),
        web.post("/api/hospice/message/{id}/read", handler.handle_mark_read),
        web.get("/api/hospice/message/stream", handler.handle_message_stream),
        web.get("/api/hospice/call/ws", handler.handle_call_ws),
        web.post("/api/hospice/upload", handler.handle_upload),
        web.get("/api/hospice/conversations/today", handler.handle_conversations_today),
        web.post("/api/hospice/video/storyboard", handler.handle_video_storyboard),
        web.post("/api/hospice/video/render", handler.handle_video_render),
        web.get("/api/hospice/video/status", handler.handle_video_status),
        web.options("/api/hospice/{path:.*}", handler.handle_options),
    ]

    app.add_routes(routes)
    logger.bind(tag=TAG).info(f"安宁疗护 API 路由已注册 ({len(routes)} 条)")
