"""
安宁疗护 - 家属端 / 患者端 REST API
"""
import asyncio
import json
import mimetypes
import os
import re
import time
import uuid
import yaml
from aiohttp import ClientSession, web
from config.logger import setup_logging
from core.connection import ConnectionHandler
from core.handle.abortHandle import handleAbortMessage
from core.api.hospice.storage import get_session_logger

TAG = __name__
logger = setup_logging()


class MessageBroker:
    """简单的内存消息广播：device_id -> set(asyncio.Queue)
    每条新消息 put 给该 device_id 下所有订阅者（患者端、家属端各自订阅）。
    """

    def __init__(self):
        self._subs: dict[str, set[asyncio.Queue]] = {}

    def subscribe(self, device_id: str) -> asyncio.Queue:
        q = asyncio.Queue()
        self._subs.setdefault(device_id, set()).add(q)
        return q

    def unsubscribe(self, device_id: str, q: asyncio.Queue):
        if device_id in self._subs:
            self._subs[device_id].discard(q)
            if not self._subs[device_id]:
                self._subs.pop(device_id, None)

    def publish(self, device_id: str, event: dict):
        for q in list(self._subs.get(device_id, ())):
            try:
                q.put_nowait(event)
            except Exception:
                pass


class HospiceFamilyHandler:
    """家属端 / 患者端 API"""

    def __init__(self, config: dict):
        self.config = config
        self.session_logger = get_session_logger(config)
        self.broker = MessageBroker()
        self.upload_dir = os.path.join("data", "hospice_media")
        self.voice_settings_path = os.path.join("data", "hospice_voice_settings.yaml")
        os.makedirs(self.upload_dir, exist_ok=True)
        # 通话信令房间：device_id -> { 'family': ws, 'patient': ws }
        self.call_rooms: dict[str, dict[str, web.WebSocketResponse]] = {}

    def _cors_headers(self):
        return {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS, DELETE",
            "Access-Control-Allow-Headers": "Content-Type",
        }

    async def handle_options(self, request):
        return web.Response(status=200, headers=self._cors_headers())

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

    def _apply_active_voice_to_config(self, voice_settings):
        voice_id = voice_settings.get("voice_id") or voice_settings.get("speaker_id")
        selected = (self.config.get("selected_module") or {}).get("TTS")
        if not selected:
            return
        tts_config = (self.config.get("TTS") or {}).get(selected)
        if not isinstance(tts_config, dict):
            return
        if tts_config.get("type") == "alibl_stream":
            if not voice_id:
                tts_config.pop("private_voice", None)
                tts_config.pop("instruction", None)
                return
            tts_config["private_voice"] = voice_id
            if voice_settings.get("model"):
                tts_config["model"] = voice_settings["model"]
            if voice_settings.get("instruction"):
                tts_config["instruction"] = voice_settings["instruction"]

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

    async def handle_summary_today(self, request):
        device_id = request.query.get("device_id", "default")
        summary = self.session_logger.get_summary_today(device_id)

        if not summary:
            conversations = self.session_logger.get_today_conversations(device_id)
            emotions = self.session_logger.get_today_emotions(device_id)

            patient_msgs = [c for c in conversations if c["role"] == "patient"]

            mood_counts = {}
            for e in emotions:
                mood = e["emotion_mood"]
                mood_counts[mood] = mood_counts.get(mood, 0) + 1

            summary = {
                "date": __import__("datetime").date.today().isoformat(),
                "device_id": device_id,
                "conversation_count": len(conversations),
                "patient_message_count": len(patient_msgs),
                "dominant_mood": max(mood_counts, key=mood_counts.get) if mood_counts else "无数据",
                "mood_distribution": mood_counts,
                "summary": f"今日共进行了 {len(patient_msgs)} 轮对话。" if patient_msgs else "今日暂无对话记录。",
            }

        return web.json_response(summary, headers=self._cors_headers())

    async def handle_summary_history(self, request):
        device_id = request.query.get("device_id", "default")
        limit = int(request.query.get("limit", "30"))
        history = self.session_logger.get_summary_history(device_id, limit)
        return web.json_response(history, headers=self._cors_headers())

    # ── 情绪接口 ──

    async def handle_emotion_today(self, request):
        device_id = request.query.get("device_id", "default")
        emotions = self.session_logger.get_today_emotions(device_id)
        return web.json_response(emotions, headers=self._cors_headers())

    async def handle_emotion_trend(self, request):
        device_id = request.query.get("device_id", "default")
        days = int(request.query.get("days", "7"))
        trend = self.session_logger.get_emotion_trend(device_id, days)
        return web.json_response(trend, headers=self._cors_headers())

    # ── 消息接口 ──

    async def handle_send_message(self, request):
        """POST /api/hospice/message
        body: {device_id, sender_name, sender_role('family'|'patient'), type, content, duration_ms?}
        """
        try:
            data = await request.json()
            device_id = data.get("device_id", "default")
            sender_name = data.get("sender_name", "家属")
            sender_role = data.get("sender_role", "family")
            msg_type = data.get("type", "text")
            content = data.get("content", "")
            duration_ms = data.get("duration_ms")
            file_path = data.get("file_path")
            contact_name = data.get("contact_name")

            row = self.session_logger.save_family_message(
                device_id=device_id,
                sender_name=sender_name,
                message_type=msg_type,
                content=content,
                file_path=file_path,
                sender_role=sender_role,
                duration_ms=duration_ms,
                contact_name=contact_name,
            )

            if row:
                self.broker.publish(device_id, {"event": "message.new", "data": row})

            return web.json_response(
                {"success": True, "message": row},
                headers=self._cors_headers()
            )
        except Exception as e:
            logger.bind(tag=TAG).error(f"发送消息失败: {e}")
            return web.json_response(
                {"success": False, "error": str(e)},
                status=500,
                headers=self._cors_headers()
            )

    async def handle_get_messages(self, request):
        """GET /api/hospice/messages?device_id=xxx&sender_role=family|patient&contact_name=xxx"""
        device_id = request.query.get("device_id", "default")
        limit = int(request.query.get("limit", "50"))
        sender_role = request.query.get("sender_role")
        contact_name = request.query.get("contact_name")
        messages = self.session_logger.get_family_messages(
            device_id, limit, sender_role, contact_name
        )
        return web.json_response(messages, headers=self._cors_headers())

    async def handle_client_config(self, request):
        """GET /api/hospice/config  返回前端需要知道的配置（目前：上传上限）"""
        max_mb = int((self.config.get("hospice", {}) or {}).get("upload_max_mb", 50))
        return web.json_response({"upload_max_mb": max_mb}, headers=self._cors_headers())

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
            elif not fallback:
                self._apply_active_voice_to_config({})
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
            return web.json_response({"success": True, "settings": settings}, headers=self._cors_headers())
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

    async def handle_get_contacts(self, request):
        """GET /api/hospice/contacts?device_id=xxx
        返回按 contact_name 聚合的联系人列表（含最后一条消息与未读数）。
        """
        device_id = request.query.get("device_id", "default")
        contacts = self.session_logger.get_contacts(device_id)
        return web.json_response(contacts, headers=self._cors_headers())

    async def handle_mark_thread_read(self, request):
        """POST /api/hospice/thread/read?device_id=xxx&contact_name=xxx"""
        try:
            device_id = request.query.get("device_id", "default")
            contact_name = request.query.get("contact_name")
            if not contact_name:
                return web.json_response({"success": False, "error": "contact_name required"},
                                         status=400, headers=self._cors_headers())
            n = self.session_logger.mark_thread_read(device_id, contact_name)
            if n > 0:
                self.broker.publish(device_id, {
                    "event": "message.read",
                    "data": {"contact_name": contact_name, "count": n},
                })
            return web.json_response({"success": True, "count": n}, headers=self._cors_headers())
        except Exception as e:
            return web.json_response({"success": False, "error": str(e)},
                                     status=500, headers=self._cors_headers())

    async def handle_mark_read(self, request):
        """POST /api/hospice/message/{id}/read"""
        try:
            msg_id = int(request.match_info["id"])
            ok = self.session_logger.mark_message_read(msg_id)
            # 广播一条已读通知，对侧可更新 UI
            device_id = request.query.get("device_id")
            if ok and device_id:
                self.broker.publish(device_id, {"event": "message.read", "data": {"id": msg_id}})
            return web.json_response({"success": ok}, headers=self._cors_headers())
        except Exception as e:
            return web.json_response({"success": False, "error": str(e)},
                                     status=400, headers=self._cors_headers())

    async def handle_message_stream(self, request):
        """GET /api/hospice/message/stream?device_id=xxx  (SSE)"""
        device_id = request.query.get("device_id", "default")
        resp = web.StreamResponse(
            status=200,
            reason="OK",
            headers={
                "Content-Type": "text/event-stream",
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
                **self._cors_headers(),
            },
        )
        await resp.prepare(request)

        q = self.broker.subscribe(device_id)
        try:
            # 首帧：握手
            await resp.write(b": connected\n\n")
            while True:
                try:
                    event = await asyncio.wait_for(q.get(), timeout=25.0)
                    payload = f"event: {event['event']}\ndata: {json.dumps(event['data'], ensure_ascii=False, default=str)}\n\n"
                    await resp.write(payload.encode("utf-8"))
                except asyncio.TimeoutError:
                    await resp.write(b": ping\n\n")  # keepalive
        except (asyncio.CancelledError, ConnectionResetError):
            pass
        finally:
            self.broker.unsubscribe(device_id, q)
        return resp

    # ── 文件上传接口 ──

    async def handle_upload(self, request):
        """POST /api/hospice/upload  multipart: field 'file'
        返回: { url, file_name, size, duration_ms? }
        保存到 data/hospice_media/，URL 通过 /hospice-media/ 静态路由对外暴露。
        """
        try:
            reader = await request.multipart()
            field = await reader.next()
            if field is None or field.name != "file":
                return web.json_response({"success": False, "error": "missing file field"},
                                         status=400, headers=self._cors_headers())

            # 文件扩展名（从 content-type 或 filename 推断）
            filename = field.filename or ""
            ext = os.path.splitext(filename)[1].lower()
            if not ext:
                ct = (field.headers.get("Content-Type") or "").lower()
                ext = {
                    "audio/webm": ".webm", "audio/ogg": ".ogg", "audio/mpeg": ".mp3",
                    "audio/wav": ".wav", "audio/mp4": ".m4a",
                    "image/jpeg": ".jpg", "image/png": ".png", "image/gif": ".gif",
                    "image/webp": ".webp",
                    "video/mp4": ".mp4", "video/webm": ".webm", "video/quicktime": ".mov",
                    "video/x-matroska": ".mkv", "video/ogg": ".ogv", "video/3gpp": ".3gp",
                }.get(ct.split(";")[0].strip(), ".bin")

            # 大小上限（家属端 / 患者端发送媒体）
            max_mb = int((self.config.get("hospice", {}) or {}).get("upload_max_mb", 50))
            max_bytes = max_mb * 1024 * 1024

            # 时间戳 + 短 uuid 防撞
            ts = time.strftime("%Y%m%d-%H%M%S")
            safe_name = f"{ts}-{uuid.uuid4().hex[:8]}{ext}"
            save_path = os.path.join(self.upload_dir, safe_name)

            size = 0
            too_big = False
            with open(save_path, "wb") as f:
                while True:
                    chunk = await field.read_chunk(64 * 1024)
                    if not chunk:
                        break
                    size += len(chunk)
                    if size > max_bytes:
                        too_big = True
                        break
                    f.write(chunk)

            if too_big:
                try:
                    os.remove(save_path)
                except OSError:
                    pass
                return web.json_response(
                    {"success": False, "error": f"文件过大，最多 {max_mb}MB"},
                    status=413, headers=self._cors_headers(),
                )

            url = f"/hospice-media/{safe_name}"
            logger.bind(tag=TAG).info(f"媒体上传完成: {safe_name} ({size} bytes)")
            return web.json_response(
                {"success": True, "url": url, "file_name": safe_name, "size": size},
                headers=self._cors_headers(),
            )
        except Exception as e:
            logger.bind(tag=TAG).error(f"上传失败: {e}")
            return web.json_response({"success": False, "error": str(e)},
                                     status=500, headers=self._cors_headers())

    # ── 通话信令（WebRTC） ──

    async def handle_call_ws(self, request):
        """GET /api/hospice/call/ws?device_id=xxx&role=family|patient

        纯信令中继：把同一 device_id 房间里一端发来的消息原样转给另一端。
        支持的 type（客户端自定义，服务端不解析业务）：
          call-request / call-accept / call-reject / call-end
          offer / answer / ice
        """
        device_id = request.query.get("device_id", "default")
        role = request.query.get("role", "")
        if role not in ("family", "patient"):
            return web.Response(status=400, text="role must be family or patient")

        ws = web.WebSocketResponse(heartbeat=20)
        await ws.prepare(request)

        room = self.call_rooms.setdefault(device_id, {})
        # 若同角色已有连接，踢掉旧的
        # 用 close code 4001 标记"被新连接顶替"，客户端据此判断不重连
        # （关闭码比 message 帧更可靠——不会被浏览器事件循环顺序搞乱）
        old = room.get(role)
        if old is not None and not old.closed:
            try:
                await old.close(code=4001, message=b"replaced-by-new")
            except Exception:
                pass
        room[role] = ws

        peer_role = "patient" if role == "family" else "family"
        logger.bind(tag=TAG).info(f"通话信令连接: device={device_id} role={role}")

        try:
            async for msg in ws:
                if msg.type == web.WSMsgType.TEXT:
                    peer = self.call_rooms.get(device_id, {}).get(peer_role)
                    if peer is not None and not peer.closed:
                        try:
                            await peer.send_str(msg.data)
                        except Exception as e:
                            logger.bind(tag=TAG).warning(f"转发信令失败: {e}")
                    else:
                        # 对端不在，返回一个占位提示（避免一端死等）
                        try:
                            await ws.send_str(json.dumps({
                                "type": "peer-absent",
                                "peer_role": peer_role,
                            }))
                        except Exception:
                            pass
                elif msg.type == web.WSMsgType.ERROR:
                    logger.bind(tag=TAG).warning(f"ws error: {ws.exception()}")
                    break
        finally:
            # 清理，并通知对端
            if self.call_rooms.get(device_id, {}).get(role) is ws:
                self.call_rooms[device_id].pop(role, None)
                if not self.call_rooms[device_id]:
                    self.call_rooms.pop(device_id, None)
            peer = self.call_rooms.get(device_id, {}).get(peer_role)
            if peer is not None and not peer.closed:
                try:
                    await peer.send_str(json.dumps({"type": "call-end", "reason": "peer-disconnect"}))
                except Exception:
                    pass
            logger.bind(tag=TAG).info(f"通话信令断开: device={device_id} role={role}")
        return ws

    # ── 对话记录接口 ──

    async def handle_conversations_today(self, request):
        device_id = request.query.get("device_id", "default")
        conversations = self.session_logger.get_today_conversations(device_id)
        return web.json_response(conversations, headers=self._cors_headers())


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
        web.options("/api/hospice/{path:.*}", handler.handle_options),
    ]

    app.add_routes(routes)
    logger.bind(tag=TAG).info(f"安宁疗护 API 路由已注册 ({len(routes)} 条)")
