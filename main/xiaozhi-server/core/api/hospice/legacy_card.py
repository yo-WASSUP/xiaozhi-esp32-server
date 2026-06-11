"""Legacy story card endpoints for the hospice API."""
from __future__ import annotations

import base64
import copy
import json
import re
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from aiohttp import web
from config.logger import setup_logging
from core.dignity.engine.prompts import (
    FAMILY_LETTER_SYSTEM_PROMPT,
    LEGACY_STORY_CARD_SYSTEM_PROMPT,
    build_family_letter_user_prompt,
    build_legacy_story_card_user_prompt,
)
from core.dignity.interview_audio import apply_audio_edits_to_memory

TAG = __name__
logger = setup_logging()

CARD_WIDTH = 1080
CARD_PADDING = 72
CARD_MIN_HEIGHT = 1680
CARD_BG = (255, 248, 238)
INK = (42, 35, 28)
INK_MID = (82, 72, 62)
INK_FAINT = (122, 105, 86)
AMBER = (172, 116, 46)
SAGE = (112, 137, 116)
MIST = (218, 205, 184)

LETTER_TEMPLATES = {
    "warm": {
        "name": "暖黄信笺",
        "style": "warm",
        "asset": "warm.png",
        "bg_top": (248, 235, 206),
        "bg_bottom": (228, 210, 176),
        "accent": (154, 124, 82),
        "soft": (232, 214, 182),
        "ink": INK,
        "ink_mid": INK_MID,
        "ink_faint": INK_FAINT,
    },
    "floral": {
        "name": "花影信笺",
        "style": "floral",
        "asset": "floral.png",
        "bg_top": (255, 240, 236),
        "bg_bottom": (238, 218, 220),
        "accent": (166, 100, 110),
        "soft": (244, 204, 210),
        "ink": (58, 38, 42),
        "ink_mid": (104, 74, 78),
        "ink_faint": (142, 96, 102),
    },
    "bamboo": {
        "name": "青竹信笺",
        "style": "bamboo",
        "asset": "bamboo.png",
        "bg_top": (238, 245, 232),
        "bg_bottom": (215, 229, 207),
        "accent": (88, 132, 98),
        "soft": (196, 218, 188),
        "ink": (32, 48, 34),
        "ink_mid": (66, 92, 68),
        "ink_faint": (98, 126, 100),
    },
    "sky": {
        "name": "晴空信笺",
        "style": "sky",
        "asset": "sky.png",
        "bg_top": (235, 244, 252),
        "bg_bottom": (211, 227, 240),
        "accent": (82, 126, 160),
        "soft": (196, 218, 236),
        "ink": (30, 44, 56),
        "ink_mid": (62, 84, 102),
        "ink_faint": (92, 116, 136),
    },
    "plain": {
        "name": "素白信笺",
        "style": "plain",
        "asset": "plain.png",
        "bg_top": (255, 252, 244),
        "bg_bottom": (242, 236, 224),
        "accent": (128, 116, 98),
        "soft": (230, 224, 214),
        "ink": INK,
        "ink_mid": INK_MID,
        "ink_faint": INK_FAINT,
    },
}


class HospiceLegacyCardMixin:
    async def handle_legacy_card_latest(self, request):
        """GET /api/hospice/legacy-card/latest?device_id=xxx."""
        try:
            device_id = (request.query.get("device_id") or "default").strip() or "default"
            server_root = Path(__file__).resolve().parents[3]
            payload = _load_latest_artifact(server_root, "dignity_legacy_cards", device_id)
            return web.json_response(
                {"success": True, **payload},
                headers=self._cors_headers(),
            )
        except Exception as exc:
            logger.bind(tag=TAG).error(f"传承故事卡片读取失败: {exc}")
            return web.json_response(
                {"success": False, "error": str(exc)},
                status=500,
                headers=self._cors_headers(),
            )

    async def handle_legacy_card_render(self, request):
        """POST /api/hospice/legacy-card/render body: {device_id, memory?, card?}."""
        try:
            data = await request.json()
            device_id = (data.get("device_id") or "default").strip() or "default"
            memory = data.get("memory") or {}
            card_input = data.get("card") if isinstance(data.get("card"), dict) else None
            if not card_input:
                memory = apply_audio_edits_to_memory(device_id, memory)
            if not card_input and not _has_memory(memory):
                return web.json_response(
                    {"success": False, "error": "还没有可生成传承故事卡片的访谈记忆。"},
                    status=400,
                    headers=self._cors_headers(),
                )

            server_root = Path(__file__).resolve().parents[3]
            card = _clean_card_payload(card_input) if card_input else _generate_card_payload(memory, self.config)
            image_url = _render_card_image(server_root, device_id, card, self.config)
            _save_latest_artifact(server_root, "dignity_legacy_cards", device_id, {
                "card": card,
                "image_url": image_url,
            })
            return web.json_response(
                {"success": True, "card": card, "image_url": image_url},
                headers=self._cors_headers(),
            )
        except Exception as exc:
            logger.bind(tag=TAG).error(f"传承故事卡片生成失败: {exc}")
            return web.json_response(
                {"success": False, "error": str(exc)},
                status=500,
                headers=self._cors_headers(),
            )

    async def handle_family_letter_latest(self, request):
        """GET /api/hospice/family-letter/latest?device_id=xxx."""
        try:
            device_id = (request.query.get("device_id") or "default").strip() or "default"
            server_root = Path(__file__).resolve().parents[3]
            payload = _load_latest_artifact(server_root, "dignity_family_letters", device_id)
            return web.json_response(
                {"success": True, **payload},
                headers=self._cors_headers(),
            )
        except Exception as exc:
            logger.bind(tag=TAG).error(f"家信读取失败: {exc}")
            return web.json_response(
                {"success": False, "error": str(exc)},
                status=500,
                headers=self._cors_headers(),
            )

    async def handle_family_letter_render(self, request):
        """POST /api/hospice/family-letter/render body: {device_id, memory?, template?, letter?}."""
        try:
            data = await request.json()
            device_id = (data.get("device_id") or "default").strip() or "default"
            memory = data.get("memory") or {}
            template = _letter_template_key(data.get("template"))
            letter_input = data.get("letter") if isinstance(data.get("letter"), dict) else None
            if not letter_input:
                memory = apply_audio_edits_to_memory(device_id, memory)
            if not letter_input and not _has_memory(memory):
                return web.json_response(
                    {"success": False, "error": "还没有可生成家信的访谈记忆。"},
                    status=400,
                    headers=self._cors_headers(),
                )

            server_root = Path(__file__).resolve().parents[3]
            letter = _clean_family_letter_payload(letter_input) if letter_input else _generate_family_letter_payload(memory, self.config)
            image_url = _render_family_letter_image(server_root, device_id, letter, template)
            _save_latest_artifact(server_root, "dignity_family_letters", device_id, {
                "letter": letter,
                "image_url": image_url,
                "template": template,
                "template_name": LETTER_TEMPLATES[template]["name"],
            })
            return web.json_response(
                {
                    "success": True,
                    "letter": letter,
                    "image_url": image_url,
                    "template": template,
                    "template_name": LETTER_TEMPLATES[template]["name"],
                },
                headers=self._cors_headers(),
            )
        except Exception as exc:
            logger.bind(tag=TAG).error(f"家信生成失败: {exc}")
            return web.json_response(
                {"success": False, "error": str(exc)},
                status=500,
                headers=self._cors_headers(),
            )


