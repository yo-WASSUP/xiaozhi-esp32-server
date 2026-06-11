"""Dignity interview audio review endpoints."""
from __future__ import annotations

from aiohttp import web
from config.logger import setup_logging
from core.dignity.interview_audio import (
    load_audio_edit_record,
    normalize_segments,
    save_audio_segments,
    segments_from_transcript,
)

TAG = __name__
logger = setup_logging()


class HospiceInterviewAudioMixin:
    async def handle_interview_audio_segments(self, request):
        """GET /api/hospice/interview/audio-segments/latest?device_id=xxx."""
        try:
            device_id = (request.query.get("device_id") or "default_patient").strip() or "default_patient"
            payload = load_audio_edit_record(device_id)
            return web.json_response(
                {
                    "success": True,
                    "patient_id": payload.get("patient_id") or device_id,
                    "segments": payload.get("segments") or [],
                    "updated_at": payload.get("updated_at") or "",
                },
                headers=self._cors_headers(),
            )
        except Exception as exc:
            logger.bind(tag=TAG).error(f"访谈语音片段读取失败: {exc}")
            return web.json_response(
                {"success": False, "error": str(exc)},
                status=500,
                headers=self._cors_headers(),
            )

    async def handle_interview_audio_segments_save(self, request):
        """POST /api/hospice/interview/audio-segments/save body: {device_id, segments}."""
        try:
            data = await request.json()
            device_id = (data.get("device_id") or "default_patient").strip() or "default_patient"
            segments = data.get("segments")
            if not isinstance(segments, list):
                segments = segments_from_transcript(data.get("transcript"))
            payload = save_audio_segments(device_id, normalize_segments(segments))
            return web.json_response(
                {"success": True, **payload},
                headers=self._cors_headers(),
            )
        except Exception as exc:
            logger.bind(tag=TAG).error(f"访谈语音片段保存失败: {exc}")
            return web.json_response(
                {"success": False, "error": str(exc)},
                status=500,
                headers=self._cors_headers(),
            )
