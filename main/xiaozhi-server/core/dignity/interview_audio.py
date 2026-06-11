from __future__ import annotations

import copy
import hashlib
import json
import re
import uuid
import wave
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List


SERVER_ROOT = Path(__file__).resolve().parents[2]
EDIT_DIR = SERVER_ROOT / "data" / "hospice_media" / "dignity_audio_edits" / "sources"
INTERVIEW_AUDIO_DIR = SERVER_ROOT / "data" / "hospice_media" / "dignity_interview_audio"
MEMORY_KEYS = ("life_story_materials", "important_relationships", "values_and_strengths", "messages_to_family")


def safe_patient_key(value: Any) -> str:
    key = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value or "")).strip("._")
    return key or "default_patient"


def latest_edit_path(patient_id: Any) -> Path:
    return EDIT_DIR / f"{safe_patient_key(patient_id)}_latest.json"


def load_audio_edit_record(patient_id: Any) -> Dict[str, Any]:
    path = latest_edit_path(patient_id)
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as file:
            value = json.load(file) or {}
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def load_audio_segments(patient_id: Any) -> List[Dict[str, Any]]:
    record = load_audio_edit_record(patient_id)
    segments = record.get("segments")
    return segments if isinstance(segments, list) else []


def save_audio_segments(patient_id: Any, segments: List[Dict[str, Any]]) -> Dict[str, Any]:
    EDIT_DIR.mkdir(parents=True, exist_ok=True)
    patient_key = safe_patient_key(patient_id)
    clean_segments = normalize_segments(segments)
    payload = {
        "patient_id": patient_key,
        "segments": clean_segments,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }
    with latest_edit_path(patient_key).open("w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)
    return payload


def save_pcm_audio_segment(
    patient_id: Any,
    pcm_frames: Any,
    sample_rate: int = 16000,
    channels: int = 1,
) -> Dict[str, Any]:
    if not isinstance(pcm_frames, list) or not pcm_frames:
        return {}
    patient_key = safe_patient_key(patient_id)
    target_dir = INTERVIEW_AUDIO_DIR / patient_key
    target_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{datetime.now():%Y%m%d_%H%M%S}_{uuid.uuid4().hex[:8]}.wav"
    path = target_dir / filename
    pcm_bytes = b"".join(bytes(frame) for frame in pcm_frames if frame)
    if not pcm_bytes:
        return {}
    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(channels)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm_bytes)
    duration = len(pcm_bytes) / max(1, sample_rate * channels * 2)
    return {
        "audio_url": f"/hospice-media/dignity_interview_audio/{patient_key}/{filename}",
        "duration": round(duration, 2),
    }


def merge_and_save_transcript_segments(patient_id: Any, transcript: Any) -> Dict[str, Any]:
    incoming = segments_from_transcript(transcript)
    if not incoming:
        return load_audio_edit_record(patient_id)
    current = load_audio_segments(patient_id)
    deleted_by_id = {str(item.get("id")): bool(item.get("deleted")) for item in current if isinstance(item, dict)}
    deleted_by_text = {
        _text_key(item.get("text")): bool(item.get("deleted"))
        for item in current
        if isinstance(item, dict) and item.get("text")
    }
    merged = []
    for segment in incoming:
        segment_id = str(segment.get("id") or "")
        text_key = _text_key(segment.get("text"))
        segment["deleted"] = deleted_by_id.get(segment_id, deleted_by_text.get(text_key, False))
        merged.append(segment)
    return save_audio_segments(patient_id, merged)


def normalize_segments(segments: Any) -> List[Dict[str, Any]]:
    clean = []
    if not isinstance(segments, list):
        return clean
    for index, item in enumerate(segments):
        if not isinstance(item, dict):
            continue
        text = _clean_text(item.get("text"))
        if not text:
            continue
        segment = {
            "id": _clean_id(item.get("id")) or segment_id(text, index),
            "text": text,
            "deleted": bool(item.get("deleted")),
        }
        for key in ("speaker", "audio_url"):
            value = _clean_text(item.get(key))
            if value:
                segment[key] = value
        for key in ("start_time", "end_time"):
            value = _float_or_none(item.get(key))
            if value is not None:
                segment[key] = value
        clean.append(segment)
    return clean