def _generate_card_payload(memory: Dict[str, Any], config: dict) -> Dict[str, Any]:
    try:
        provider = _create_llm_provider(config)
        if provider:
            content = provider.response_no_stream(
                LEGACY_STORY_CARD_SYSTEM_PROMPT,
                build_legacy_story_card_user_prompt(memory),
                temperature=0.2,
                max_tokens=2600,
            )
            parsed = _parse_json_object(content)
            if parsed:
                return _normalize_card(parsed, memory)
    except Exception as exc:
        logger.bind(tag=TAG).warning(f"传承故事文案生成失败，使用本地兜底: {exc}")
    return _fallback_card(memory)


def _generate_family_letter_payload(memory: Dict[str, Any], config: dict) -> Dict[str, Any]:
    generated_date = _today_text()
    try:
        provider = _create_llm_provider(config)
        if provider:
            content = provider.response_no_stream(
                FAMILY_LETTER_SYSTEM_PROMPT,
                build_family_letter_user_prompt(memory, generated_date),
                temperature=0.2,
                max_tokens=3200,
            )
            parsed = _parse_json_object(content)
            if parsed:
                return _normalize_family_letter(parsed, memory, generated_date)
    except Exception as exc:
        logger.bind(tag=TAG).warning(f"家信文案生成失败，使用本地兜底: {exc}")
    return _fallback_family_letter(memory, generated_date)


def _create_llm_provider(config: Dict[str, Any]):
    selected = (config.get("selected_module") or {}).get("LLM")
    if not selected:
        return None
    module_config = (config.get("LLM") or {}).get(selected)
    if not isinstance(module_config, dict):
        return None
    from core.utils import llm

    safe_config = copy.deepcopy(module_config)
    provider_type = safe_config.get("type") or selected
    return llm.create_instance(provider_type, safe_config)


def _parse_json_object(content: str) -> Dict[str, Any]:
    text = (content or "").strip()
    if not text:
        return {}
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        extracted = _extract_json(text)
        if not extracted:
            return {}
        value = json.loads(extracted)
    return value if isinstance(value, dict) else {}


def _extract_json(text: str) -> str:
    start = text.find("{")
    if start < 0:
        return ""
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start:index + 1]
    return ""


def _normalize_card(card: Dict[str, Any], memory: Dict[str, Any]) -> Dict[str, Any]:
    subject = _subject_from_card(card) or _subject_from_memory(memory)
    title = _clean_text(card.get("title")) or f"{subject}的传承故事"
    if "传承故事" not in title:
        title = f"{title}的传承故事" if not title.endswith("的故事") else title.replace("的故事", "的传承故事")
    subtitle = _clean_text(card.get("subtitle")) or "基于尊严疗法访谈形成的生命回顾与心愿传承"
    intro = _trim(_clean_text(card.get("intro")), 180)
    sections = []
    for index, raw in enumerate(card.get("sections") or []):
        if not isinstance(raw, dict):
            continue
        title_text = _trim(_clean_text(raw.get("title")), 18)
        body = _trim(_clean_text(raw.get("body")), 180)
        quote = _trim(_clean_quote(raw.get("quote")), 44)
        if not title_text or not body:
            continue
        sections.append({
            "number": f"{len(sections) + 1:02d}",
            "title": title_text,
            "body": body,
            "quote": quote,
        })
        if len(sections) >= 6:
            break
    if len(sections) < 3:
        return _fallback_card(memory)
    wish = _trim(_clean_text(card.get("wish")), 140)
    closing = _clean_text(card.get("closing")) or f"——谨以此记录{subject}的人生故事与心愿"
    return {
        "title": _privacy_filter(title),
        "subtitle": subtitle,
        "intro": _privacy_filter(intro),
        "sections": [
            {
                "number": item["number"],
                "title": _privacy_filter(item["title"]),
                "body": _privacy_filter(item["body"]),
                "quote": _privacy_filter(item["quote"]),
            }
            for item in sections
        ],
        "wish": _privacy_filter(wish),
        "closing": _privacy_filter(closing),
    }


