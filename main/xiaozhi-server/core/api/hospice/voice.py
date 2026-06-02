"""TTS and voice-clone endpoints for the hospice API."""
import asyncio
import json
import mimetypes
import os
import re
import time
import uuid
import yaml
from urllib.parse import urlparse

from aiohttp import ClientSession, web
from config.logger import setup_logging
from core.connection import ConnectionHandler
from core.handle.abortHandle import handleAbortMessage

TAG = __name__
logger = setup_logging()


class HospiceVoiceMixin:
    def _selected_tts_config(self):
        selected = (self.config.get("selected_module") or {}).get("TTS")
        return (self.config.get("TTS") or {}).get(selected, {}) if selected else {}

    def _voice_clone_config(self):
        tts_config = self._selected_tts_config()
        hospice_config = self.config.get("hospice", {}) or {}
        cosy_config = hospice_config.get("cosyvoice", {}) or {}
        oss_config = cosy_config.get("oss", {}) or {}
        ali_llm_config = (self.config.get("LLM") or {}).get("AliLLM", {}) or {}
        prefix = re.sub(r"[^A-Za-z0-9]", "", str(cosy_config.get("prefix") or "hospice"))[:10]
        return {
            "provider": "aliyun_cosyvoice",
            "api_key": cosy_config.get("api_key") or tts_config.get("api_key") or ali_llm_config.get("api_key"),
            "model": cosy_config.get("model") or tts_config.get("model") or "cosyvoice-v3.5-flash",
            "prefix": prefix or "hospice",
            "language": cosy_config.get("language") or "zh",
            "max_sample_mb": int(cosy_config.get("max_sample_mb", 10)),
            "max_prompt_audio_length": float(cosy_config.get("max_prompt_audio_length", 20.0)),
            "enable_preprocess": bool(cosy_config.get("enable_preprocess", True)),
            "instruction": cosy_config.get("instruction") or "请用亲切自然的中文表达，语速稍慢。",
            "oss": {
                "access_key_id": oss_config.get("access_key_id") or os.getenv("ALIYUN_OSS_ACCESS_KEY_ID") or os.getenv("OSS_ACCESS_KEY_ID"),
                "access_key_secret": oss_config.get("access_key_secret") or os.getenv("ALIYUN_OSS_ACCESS_KEY_SECRET") or os.getenv("OSS_ACCESS_KEY_SECRET"),
                "endpoint": oss_config.get("endpoint") or os.getenv("ALIYUN_OSS_ENDPOINT") or os.getenv("OSS_ENDPOINT"),
                "bucket": oss_config.get("bucket") or os.getenv("ALIYUN_OSS_BUCKET") or os.getenv("OSS_BUCKET"),
                "prefix": oss_config.get("prefix") or os.getenv("ALIYUN_OSS_PREFIX") or os.getenv("OSS_PREFIX") or "xiaozhi/cosyvoice",
                "expires": int(oss_config.get("expires", 3600)),
            },
        }

    def _voice_clone_missing_config(self, clone_config, require_oss=True):
        missing = []
        if not clone_config.get("api_key"):
            missing.append("cosyvoice.api_key")
        if not require_oss:
            return missing
        oss_config = clone_config.get("oss") or {}
        for key in ("access_key_id", "access_key_secret", "endpoint", "bucket"):
            if not oss_config.get(key):
                missing.append(f"cosyvoice.oss.{key}")
        return missing

    def _load_voice_settings(self):
        if not os.path.exists(self.voice_settings_path):
            return {}
        try:
            with open(self.voice_settings_path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            logger.bind(tag=TAG).warning(f"读取音色设置失败: {e}")
            return {}

    def _save_voice_settings(self, data):
        os.makedirs(os.path.dirname(self.voice_settings_path), exist_ok=True)
        with open(self.voice_settings_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(
                data,
                f,
                allow_unicode=True,
                sort_keys=False,
                default_flow_style=False,
            )

    def _get_device_voice_settings(self, device_id):
        current = self._load_voice_settings().get(device_id, {})
        if current and not isinstance(current.get("voices"), list):
            legacy = self._compact_voice_record(current)
            if legacy:
                current = {**current, "voices": [legacy]}
        alias = (current.get("alias") or "").strip()
        if alias in ("", "家属音色", "家属声音"):
            voices = current.get("voices") or []
            preferred = None
            for item in voices:
                if not isinstance(item, dict):
                    continue
                item_alias = (item.get("alias") or "").strip()
                if item.get("active") and item_alias and item_alias not in ("家属音色", "家属声音"):
                    preferred = item_alias
                    break
                if not preferred and item_alias and item_alias not in ("家属音色", "家属声音"):
                    preferred = item_alias
            if preferred:
                current["alias"] = preferred
        current = self._sync_active_voice_summary(current)
        return current

    def _compact_voice_record(self, data):
        voice_id = data.get("voice_id") or data.get("speaker_id")
        if not voice_id:
            return None
        keep_keys = (
            "provider", "voice_id", "speaker_id", "alias", "model", "status", "active",
            "resource_link", "oss_object_key", "instruction", "updated_at",
        )
        record = {key: data.get(key) for key in keep_keys if data.get(key) is not None}
        record["voice_id"] = voice_id
        record["speaker_id"] = data.get("speaker_id") or voice_id
        record["alias"] = data.get("alias") or "家属音色"
        return record

    def _merge_voice_alias(self, old_alias, new_alias):
        old_alias = (old_alias or "").strip()
        new_alias = (new_alias or "").strip()
        if new_alias and new_alias not in ("家属音色", "家属声音"):
            return new_alias
        return old_alias or new_alias or "家属音色"

    def _voice_record_id(self, voice):
        if not isinstance(voice, dict):
            return None
        return voice.get("voice_id") or voice.get("speaker_id")

    def _voice_is_usable(self, voice):
        status = (voice.get("status") or "").strip()
        return status in ("", "OK", "Success", "Active")

    def _sync_active_voice_summary(self, current):
        voices = [v for v in current.get("voices", []) if isinstance(v, dict)]
        active_id = current.get("active_voice_id")
        if not active_id and current.get("active"):
            active_id = current.get("voice_id") or current.get("speaker_id")

        active_record = None
        for item in voices:
            item_id = self._voice_record_id(item)
            is_active = bool(active_id and item_id == active_id and self._voice_is_usable(item))
            item["active"] = is_active
            if is_active:
                active_record = item

        current["voices"] = voices
        summary_keys = (
            "provider", "voice_id", "speaker_id", "alias", "model", "status",
            "oss_object_key", "instruction", "updated_at", "resource_link",
        )
        if not active_record:
            current.pop("active_voice_id", None)
            current["active"] = False
            for key in summary_keys:
                current.pop(key, None)
            return current

        current["active_voice_id"] = self._voice_record_id(active_record)
        current["active"] = True
        for key in summary_keys:
            if active_record.get(key) is not None:
                current[key] = active_record.get(key)
            else:
                current.pop(key, None)
        current["voice_id"] = self._voice_record_id(active_record)
        current["speaker_id"] = active_record.get("speaker_id") or current["voice_id"]
        return current

    def _merge_voice_history(self, current, patch, updated_at):
        voices = current.get("voices")
        if not isinstance(voices, list):
            voices = []

        legacy = self._compact_voice_record({**current, "updated_at": current.get("updated_at")})
        if legacy and not any((v.get("voice_id") or v.get("speaker_id")) == legacy["voice_id"] for v in voices if isinstance(v, dict)):
            voices.insert(0, legacy)

        incoming = self._compact_voice_record({**current, **patch, "updated_at": updated_at})
        if not incoming:
            current["voices"] = voices
            return current

        incoming_id = incoming["voice_id"]
        if patch.get("active") is not True:
            incoming["active"] = False
        merged = []
        found = False
        for item in voices:
            if not isinstance(item, dict):
                continue
            item_id = self._voice_record_id(item)
            if patch.get("active") is True:
                item = {**item, "active": False}
            if item_id == incoming_id:
                incoming["alias"] = self._merge_voice_alias(item.get("alias"), incoming.get("alias"))
                item = {**item, **incoming}
                found = True
            else:
                item["alias"] = self._merge_voice_alias(item.get("alias"), item.get("alias"))
            merged.append(item)
        if not found:
            merged.insert(0, incoming)
        if patch.get("active") is True:
            current["active_voice_id"] = incoming_id
        current["voices"] = merged[:20]
        return current

    def _normalize_cosyvoice_record(self, item):
        if not isinstance(item, dict):
            return None
        voice_id = (
            item.get("voice_id")
            or item.get("voiceId")
            or item.get("speaker_id")
            or item.get("custom_voice_id")
        )
        if not voice_id:
            return None
        return {
            "provider": "aliyun_cosyvoice",
            "voice_id": voice_id,
            "speaker_id": voice_id,
            "alias": item.get("alias") or item.get("name") or item.get("voice_name"),
            "model": item.get("target_model") or item.get("model"),
            "status": item.get("status") or item.get("state") or "UNKNOWN",
            "resource_link": item.get("resource_link") or item.get("url"),
            "updated_at": item.get("gmt_modified") or item.get("updated_at") or item.get("create_time"),
        }

    def _merge_device_voice_records(self, device_id, records):
        settings = self._load_voice_settings()
        current = settings.get(device_id, {})
        updated_at = time.strftime("%Y-%m-%d %H:%M:%S")
        current = self._merge_voice_history(current, {}, updated_at)
        voices = [v for v in current.get("voices", []) if isinstance(v, dict)]
        active_id = current.get("active_voice_id") or current.get("voice_id") or current.get("speaker_id")
        current_alias = current.get("alias")
        by_id = {
            (voice.get("voice_id") or voice.get("speaker_id")): voice
            for voice in voices
            if voice.get("voice_id") or voice.get("speaker_id")
        }
        for record in records:
            record_id = record.get("voice_id") or record.get("speaker_id")
            if not record_id:
                continue
            old = by_id.get(record_id, {})
            if (
                record_id == active_id
                and current_alias
                and current_alias not in ("家属音色", "家属声音")
                and (not record.get("alias") or record.get("alias") in ("家属音色", "家属声音"))
            ):
                record["alias"] = current_alias
            record = {
                **record,
                "alias": self._merge_voice_alias(old.get("alias"), record.get("alias")),
                "active": old.get("active", record_id == active_id),
            }
            by_id[record_id] = {**old, **record}
        current["voices"] = list(by_id.values())[:50]
        current = self._sync_active_voice_summary(current)
        settings[device_id] = current
        self._save_voice_settings(settings)
        return current

    def _remove_device_voice_record(self, device_id, voice_id):
        settings = self._load_voice_settings()
        current = settings.get(device_id, {})
        voices = current.get("voices")
        if not isinstance(voices, list):
            voices = []
        kept = []
        removed = False
        fallback = None
        for item in voices:
            if not isinstance(item, dict):
                continue
            item_id = item.get("voice_id") or item.get("speaker_id")
            if item_id == voice_id:
                removed = True
                continue
            kept.append(item)
            if fallback is None and item.get("active"):
                fallback = item
        if current.get("voice_id") == voice_id or current.get("speaker_id") == voice_id:
            current.pop("voice_id", None)
            current.pop("speaker_id", None)
            current["active"] = False
            if fallback:
                current["voice_id"] = fallback.get("voice_id") or fallback.get("speaker_id")
                current["speaker_id"] = fallback.get("speaker_id") or fallback.get("voice_id")
                current["alias"] = fallback.get("alias") or current.get("alias")
                current["model"] = fallback.get("model") or current.get("model")
                current["instruction"] = fallback.get("instruction") or current.get("instruction")
                current["active"] = bool(fallback.get("active", True))
        current["voices"] = kept
        if current.get("active_voice_id") == voice_id:
            current.pop("active_voice_id", None)
        if fallback and not current.get("active"):
            current["active_voice_id"] = fallback.get("voice_id") or fallback.get("speaker_id")
        settings[device_id] = current
        self._save_voice_settings(settings)
        return removed, current, fallback

    def _update_device_voice_settings(self, device_id, patch):
        settings = self._load_voice_settings()
        current = settings.get(device_id, {})
        previous_active_id = current.get("active_voice_id")
        if not previous_active_id and current.get("active"):
            previous_active_id = current.get("voice_id") or current.get("speaker_id")
        current.update(patch)
        if patch.get("active") is not True and previous_active_id:
            current["active_voice_id"] = previous_active_id
        updated_at = time.strftime("%Y-%m-%d %H:%M:%S")
        current["updated_at"] = updated_at
        current = self._merge_voice_history(current, patch, updated_at)
        current = self._sync_active_voice_summary(current)
        settings[device_id] = current
        self._save_voice_settings(settings)
        return current

    def _clear_active_voice_settings(self, device_id):
        settings = self._load_voice_settings()
        current = settings.get(device_id, {})
        voices = current.get("voices")
        if not isinstance(voices, list):
            voices = []
        for item in voices:
            if isinstance(item, dict):
                item["active"] = False
        current["voices"] = voices
        current["active"] = False
        current.pop("active_voice_id", None)
        for key in (
            "provider", "voice_id", "speaker_id", "alias", "model", "status",
            "oss_object_key", "instruction", "resource_link",
        ):
            current.pop(key, None)
        current["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        settings[device_id] = current
        self._save_voice_settings(settings)
        return current

    def _apply_active_voice_to_config(self, voice_settings):
        voice_id = voice_settings.get("voice_id") or voice_settings.get("speaker_id")
        selected = (self.config.get("selected_module") or {}).get("TTS")
        if not selected:
            return
        tts_config = (self.config.get("TTS") or {}).get(selected)
        if not isinstance(tts_config, dict):
            return
        if tts_config.get("type") == "alibl_stream":
            tts_config.setdefault("_hospice_default_model", tts_config.get("model"))
            tts_config.setdefault("_hospice_default_instruction", tts_config.get("instruction"))
            if not voice_id:
                tts_config.pop("private_voice", None)
                default_model = tts_config.get("_hospice_default_model")
                default_instruction = tts_config.get("_hospice_default_instruction")
                if default_model:
                    tts_config["model"] = default_model
                if default_instruction:
                    tts_config["instruction"] = default_instruction
                else:
                    tts_config.pop("instruction", None)
                return
            tts_config["private_voice"] = voice_id
            if voice_settings.get("model"):
                tts_config["model"] = voice_settings["model"]
            if voice_settings.get("instruction"):
                tts_config["instruction"] = voice_settings["instruction"]

    async def _apply_voice_settings_to_active_connection(self, device_id, voice_settings):
        conn = ConnectionHandler.get_active_connection(device_id)
        if conn is None or getattr(conn, "tts", None) is None:
            return False
        conn.config = self.config
        apply_settings = getattr(conn.tts, "_apply_hospice_voice_settings", None)
        if callable(apply_settings):
            apply_settings(conn)
        close_ws = getattr(conn.tts, "close", None)
        if callable(close_ws):
            result = close_ws()
            if asyncio.iscoroutine(result):
                if conn.loop is asyncio.get_running_loop():
                    await result
                else:
                    await asyncio.wrap_future(
                        asyncio.run_coroutine_threadsafe(result, conn.loop)
                    )
        logger.bind(tag=TAG).info(
            f"已同步在线 TTS 音色: device={device_id}, active={bool(voice_settings.get('active'))}"
        )
        return True

    def _safe_speaker_id(self, speaker_id):
        speaker_id = (speaker_id or "").strip()
        if not re.match(r"^S_[A-Za-z0-9_-]{4,64}$", speaker_id):
            raise ValueError("音色 ID 格式不正确，格式通常为 S_xxx")
        return speaker_id

    def _new_speaker_id(self):
        return f"S_hospice_{uuid.uuid4().hex[:16]}"

    async def _post_voice_clone(self, path, payload, resource_id):
        clone_config = self._voice_clone_config()
        api_key = clone_config.get("api_key")
        if not api_key:
            raise RuntimeError("缺少豆包声音复刻 V3 X-Api-Key，请配置 hospice.voice_clone.api_key 或 TTS.<当前模块>.api_key，不要使用 access_token")
        if not clone_config.get("appid"):
            raise RuntimeError("缺少豆包声音复刻 appid，请配置 hospice.voice_clone.appid 或当前 TTS 模块 appid")
        headers = {
            "X-Api-Key": api_key,
            "X-Api-Resource-Id": resource_id,
            "X-Api-Request-Id": str(uuid.uuid4()),
            "Content-Type": "application/json",
        }
        async with ClientSession() as session:
            async with session.post(
                f"https://openspeech.bytedance.com{path}",
                headers=headers,
                json=payload,
                timeout=60,
            ) as resp:
                try:
                    data = await resp.json()
                except Exception:
                    text = await resp.text()
                    data = {"BaseResp": {"StatusCode": resp.status, "StatusMessage": text}}
                if resp.status >= 400:
                    raise RuntimeError(data.get("message") or data.get("BaseResp", {}).get("StatusMessage") or f"火山接口 HTTP {resp.status}")
                return data

    def _safe_voice_id(self, voice_id):
        voice_id = (voice_id or "").strip()
        if not re.match(r"^[A-Za-z0-9_.-]{4,160}$", voice_id):
            raise ValueError("音色 ID 格式不正确")
        return voice_id

    def _upload_voice_sample_to_oss(self, clone_config, file_bytes, file_ext):
        try:
            import oss2
        except ImportError as exc:
            raise RuntimeError("缺少 oss2 依赖，请先安装 oss2") from exc

        missing = self._voice_clone_missing_config(clone_config)
        if missing:
            raise RuntimeError("缺少阿里云 CosyVoice/OSS 配置：" + "、".join(missing))

        oss_config = clone_config.get("oss") or {}
        endpoint = oss_config["endpoint"]
        if not endpoint.startswith(("http://", "https://")):
            endpoint = f"https://{endpoint}"
        object_key = "/".join(
            part.strip("/")
            for part in (
                oss_config.get("prefix") or "xiaozhi/cosyvoice",
                time.strftime("%Y%m%d"),
                f"sample-{uuid.uuid4().hex[:12]}.{file_ext}",
            )
            if part
        )
        content_type = mimetypes.types_map.get(f".{file_ext}", "audio/wav")
        auth = oss2.Auth(oss_config["access_key_id"], oss_config["access_key_secret"])
        bucket = oss2.Bucket(auth, endpoint, oss_config["bucket"])
        bucket.put_object(object_key, file_bytes, headers={"Content-Type": content_type})
        return bucket.sign_url("GET", object_key, int(oss_config.get("expires", 3600))), object_key

    async def _post_cosyvoice_customization(self, payload, require_oss=False):
        clone_config = self._voice_clone_config()
        missing = self._voice_clone_missing_config(clone_config, require_oss=require_oss)
        if missing:
            raise RuntimeError("缺少阿里云 CosyVoice/OSS 配置：" + "、".join(missing))
        headers = {
            "Authorization": f"Bearer {clone_config['api_key']}",
            "Content-Type": "application/json",
        }
        async with ClientSession() as session:
            async with session.post(
                "https://dashscope.aliyuncs.com/api/v1/services/audio/tts/customization",
                headers=headers,
                json=payload,
                timeout=60,
            ) as resp:
                try:
                    data = await resp.json()
                except Exception:
                    text = await resp.text()
                    data = {"message": text}
                if resp.status >= 400:
                    raise RuntimeError(data.get("message") or data.get("code") or f"阿里百炼接口 HTTP {resp.status}")
                return data

    # ── 摘要接口 ──

    async def handle_tts_speak(self, request):
        """POST /api/hospice/tts/speak body: {device_id, text}"""
        try:
            data = await request.json()
            device_id = (data.get("device_id") or "default").strip()
            text = (data.get("text") or "").strip()
            if not text:
                return web.json_response(
                    {"success": False, "error": "text required"},
                    status=400,
                    headers=self._cors_headers(),
                )

            conn = ConnectionHandler.get_active_connection(device_id)
            if conn is None:
                logger.bind(tag=TAG).warning(f"TTS播报找不到在线连接: device_id={device_id}")
                return web.json_response(
                    {"success": False, "error": "connection not ready"},
                    status=404,
                    headers=self._cors_headers(),
                )
            if not conn.speak_text_with_tts(text):
                logger.bind(tag=TAG).warning(f"TTS未就绪: device_id={device_id}")
                return web.json_response(
                    {"success": False, "error": "tts not ready"},
                    status=503,
                    headers=self._cors_headers(),
                )
            return web.json_response({"success": True}, headers=self._cors_headers())
        except Exception as e:
            logger.bind(tag=TAG).error(f"TTS播报失败: {e}")
            return web.json_response({"success": False, "error": str(e)}, status=500, headers=self._cors_headers())

    async def handle_tts_stop(self, request):
        """POST /api/hospice/tts/stop body: {device_id}"""
        try:
            data = await request.json()
            device_id = (data.get("device_id") or "default").strip()
            conn = ConnectionHandler.get_active_connection(device_id)
            if conn is None:
                return web.json_response(
                    {"success": False, "error": "connection not ready"},
                    status=404,
                    headers=self._cors_headers(),
                )
            asyncio.run_coroutine_threadsafe(handleAbortMessage(conn), conn.loop)
            return web.json_response({"success": True}, headers=self._cors_headers())
        except Exception as e:
            logger.bind(tag=TAG).error(f"停止TTS失败: {e}")
            return web.json_response({"success": False, "error": str(e)}, status=500, headers=self._cors_headers())

    async def handle_voice_clone_config(self, request):
        """GET /api/hospice/voice-clone/config?device_id=xxx"""
        device_id = request.query.get("device_id", "default")
        clone_config = self._voice_clone_config()
        settings = self._get_device_voice_settings(device_id)
        missing = self._voice_clone_missing_config(clone_config)
        return web.json_response(
            {
                "success": True,
                "provider": clone_config.get("provider"),
                "configured": not missing,
                "missing_config": missing,
                "model": clone_config.get("model"),
                "max_sample_mb": clone_config.get("max_sample_mb"),
                "language": clone_config.get("language"),
                "settings": settings,
            },
            headers=self._cors_headers(),
        )

    async def handle_voice_clone_train(self, request):
        """POST /api/hospice/voice-clone/train multipart: file, device_id, alias?, resource_id?"""
        try:
            clone_config = self._voice_clone_config()
            reader = await request.multipart()
            fields = {}
            file_bytes = None
            file_ext = ""
            max_bytes = clone_config.get("max_sample_mb", 10) * 1024 * 1024

            while True:
                field = await reader.next()
                if field is None:
                    break
                if field.name == "file":
                    filename = field.filename or ""
                    file_ext = os.path.splitext(filename)[1].lstrip(".").lower()
                    size = 0
                    chunks = []
                    while True:
                        chunk = await field.read_chunk(64 * 1024)
                        if not chunk:
                            break
                        size += len(chunk)
                        if size > max_bytes:
                            return web.json_response(
                                {"success": False, "error": f"样音最多 {clone_config.get('max_sample_mb', 10)}MB"},
                                status=413,
                                headers=self._cors_headers(),
                            )
                        chunks.append(chunk)
                    file_bytes = b"".join(chunks)
                else:
                    fields[field.name] = (await field.text()).strip()

            if not file_bytes:
                return web.json_response({"success": False, "error": "missing file"}, status=400, headers=self._cors_headers())

            device_id = fields.get("device_id") or "default"
            model = fields.get("model") or clone_config.get("model") or "cosyvoice-v3.5-flash"
            alias = fields.get("alias") or "家属音色"
            if file_ext not in ("wav", "mp3", "ogg", "m4a", "aac", "pcm"):
                return web.json_response(
                    {"success": False, "error": "声音复刻样音仅支持 wav、mp3、ogg、m4a、aac、pcm"},
                    status=400,
                    headers=self._cors_headers(),
                )

            audio_url, object_key = self._upload_voice_sample_to_oss(clone_config, file_bytes, file_ext)
            payload = {
                "model": "voice-enrollment",
                "input": {
                    "action": "create_voice",
                    "target_model": model,
                    "prefix": clone_config.get("prefix") or "hospice",
                    "url": audio_url,
                    "language_hints": [fields.get("language") or clone_config.get("language") or "zh"],
                    "max_prompt_audio_length": float(fields.get("max_prompt_audio_length") or clone_config.get("max_prompt_audio_length", 20.0)),
                    "enable_preprocess": str(fields.get("enable_preprocess") or clone_config.get("enable_preprocess", True)).lower() not in ("false", "0", "no"),
                },
            }
            result = await self._post_cosyvoice_customization(payload, require_oss=True)
            voice_id = ((result.get("output") or {}).get("voice_id") or "").strip()
            if not voice_id:
                raise RuntimeError("阿里百炼未返回 voice_id")
            settings = self._update_device_voice_settings(device_id, {
                "provider": "aliyun_cosyvoice",
                "voice_id": voice_id,
                "speaker_id": voice_id,
                "alias": alias,
                "model": model,
                "status": "DEPLOYING",
                "active": False,
                "oss_object_key": object_key,
                "instruction": clone_config.get("instruction"),
            })
            return web.json_response({"success": True, "settings": settings, "raw": result}, headers=self._cors_headers())

            payload = {
                "speaker_id": speaker_id,
                "appid": clone_config.get("appid"),
                "audios": [{
                    "audio_bytes": base64.b64encode(file_bytes).decode("ascii"),
                    "audio_format": file_ext,
                }],
                "source": clone_config.get("source", 2),
                "language": int(fields.get("language") or clone_config.get("language", 0)),
                "model_type": int(fields.get("model_type") or clone_config.get("model_type", 5)),
                "extra_params": json.dumps(clone_config.get("extra_params") or {}, ensure_ascii=False),
            }

            result = await self._post_voice_clone("/api/v3/tts/voice_clone", payload, resource_id)
            if result.get("BaseResp", {}).get("StatusCode", 0) not in (0, None):
                raise RuntimeError(result.get("BaseResp", {}).get("StatusMessage") or "训练提交失败")

            settings = self._update_device_voice_settings(device_id, {
                "speaker_id": result.get("speaker_id") or speaker_id,
                "alias": alias,
                "resource_id": resource_id,
                "status": "Training",
                "active": False,
            })
            return web.json_response({"success": True, "settings": settings, "raw": result}, headers=self._cors_headers())
        except Exception as e:
            logger.bind(tag=TAG).error(f"提交声音复刻失败: {e}")
            return web.json_response({"success": False, "error": str(e)}, status=500, headers=self._cors_headers())

    async def handle_voice_clone_status(self, request):
        """GET /api/hospice/voice-clone/status?device_id=xxx&speaker_id=S_xxx"""
        try:
            device_id = request.query.get("device_id", "default")
            existing = self._get_device_voice_settings(device_id)
            voice_id = self._safe_voice_id(request.query.get("voice_id") or request.query.get("speaker_id") or existing.get("voice_id") or existing.get("speaker_id"))
            clone_config = self._voice_clone_config()
            result = await self._post_cosyvoice_customization({
                "model": "voice-enrollment",
                "input": {
                    "action": "query_voice",
                    "voice_id": voice_id,
                },
            })
            output = result.get("output") or {}
            settings = self._update_device_voice_settings(device_id, {
                "provider": "aliyun_cosyvoice",
                "voice_id": voice_id,
                "speaker_id": voice_id,
                "model": output.get("target_model") or existing.get("model") or clone_config.get("model"),
                "status": output.get("status") or "UNKNOWN",
                "resource_link": output.get("resource_link"),
            })
            return web.json_response({"success": True, "settings": settings, "raw": result}, headers=self._cors_headers())
            resource_id = request.query.get("resource_id") or existing.get("resource_id") or clone_config.get("default_resource_id") or "seed-icl-2.0"
            result = await self._post_voice_clone(
                "/api/v3/tts/get_voice",
                {"speaker_id": speaker_id, "appid": clone_config.get("appid")},
                resource_id,
            )
            if result.get("BaseResp", {}).get("StatusCode", 0) not in (0, None):
                raise RuntimeError(result.get("BaseResp", {}).get("StatusMessage") or "查询失败")

            status_map = {0: "NotFound", 1: "Training", 2: "Success", 3: "Failed", 4: "Active"}
            raw_status = result.get("speaker_status", result.get("status"))
            settings = self._update_device_voice_settings(device_id, {
                "speaker_id": speaker_id,
                "resource_id": resource_id,
                "status": status_map.get(raw_status, str(raw_status)),
                "demo_audio": result.get("demo_audio"),
                "version": result.get("version"),
            })
            return web.json_response({"success": True, "settings": settings, "raw": result}, headers=self._cors_headers())
        except Exception as e:
            logger.bind(tag=TAG).error(f"查询声音复刻状态失败: {e}")
            return web.json_response({"success": False, "error": str(e)}, status=500, headers=self._cors_headers())

    async def handle_voice_clone_list(self, request):
        """GET /api/hospice/voice-clone/list?device_id=xxx"""
        try:
            device_id = request.query.get("device_id", "default")
            clone_config = self._voice_clone_config()
            input_data = {
                "action": "list_voice",
                "prefix": clone_config.get("prefix") or "hospice",
                "page_size": int(request.query.get("page_size", 50)),
                "page_index": int(request.query.get("page_index", 0)),
            }
            result = await self._post_cosyvoice_customization({
                "model": "voice-enrollment",
                "input": input_data,
            })
            output = result.get("output") or {}
            raw_items = (
                output.get("voices")
                or output.get("voice_list")
                or output.get("items")
                or output.get("data")
                or []
            )
            records = [
                record for record in (self._normalize_cosyvoice_record(item) for item in raw_items)
                if record
            ]
            settings = self._merge_device_voice_records(device_id, records)
            return web.json_response(
                {"success": True, "settings": settings, "raw": result},
                headers=self._cors_headers(),
            )
        except Exception as e:
            logger.bind(tag=TAG).error(f"拉取声音列表失败: {e}")
            return web.json_response({"success": False, "error": str(e)}, status=500, headers=self._cors_headers())

    async def handle_voice_clone_delete(self, request):
        """DELETE /api/hospice/voice-clone/delete?device_id=xxx&voice_id=yyy"""
        try:
            device_id = request.query.get("device_id", "default")
            voice_id = self._safe_voice_id(request.query.get("voice_id"))
            delete_result = await self._post_cosyvoice_customization({
                "model": "voice-enrollment",
                "input": {
                    "action": "delete_voice",
                    "voice_id": voice_id,
                },
            })
            removed, settings, fallback = self._remove_device_voice_record(device_id, voice_id)
            if fallback and settings.get("active") and settings.get("voice_id"):
                self._apply_active_voice_to_config(settings)
                await self._apply_voice_settings_to_active_connection(device_id, settings)
            elif not fallback:
                self._apply_active_voice_to_config({})
                await self._apply_voice_settings_to_active_connection(device_id, {})
            return web.json_response(
                {
                    "success": True,
                    "removed": removed,
                    "remote_deleted": True,
                    "settings": settings,
                    "fallback": fallback,
                    "raw": delete_result,
                },
                headers=self._cors_headers(),
            )
        except Exception as e:
            logger.bind(tag=TAG).error(f"删除声音记录失败: {e}")
            return web.json_response({"success": False, "error": str(e)}, status=500, headers=self._cors_headers())

    async def handle_voice_clone_activate(self, request):
        """POST /api/hospice/voice-clone/activate body: {device_id, speaker_id, resource_id, alias?}"""
        try:
            data = await request.json()
            device_id = data.get("device_id") or "default"
            voice_id = self._safe_voice_id(data.get("voice_id") or data.get("speaker_id"))
            clone_config = self._voice_clone_config()
            settings = self._update_device_voice_settings(device_id, {
                "provider": "aliyun_cosyvoice",
                "voice_id": voice_id,
                "speaker_id": voice_id,
                "alias": data.get("alias") or "家属音色",
                "model": data.get("model") or clone_config.get("model"),
                "instruction": data.get("instruction") or clone_config.get("instruction"),
                "active": True,
            })
            self._apply_active_voice_to_config(settings)
            applied_online = await self._apply_voice_settings_to_active_connection(device_id, settings)
            return web.json_response({"success": True, "settings": settings, "applied_online": applied_online}, headers=self._cors_headers())
            speaker_id = self._safe_speaker_id(data.get("speaker_id"))
            clone_config = self._voice_clone_config()
            resource_id = data.get("resource_id") or clone_config.get("default_resource_id") or "seed-icl-2.0"
            settings = self._update_device_voice_settings(device_id, {
                "speaker_id": speaker_id,
                "alias": data.get("alias") or "家属音色",
                "resource_id": resource_id,
                "active": True,
            })
            self._apply_active_voice_to_config(settings)
            return web.json_response({"success": True, "settings": settings}, headers=self._cors_headers())
        except Exception as e:
            return web.json_response({"success": False, "error": str(e)}, status=400, headers=self._cors_headers())

    async def handle_voice_clone_reset(self, request):
        """POST /api/hospice/voice-clone/reset body: {device_id}"""
        try:
            data = await request.json()
            device_id = data.get("device_id") or "default"
            settings = self._clear_active_voice_settings(device_id)
            self._apply_active_voice_to_config({})
            applied_online = await self._apply_voice_settings_to_active_connection(device_id, settings)
            return web.json_response(
                {"success": True, "settings": settings, "applied_online": applied_online},
                headers=self._cors_headers(),
            )
        except Exception as e:
            return web.json_response({"success": False, "error": str(e)}, status=400, headers=self._cors_headers())