def segments_from_transcript(transcript: Any) -> List[Dict[str, Any]]:
    segments = []
    if not isinstance(transcript, list):
        return segments
    for index, turn in enumerate(transcript):
        if not isinstance(turn, dict):
            continue
        text = _clean_text(turn.get("patient") or turn.get("patient_text") or turn.get("text"))
        if not text:
            continue
        segment = {
            "id": _clean_id(turn.get("id")) or segment_id(text, index),
            "text": text,
            "speaker": _clean_text(turn.get("speaker")) or "patient",
            "deleted": bool(turn.get("deleted")),
        }
        for key in ("audio_url", "start_time", "end_time"):
            if turn.get(key) is not None:
                segment[key] = turn.get(key)
        segments.append(segment)
    return normalize_segments(segments)


def apply_audio_edits_to_transcript(patient_id: Any, transcript: Any) -> List[Dict[str, Any]]:
    deleted_ids, deleted_texts = deleted_segment_keys(patient_id)
    result = []
    for index, turn in enumerate(transcript if isinstance(transcript, list) else []):
        if not isinstance(turn, dict):
            continue
        text = _clean_text(turn.get("patient") or turn.get("patient_text") or turn.get("text"))
        turn_id = _clean_id(turn.get("id")) or segment_id(text, index)
        if turn_id in deleted_ids or _text_key(text) in deleted_texts:
            continue
        result.append(turn)
    return result


def apply_audio_edits_to_memory(patient_id: Any, memory: Any) -> Dict[str, List[Any]]:
    if not isinstance(memory, dict):
        return {}
    deleted_ids, deleted_texts = deleted_segment_keys(patient_id)
    if not deleted_ids and not deleted_texts:
        return copy.deepcopy(memory)
    deleted_values = [text for text in deleted_texts if text]
    filtered: Dict[str, List[Any]] = {}
    for key, items in memory.items():
        if key not in MEMORY_KEYS or not isinstance(items, list):
            continue
        kept = []
        for item in items:
            item_key = _text_key(_item_text(item))
            if not _matches_deleted_text(item_key, deleted_values):
                kept.append(item)
        filtered[key] = kept
    return filtered


def deleted_segment_keys(patient_id: Any) -> tuple[set[str], set[str]]:
    deleted_ids: set[str] = set()
    deleted_texts: set[str] = set()
    for segment in load_audio_segments(patient_id):
        if not isinstance(segment, dict) or not segment.get("deleted"):
            continue
        segment_id_value = _clean_id(segment.get("id"))
        if segment_id_value:
            deleted_ids.add(segment_id_value)
        text_key = _text_key(segment.get("text"))
        if text_key:
            deleted_texts.add(text_key)
    return deleted_ids, deleted_texts


def segment_id(text: Any, index: int = 0) -> str:
    digest = hashlib.sha1(_clean_text(text).encode("utf-8")).hexdigest()[:12]
    return f"seg_{index + 1:03d}_{digest}"


def _matches_deleted_text(item_key: str, deleted_values: List[str]) -> bool:
    if not item_key:
        return False
    for deleted in deleted_values:
        if not deleted:
            continue
        shorter, longer = sorted((item_key, deleted), key=len)
        if len(shorter) >= 12 and shorter in longer:
            return True
        if len(shorter) >= 18:
            overlap = len(set(shorter) & set(longer)) / max(1, len(set(shorter)))
            if overlap >= 0.9:
                return True
    return False


def _item_text(item: Any) -> str:
    if isinstance(item, str):
        return item
    if isinstance(item, dict):
        return " ".join(str(value or "") for value in item.values())
    return str(item or "")


def _clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _clean_id(value: Any) -> str:
    return re.sub(r"[^A-Za-z0-9_.:-]+", "_", str(value or "")).strip("._:-")


def _text_key(value: Any) -> str:
    return re.sub(r"[\s,.，。；;：:、!?！？'\"“”‘’（）()《》<>]+", "", _clean_text(value))


def _float_or_none(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None