def _clean_card_payload(card: Dict[str, Any]) -> Dict[str, Any]:
    title = _clean_text(card.get("title")) or "传承故事图文卡片"
    subtitle = _clean_text(card.get("subtitle")) or "基于尊严疗法访谈形成的生命回顾与心愿传承"
    intro = _trim(_clean_text(card.get("intro")), 220)
    sections = []
    for raw in card.get("sections") or []:
        if not isinstance(raw, dict):
            continue
        title_text = _trim(_clean_text(raw.get("title")), 24)
        body = _trim(_clean_text(raw.get("body")), 220)
        quote = _trim(_clean_quote(raw.get("quote")), 60)
        if not title_text and not body and not quote:
            continue
        sections.append({
            "number": f"{len(sections) + 1:02d}",
            "title": title_text or f"片段{len(sections) + 1}",
            "body": body,
            "quote": quote,
        })
        if len(sections) >= 8:
            break
    if not sections:
        sections.append({
            "number": "01",
            "title": "人生故事",
            "body": "这里记录了一段值得被记住的生命记忆。",
            "quote": "",
        })
    return {
        "title": _privacy_filter(title),
        "subtitle": _privacy_filter(subtitle),
        "intro": _privacy_filter(intro),
        "sections": [
            {
                "number": item["number"],
                "title": _privacy_filter(item["title"]),
                "body": _privacy_filter(item["body"]),
                "quote": _privacy_filter(item["quote"]),
            }
            for item in sections
        ],
        "wish": _privacy_filter(_trim(_clean_text(card.get("wish")), 180)),
        "closing": _privacy_filter(_clean_text(card.get("closing")) or "——谨以此记录人生故事与心愿"),
    }


def _fallback_card(memory: Dict[str, Any]) -> Dict[str, Any]:
    subject = _subject_from_memory(memory)
    sections = []
    candidates = [
        ("人生经历", memory.get("life_story_materials") or []),
        ("家人之间", memory.get("important_relationships") or []),
        ("珍视与力量", memory.get("values_and_strengths") or []),
        ("留给家人的话", memory.get("messages_to_family") or []),
    ]
    for title, items in candidates:
        text = _first_item_text(items)
        if not text:
            continue
        sections.append({
            "number": f"{len(sections) + 1:02d}",
            "title": title,
            "body": _privacy_filter(_trim(text, 160)),
            "quote": _privacy_filter(_trim(text, 42)),
        })
    if not sections:
        sections.append({
            "number": "01",
            "title": "人生故事",
            "body": "这些访谈记忆记录了患者珍视的人生经历、家人关系和想留下的话。",
            "quote": "健康第一，好好生活。",
        })
    return {
        "title": f"{subject}的传承故事",
        "subtitle": "基于尊严疗法访谈形成的生命回顾与心愿传承",
        "intro": _privacy_filter(_intro_from_sections(sections)),
        "sections": sections[:6],
        "wish": "",
        "closing": f"——谨以此记录{subject}的人生故事与心愿",
    }


def _normalize_family_letter(letter: Dict[str, Any], memory: Dict[str, Any], generated_date: str) -> Dict[str, Any]:
    subject = _subject_from_letter(letter) or _subject_from_memory(memory)
    title = _clean_text(letter.get("title")) or "写给家人的一封信"
    subtitle = _clean_text(letter.get("subtitle")) or f"——{subject}的心里话"
    salutation = _clean_text(letter.get("salutation")) or _salutation_from_memory(memory)
    paragraphs = []
    for item in letter.get("paragraphs") or []:
        text = _privacy_filter(_clean_text(item))
        if text:
            paragraphs.append(text)
    if not paragraphs:
        return _fallback_family_letter(memory, generated_date)
    paragraphs = _expand_letter_paragraphs(paragraphs, memory, min_chars=400)
    signature = _clean_text(letter.get("signature")) or f"爱你们的{subject}"
    if not signature.startswith("爱你们的"):
        signature = f"爱你们的{subject}"
    date = _clean_text(letter.get("date")) or generated_date
    return {
        "title": _privacy_filter(title),
        "subtitle": _privacy_filter(subtitle),
        "salutation": _privacy_filter(salutation),
        "paragraphs": [_privacy_filter(item) for item in paragraphs],
        "signature": _privacy_filter(signature),
        "date": date,
    }


def _clean_family_letter_payload(letter: Dict[str, Any]) -> Dict[str, Any]:
    paragraphs = []
    for item in letter.get("paragraphs") or []:
        text = _privacy_filter(_clean_text(item))
        if text:
            paragraphs.append(text)
    if not paragraphs:
        paragraphs = ["这些话，想留给我最牵挂的家人。"]
    return {
        "title": _privacy_filter(_clean_text(letter.get("title")) or "写给家人的一封信"),
        "subtitle": _privacy_filter(_clean_text(letter.get("subtitle"))),
        "salutation": _privacy_filter(_clean_text(letter.get("salutation")) or "亲爱的家人："),
        "paragraphs": paragraphs[:10],
        "signature": _privacy_filter(_clean_text(letter.get("signature")) or "爱你们的我"),
        "date": _clean_text(letter.get("date")) or _today_text(),
    }


def _fallback_family_letter(memory: Dict[str, Any], generated_date: str) -> Dict[str, Any]:
    subject = _subject_from_memory(memory)
    salutation = _salutation_from_memory(memory)
    source_lines = _memory_lines(memory)
    paragraphs = []
    if source_lines:
        chunk = []
        for line in source_lines:
            chunk.append(line)
            if len("".join(chunk)) >= 120:
                paragraphs.append(_privacy_filter(" ".join(chunk)))
                chunk = []
        if chunk:
            paragraphs.append(_privacy_filter(" ".join(chunk)))
    if not paragraphs:
        paragraphs = ["这些访谈记忆里，留下了我想对家人说的话，也留下了我对生活的牵挂和心愿。"]
    paragraphs = _expand_letter_paragraphs(paragraphs, memory, min_chars=400)
    return {
        "title": "写给家人的一封信",
        "subtitle": f"——{subject}的心里话",
        "salutation": salutation,
        "paragraphs": paragraphs,
        "signature": f"爱你们的{subject}",
        "date": generated_date,
    }


def _expand_letter_paragraphs(paragraphs: List[str], memory: Dict[str, Any], min_chars: int) -> List[str]:
    current = "".join(paragraphs)
    if len(current) >= min_chars:
        return paragraphs
    used = set(paragraphs)
    for line in _memory_lines(memory):
        line = _privacy_filter(line)
        if not line or line in used or line in current:
            continue
        paragraphs.append(line)
        used.add(line)
        current += line
        if len(current) >= min_chars:
            break
    return paragraphs


def _render_card_image(server_root: Path, device_id: str, card: Dict[str, Any], config: dict) -> str:
    from PIL import Image, ImageDraw

    font_regular = _font(34)
    font_small = _font(28)
    font_title = _font(62, bold=True)
    font_subtitle = _font(28)
    font_section = _font(40, bold=True)
    font_quote = _font(34, bold=True)
    font_footer = _font(30)

    body_width = CARD_WIDTH - CARD_PADDING * 2
    blocks = _measure_blocks(card, body_width, font_regular, font_small, font_title, font_subtitle, font_section, font_quote, font_footer)
    height = max(CARD_MIN_HEIGHT, blocks[-1]["bottom"] + CARD_PADDING)
    background = _build_background(server_root, card, config, height)
    image = background.resize((CARD_WIDTH, height))
    draw = ImageDraw.Draw(image)

    _draw_overlay(draw, height)
    y = CARD_PADDING
    y = _draw_wrapped(draw, card["title"], CARD_PADDING, y, body_width, font_title, INK, line_gap=12)
    y += 12
    y = _draw_wrapped(draw, card["subtitle"], CARD_PADDING, y, body_width, font_subtitle, INK_FAINT, line_gap=7)
    y += 28
    y = _draw_wrapped(draw, card.get("intro") or "", CARD_PADDING, y, body_width, font_regular, INK_MID, line_gap=10)
    y += 30

    for section in card.get("sections") or []:
        _draw_separator(draw, y)
        y += 30
        header = f"{section.get('number', '')} {section.get('title', '')}".strip()
        y = _draw_wrapped(draw, header, CARD_PADDING, y, body_width, font_section, AMBER, line_gap=10)
        y += 12
        y = _draw_wrapped(draw, section.get("body") or "", CARD_PADDING, y, body_width, font_regular, INK_MID, line_gap=10)
        quote = section.get("quote") or ""
        if quote:
            y += 12
            y = _draw_wrapped(draw, f"“{quote.strip('“”')}”", CARD_PADDING + 18, y, body_width - 36, font_quote, INK, line_gap=10)
        y += 22

    if card.get("wish"):
        _draw_separator(draw, y)
        y += 28
        y = _draw_wrapped(draw, "最大的心愿", CARD_PADDING, y, body_width, font_section, SAGE, line_gap=10)
        y += 12
        y = _draw_wrapped(draw, card["wish"], CARD_PADDING, y, body_width, font_regular, INK_MID, line_gap=10)
        y += 22

    _draw_separator(draw, y)
    y += 34
    _draw_wrapped(draw, card.get("closing") or "", CARD_PADDING, y, body_width, font_footer, INK_FAINT, line_gap=8)

    patient_id = _safe_key(device_id)
    out_dir = server_root / "data" / "hospice_media" / "dignity_legacy_cards" / patient_id
    out_dir.mkdir(parents=True, exist_ok=True)
    filename = f"legacy_card_{time.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}.png"
    path = out_dir / filename
    image.save(path, "PNG")
    return f"/hospice-media/dignity_legacy_cards/{patient_id}/{filename}"


def _render_family_letter_image(server_root: Path, device_id: str, letter: Dict[str, Any], template_key: str = "warm") -> str:
    from PIL import Image, ImageDraw

    template = LETTER_TEMPLATES[_letter_template_key(template_key)]
    width = 1080
    padding = 88
    body_width = width - padding * 2
    title_font = _font(64, bold=False, preferred="hand")
    subtitle_font = _font(36, preferred="hand")
    body_font = _font(38, preferred="hand")
    signature_font = _font(40, preferred="hand")
    date_font = _font(32, preferred="hand")

    y = padding
    height = 0
    height += _text_height(letter["title"], body_width, title_font, 14) + 12
    height += _text_height(letter.get("subtitle") or "", body_width, subtitle_font, 10) + 44
    height += _text_height(letter.get("salutation") or "", body_width, body_font, 12) + 22
    for paragraph in letter.get("paragraphs") or []:
        height += _text_height(paragraph, body_width, body_font, 14) + 22
    height += 36 + _text_height(letter.get("signature") or "", body_width, signature_font, 12)
    height += 12 + _text_height(letter.get("date") or "", body_width, date_font, 8) + padding
    height = max(1520, height)

    image = _letter_background(width, height, template)
    draw = ImageDraw.Draw(image)
    _draw_letter_border(draw, width, height, template)
    _draw_letter_rules(draw, width, height, padding, template)

    title_lines = _wrap_text(letter["title"], body_width, title_font, draw)
    for line in title_lines:
        line_width = draw.textlength(line, font=title_font)
        draw.text(((width - line_width) / 2, y), line, font=title_font, fill=template["ink"])
        bbox = draw.textbbox((0, y), line, font=title_font)
        y += bbox[3] - bbox[1] + 14
    y += 2

    subtitle = letter.get("subtitle") or ""
    for line in _wrap_text(subtitle, body_width, subtitle_font, draw):
        line_width = draw.textlength(line, font=subtitle_font)
        draw.text(((width - line_width) / 2, y), line, font=subtitle_font, fill=template["ink_faint"])
        bbox = draw.textbbox((0, y), line, font=subtitle_font)
        y += bbox[3] - bbox[1] + 10
    y += 34

    y = _draw_wrapped(draw, letter.get("salutation") or "亲爱的家人：", padding, y, body_width, body_font, template["ink"], line_gap=12)
    y += 22
    for paragraph in letter.get("paragraphs") or []:
        y = _draw_wrapped(draw, f"　　{paragraph}", padding, y, body_width, body_font, template["ink"], line_gap=16)
        y += 22

    y += 22
    signature = letter.get("signature") or ""
    date = letter.get("date") or ""
    signature_width = draw.textlength(signature, font=signature_font)
    draw.text((width - padding - signature_width, y), signature, font=signature_font, fill=template["ink"])
    y += 52
    date_width = draw.textlength(date, font=date_font)
    draw.text((width - padding - date_width, y), date, font=date_font, fill=template["ink_mid"])

    patient_id = _safe_key(device_id)
    out_dir = server_root / "data" / "hospice_media" / "dignity_family_letters" / patient_id
    out_dir.mkdir(parents=True, exist_ok=True)
    filename = f"family_letter_{time.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}.png"
    path = out_dir / filename
    image.save(path, "PNG")
    return f"/hospice-media/dignity_family_letters/{patient_id}/{filename}"


def _measure_blocks(card: Dict[str, Any], width: int, *fonts) -> List[Dict[str, int]]:
    y = CARD_PADDING
    result = []
    font_regular, font_small, font_title, font_subtitle, font_section, font_quote, font_footer = fonts
    for text, font, gap, extra in [
        (card.get("title") or "", font_title, 12, 12),
        (card.get("subtitle") or "", font_subtitle, 7, 28),
        (card.get("intro") or "", font_regular, 10, 30),
    ]:
        y += _text_height(text, width, font, gap) + extra
        result.append({"bottom": y})
    for section in card.get("sections") or []:
        y += 30 + _text_height(f"{section.get('number', '')} {section.get('title', '')}", width, font_section, 10) + 12
        y += _text_height(section.get("body") or "", width, font_regular, 10)
        if section.get("quote"):
            y += 12 + _text_height(section.get("quote") or "", width - 36, font_quote, 10)
        y += 22
        result.append({"bottom": y})
    if card.get("wish"):
        y += 28 + _text_height("最大的心愿", width, font_section, 10) + 12
        y += _text_height(card["wish"], width, font_regular, 10) + 22
    y += 34 + _text_height(card.get("closing") or "", width, font_footer, 8)
    result.append({"bottom": y})
    return result


def _build_background(server_root: Path, card: Dict[str, Any], config: dict, height: int):
    from PIL import Image, ImageDraw, ImageFilter

    generated = _generate_background_image(server_root, card, config)
    if generated:
        try:
            image = Image.open(generated).convert("RGB")
            return _cover_resize(image, CARD_WIDTH, height).filter(ImageFilter.GaussianBlur(10))
        except Exception:
            pass

    image = Image.new("RGB", (CARD_WIDTH, height), CARD_BG)
    draw = ImageDraw.Draw(image)
    for y in range(height):
        ratio = y / max(1, height - 1)
        color = (
            int(255 - 18 * ratio),
            int(248 - 20 * ratio),
            int(238 - 28 * ratio),
        )
        draw.line([(0, y), (CARD_WIDTH, y)], fill=color)
    for index in range(18):
        x = 80 + (index * 137) % CARD_WIDTH
        y = 120 + (index * 311) % height
        radius = 90 + (index % 4) * 34
        fill = (238, 220, 184) if index % 2 else (202, 218, 198)
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=fill)
    return image.filter(ImageFilter.GaussianBlur(26))


def _letter_background(width: int, height: int, template: Dict[str, Any] | None = None):
    from PIL import Image, ImageDraw, ImageFilter

    template = template or LETTER_TEMPLATES["warm"]
    asset = template.get("asset")
    if asset:
        asset_path = Path(__file__).resolve().parent / "assets" / "letter_templates" / str(asset)
        if asset_path.exists():
            try:
                return _cover_resize(Image.open(asset_path).convert("RGB"), width, height)
            except Exception as exc:
                logger.bind(tag=TAG).warning(f"家信信纸底图读取失败，使用本地绘制背景: {exc}")
    top = template["bg_top"]
    bottom = template["bg_bottom"]
    accent = template["accent"]
    soft = template["soft"]
    image = Image.new("RGB", (width, height), top)
    draw = ImageDraw.Draw(image)
    for y in range(height):
        ratio = y / max(1, height - 1)
        color = (
            int(top[0] + (bottom[0] - top[0]) * ratio),
            int(top[1] + (bottom[1] - top[1]) * ratio),
            int(top[2] + (bottom[2] - top[2]) * ratio),
        )
        draw.line((0, y, width, y), fill=color)
    for index in range(26):
        x = (index * 97 + 38) % width
        y = (index * 211 + 80) % height
        r = 34 + (index % 5) * 18
        draw.ellipse((x - r, y - r, x + r, y + r), fill=soft)
    if template.get("style") == "bamboo":
        for x in (116, width - 132):
            draw.line((x, 90, x - 34, height - 100), fill=accent, width=5)
            for y in range(180, height - 120, 220):
                draw.polygon([(x - 8, y), (x - 92, y - 32), (x - 20, y + 38)], fill=soft)
                draw.polygon([(x + 8, y + 42), (x + 86, y + 8), (x + 18, y + 80)], fill=soft)
    elif template.get("style") == "floral":
        for index in range(10):
            cx = 110 + (index * 211) % (width - 220)
            cy = 128 + (index * 277) % (height - 256)
            for petal in range(6):
                dx = ((petal % 3) - 1) * 18
                dy = (petal // 3) * 18 - 10
                draw.ellipse((cx + dx - 18, cy + dy - 12, cx + dx + 18, cy + dy + 12), fill=soft)
            draw.ellipse((cx - 8, cy - 8, cx + 8, cy + 8), fill=accent)
    elif template.get("style") == "sky":
        for index in range(12):
            x = (index * 173 + 72) % width
            y = (index * 131 + 96) % height
            draw.arc((x, y, x + 90, y + 56), 200, 340, fill=soft, width=5)
    _draw_letter_paper_grain(draw, width, height, top, bottom)
    _draw_letter_corner_decor(draw, width, height, template)
    return image.filter(ImageFilter.GaussianBlur(8))


def _draw_letter_border(draw, width: int, height: int, template: Dict[str, Any] | None = None) -> None:
    template = template or LETTER_TEMPLATES["warm"]
    accent = template["accent"]
    soft = template["soft"]
    outer = (38, 38, width - 38, height - 38)
    inner = (56, 56, width - 56, height - 56)
    hairline = (70, 70, width - 70, height - 70)
    draw.rectangle(outer, outline=accent, width=3)
    draw.rectangle(inner, outline=soft, width=1)
    draw.rectangle(hairline, outline=_mix(accent, (255, 255, 255), 0.45), width=1)
    corner = 46
    for x, y, sx, sy in (
        (64, 64, 1, 1),
        (width - 64, 64, -1, 1),
        (64, height - 64, 1, -1),
        (width - 64, height - 64, -1, -1),
    ):
        draw.line((x, y, x + sx * corner, y), fill=accent, width=2)
        draw.line((x, y, x, y + sy * corner), fill=accent, width=2)
        draw.line((x + sx * 12, y + sy * 12, x + sx * corner, y + sy * 12), fill=soft, width=1)
        draw.line((x + sx * 12, y + sy * 12, x + sx * 12, y + sy * corner), fill=soft, width=1)
        for step in (18, 30):
            draw.line((x + sx * step, y, x + sx * step, y + sy * 18), fill=_mix(accent, soft, 0.52), width=1)
            draw.line((x, y + sy * step, x + sx * 18, y + sy * step), fill=_mix(accent, soft, 0.52), width=1)


def _draw_letter_rules(draw, width: int, height: int, padding: int, template: Dict[str, Any]) -> None:
    accent = template["accent"]
    soft = template["soft"]
    line = _mix(soft, (255, 255, 255), 0.42)
    top = padding + 220
    bottom = height - padding - 130
    for y in range(top, max(top, bottom), 70):
        draw.line((padding, y, width - padding, y), fill=line, width=1)
    draw.line((padding - 18, top - 26, padding - 18, bottom + 22), fill=_mix(accent, (255, 255, 255), 0.62), width=2)
    for y in range(top - 10, bottom, 210):
        draw.ellipse((padding - 28, y, padding - 10, y + 18), outline=_mix(accent, soft, 0.55), width=2)


def _draw_letter_paper_grain(draw, width: int, height: int, top, bottom) -> None:
    for index in range(1800):
        x = (index * 47 + 19) % width
        y = (index * 83 + 31) % height
        ratio = y / max(1, height - 1)
        base = (
            int(top[0] + (bottom[0] - top[0]) * ratio),
            int(top[1] + (bottom[1] - top[1]) * ratio),
            int(top[2] + (bottom[2] - top[2]) * ratio),
        )
        draw.point((x, y), fill=_mix(base, (118, 102, 82), 0.92))
    for index in range(44):
        x = (index * 173 + 51) % width
        y = (index * 257 + 87) % height
        radius_x = 18 + (index % 5) * 15
        radius_y = 10 + (index % 4) * 12
        fill = _mix(top, (128, 94, 54), 0.82 + (index % 3) * 0.03)
        draw.ellipse((x - radius_x, y - radius_y, x + radius_x, y + radius_y), fill=fill)
    for index in range(20):
        x = (index * 229 + 113) % width
        y = (index * 181 + 141) % height
        draw.arc((x, y, x + 90, y + 48), 8, 170, fill=_mix(bottom, (116, 82, 48), 0.72), width=1)


def _draw_letter_corner_decor(draw, width: int, height: int, template: Dict[str, Any]) -> None:
    accent = template["accent"]
    soft = template["soft"]
    if template.get("style") == "floral":
        for cx, cy, sx, sy in ((96, 108, 1, 1), (width - 96, height - 108, -1, -1)):
            draw.line((cx, cy, cx + sx * 170, cy + sy * 56), fill=accent, width=3)
            for index in range(7):
                px = cx + sx * (30 + index * 22)
                py = cy + sy * (8 + (index % 3) * 18)
                draw.ellipse((px - 16, py - 11, px + 16, py + 11), fill=soft)
                draw.ellipse((px - 5, py - 5, px + 5, py + 5), fill=accent)
    elif template.get("style") == "bamboo":
        for x, tilt in ((96, 1), (width - 98, -1)):
            draw.line((x, 96, x + tilt * 32, 282), fill=accent, width=4)
            for y in (136, 188, 240):
                draw.polygon([(x, y), (x + tilt * 82, y - 24), (x + tilt * 20, y + 28)], fill=soft)
    elif template.get("style") == "sky":
        for index in range(4):
            y = 92 + index * 30
            draw.arc((width - 250, y, width - 72, y + 84), 190, 350, fill=_mix(accent, soft, 0.45), width=4)
        draw.ellipse((86, height - 146, 138, height - 94), outline=accent, width=3)
        draw.arc((74, height - 160, 150, height - 84), 10, 280, fill=soft, width=4)
    elif template.get("style") == "plain":
        draw.rectangle((width - 220, 92, width - 96, 166), outline=accent, width=3)
        for index in range(3):
            draw.line((width - 202, 112 + index * 18, width - 114, 112 + index * 18), fill=soft, width=2)
        for y in (height - 150, height - 116, height - 82):
            draw.line((94, y, 300, y), fill=_mix(accent, soft, 0.5), width=2)
    else:
        draw.arc((74, 84, 232, 216), 190, 330, fill=accent, width=3)
        draw.arc((width - 232, height - 216, width - 74, height - 84), 10, 150, fill=accent, width=3)
        for x, y in ((118, 126), (width - 140, height - 150)):
            draw.ellipse((x - 18, y - 13, x + 18, y + 13), fill=soft)
            draw.ellipse((x - 6, y - 6, x + 6, y + 6), fill=accent)


def _mix(a, b, ratio: float):
    ratio = max(0.0, min(1.0, ratio))
    return (
        int(a[0] * ratio + b[0] * (1 - ratio)),
        int(a[1] * ratio + b[1] * (1 - ratio)),
        int(a[2] * ratio + b[2] * (1 - ratio)),
    )


def _generate_background_image(server_root: Path, card: Dict[str, Any], config: dict) -> Path | None:
    image_config = ((config.get("hospice") or {}).get("legacy_card_image") or {})
    if image_config.get("enabled") is not True:
        return None
    api_key = image_config.get("api_key") or ((config.get("LLM") or {}).get((config.get("selected_module") or {}).get("LLM")) or {}).get("api_key")
    if not api_key:
        return None
    try:
        import openai

        model = image_config.get("model") or "dall-e-3"
        size = image_config.get("size") or "1024x1792"
        prompt = image_config.get("prompt") or _background_prompt(card)
        client = openai.OpenAI(api_key=api_key, base_url=image_config.get("base_url") or None)
        response = client.images.generate(
            model=model,
            prompt=prompt,
            size=size,
            n=1,
            response_format="b64_json",
        )
        b64 = response.data[0].b64_json
        if not b64:
            return None
        out_dir = server_root / "data" / "hospice_media" / "dignity_legacy_cards" / "_backgrounds"
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / f"background_{uuid.uuid4().hex[:10]}.png"
        path.write_bytes(base64.b64decode(b64))
        return path
    except Exception as exc:
        logger.bind(tag=TAG).warning(f"传承故事背景图生成失败，使用本地背景: {exc}")
        return None


def _background_prompt(card: Dict[str, Any]) -> str:
    return (
        "A warm, quiet editorial background for a Chinese family legacy story card, "
        "soft paper texture, subtle light, gentle memorial mood, no text, no people, "
        f"themes: {card.get('title', 'legacy story')}, family, dignity therapy, life review."
    )


def _draw_overlay(draw, height: int) -> None:
    draw.rounded_rectangle(
        (34, 34, CARD_WIDTH - 34, height - 34),
        radius=28,
        fill=(255, 250, 242),
        outline=(225, 210, 184),
        width=2,
    )


def _draw_separator(draw, y: int) -> None:
    draw.line((CARD_PADDING, y, CARD_WIDTH - CARD_PADDING, y), fill=(210, 190, 158), width=2)


def _draw_wrapped(draw, text: str, x: int, y: int, width: int, font, fill, line_gap: int = 8) -> int:
    for line in _wrap_text(text, width, font, draw):
        draw.text((x, y), line, font=font, fill=fill)
        bbox = draw.textbbox((x, y), line, font=font)
        y += (bbox[3] - bbox[1]) + line_gap
    return y


def _text_height(text: str, width: int, font, line_gap: int) -> int:
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (10, 10))
    draw = ImageDraw.Draw(image)
    lines = _wrap_text(text, width, font, draw)
    if not lines:
        return 0
    total = 0
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        total += (bbox[3] - bbox[1]) + line_gap
    return total


def _wrap_text(text: str, width: int, font, draw) -> List[str]:
    text = _normalize_draw_text(text)
    if not text:
        return []
    lines: List[str] = []
    current = ""
    for char in text:
        candidate = current + char
        if draw.textlength(candidate, font=font) <= width:
            current = candidate
            continue
        if current:
            lines.append(current)
        current = char
    if current:
        lines.append(current)
    return lines


def _normalize_draw_text(text: Any) -> str:
    raw = str(text or "")
    prefix = ""
    while raw.startswith("　"):
        prefix += "　"
        raw = raw[1:]
    raw = re.sub(r"[ \t\r\n]+", " ", raw).strip(" \t\r\n")
    return f"{prefix}{raw}"


def _font(size: int, bold: bool = False, preferred: str = ""):
    from PIL import ImageFont

    if preferred == "hand":
        candidates = (
            ("C:/Windows/Fonts/STXINGKA.TTF", "C:/Windows/Fonts/STXINGKA.TTF"),
            ("C:/Windows/Fonts/STXINWEI.TTF", "C:/Windows/Fonts/STXINWEI.TTF"),
            ("C:/Windows/Fonts/FZSTK.TTF", "C:/Windows/Fonts/FZSTK.TTF"),
            ("C:/Windows/Fonts/FZYTK.TTF", "C:/Windows/Fonts/FZYTK.TTF"),
            ("C:/Windows/Fonts/simkai.ttf", "C:/Windows/Fonts/simkai.ttf"),
        )
    elif preferred == "kai":
        candidates = (
            ("C:/Windows/Fonts/simkai.ttf", "C:/Windows/Fonts/simkai.ttf"),
            ("C:/Windows/Fonts/STKAITI.TTF", "C:/Windows/Fonts/STKAITI.TTF"),
            ("C:/Windows/Fonts/msyhbd.ttc", "C:/Windows/Fonts/msyh.ttc"),
        )
    else:
        candidates = (
        ("C:/Windows/Fonts/msyhbd.ttc", "C:/Windows/Fonts/msyh.ttc"),
        ("C:/Windows/Fonts/simhei.ttf", "C:/Windows/Fonts/simhei.ttf"),
        ("C:/Windows/Fonts/simsun.ttc", "C:/Windows/Fonts/simsun.ttc"),
        )
    for bold_path, regular_path in candidates:
        path = bold_path if bold else regular_path
        if Path(path).exists():
            return ImageFont.truetype(path, size=size)
    return ImageFont.load_default()


def _cover_resize(image, width: int, height: int):
    ratio = max(width / image.width, height / image.height)
    new_size = (int(image.width * ratio), int(image.height * ratio))
    image = image.resize(new_size)
    left = (image.width - width) // 2
    top = (image.height - height) // 2
    return image.crop((left, top, left + width, top + height))


def _safe_key(value: str) -> str:
    key = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value or "")).strip("._")
    return key or "default"


def _artifact_source_dir(server_root: Path, kind: str) -> Path:
    return server_root / "data" / "hospice_media" / kind / "sources"


def _save_latest_artifact(server_root: Path, kind: str, device_id: str, payload: Dict[str, Any]) -> None:
    source_dir = _artifact_source_dir(server_root, kind)
    source_dir.mkdir(parents=True, exist_ok=True)
    patient_id = _safe_key(device_id)
    record = {
        "patient_id": patient_id,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        **payload,
    }
    latest_path = source_dir / f"{patient_id}_latest.json"
    with latest_path.open("w", encoding="utf-8") as file:
        json.dump(record, file, ensure_ascii=False, indent=2)


def _load_latest_artifact(server_root: Path, kind: str, device_id: str) -> Dict[str, Any]:
    patient_id = _safe_key(device_id)
    latest_path = _artifact_source_dir(server_root, kind) / f"{patient_id}_latest.json"
    if not latest_path.exists():
        return {}
    with latest_path.open("r", encoding="utf-8") as file:
        value = json.load(file) or {}
    return value if isinstance(value, dict) else {}


def _letter_template_key(value: Any) -> str:
    key = re.sub(r"[^A-Za-z0-9_-]+", "", str(value or "warm")).strip() or "warm"
    return key if key in LETTER_TEMPLATES else "warm"


def _has_memory(memory: Dict[str, Any]) -> bool:
    return any(isinstance(items, list) and bool(items) for items in (memory or {}).values())


def _first_item_text(items: Any) -> str:
    if not isinstance(items, list):
        return ""
    for item in items:
        text = _item_text(item)
        if text:
            return text
    return ""


def _item_text(item: Any) -> str:
    if isinstance(item, str):
        return item.strip()
    if isinstance(item, dict):
        return "，".join(str(value).strip() for value in item.values() if str(value).strip())
    return str(item or "").strip()


def _intro_from_sections(sections: List[Dict[str, str]]) -> str:
    titles = "、".join(section["title"] for section in sections[:4])
    return f"这份传承故事记录了患者关于{titles}的记忆与心愿。"


def _subject_from_card(card: Dict[str, Any]) -> str:
    title = str(card.get("title") or "")
    match = re.search(r"(.{1,8}?)(?:的)?传承故事", title)
    return match.group(1).strip() if match else ""


def _subject_from_memory(memory: Dict[str, Any]) -> str:
    text = json.dumps(memory or {}, ensure_ascii=False)
    match = re.search(r"([\u4e00-\u9fa5]{1,3}(?:师傅|老师|先生|女士|阿姨|叔叔|爷爷|奶奶))", text)
    if match:
        return match.group(1)
    return "我"


def _subject_from_letter(letter: Dict[str, Any]) -> str:
    text = f"{letter.get('subtitle', '')} {letter.get('signature', '')}"
    match = re.search(r"([\u4e00-\u9fa5]{1,8})(?:的心里话|$)", text)
    if match:
        value = match.group(1).replace("爱你们的", "").strip()
        return value or ""
    return ""


def _salutation_from_memory(memory: Dict[str, Any]) -> str:
    text = json.dumps(memory or {}, ensure_ascii=False)
    family = []
    for label in ("老伴", "妻子", "丈夫", "儿子", "女儿"):
        if label in text:
            family.append("老伴儿" if label in ("老伴", "妻子", "丈夫") else label)
    unique = []
    for item in family:
        if item not in unique:
            unique.append(item)
    return f"亲爱的{'、'.join(unique)}：" if unique else "亲爱的家人："


def _today_text() -> str:
    now = datetime.now()
    return f"{now.year}年{now.month}月{now.day}日"


def _memory_lines(memory: Dict[str, Any]) -> List[str]:
    lines = []
    for key in ("life_story_materials", "important_relationships", "values_and_strengths", "messages_to_family"):
        items = memory.get(key) or []
        if not isinstance(items, list):
            continue
        for item in items:
            text = _item_text(item)
            if text:
                lines.append(text)
    return lines


def _clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _clean_quote(value: Any) -> str:
    text = _clean_text(value)
    return text.strip("“”\"'「」")


def _trim(text: str, limit: int) -> str:
    text = _clean_text(text)
    return text if len(text) <= limit else f"{text[:limit - 1]}…"


def _privacy_filter(text: str) -> str:
    text = _clean_text(text)
    text = re.sub(r"[\u4e00-\u9fa5]{2,12}(?:省|市|县|区|镇|乡|村)", "某地", text)
    text = re.sub(r"[\u4e00-\u9fa5A-Za-z0-9（）()·]{2,24}(?:公司|集团|银行|医院|学校|建委|单位)", lambda m: _generic_org(m.group(0)), text)
    return text


def _generic_org(value: str) -> str:
    if "银行" in value:
        return "银行"
    if "医院" in value:
        return "医院"
    if "学校" in value:
        return "学校"
    if "集团" in value or "公司" in value:
        return "单位"
    if "建委" in value:
        return "工程管理单位"
    return "单位"
