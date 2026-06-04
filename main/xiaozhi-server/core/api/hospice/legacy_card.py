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


class HospiceLegacyCardMixin:
    async def handle_legacy_card_render(self, request):
        """POST /api/hospice/legacy-card/render body: {device_id, memory?}."""
        try:
            data = await request.json()
            device_id = (data.get("device_id") or "default").strip() or "default"
            memory = data.get("memory") or {}
            if not _has_memory(memory):
                return web.json_response(
                    {"success": False, "error": "还没有可生成传承故事卡片的访谈记忆。"},
                    status=400,
                    headers=self._cors_headers(),
                )

            server_root = Path(__file__).resolve().parents[3]
            card = _generate_card_payload(memory, self.config)
            image_url = _render_card_image(server_root, device_id, card, self.config)
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

    async def handle_family_letter_render(self, request):
        """POST /api/hospice/family-letter/render body: {device_id, memory?}."""
        try:
            data = await request.json()
            device_id = (data.get("device_id") or "default").strip() or "default"
            memory = data.get("memory") or {}
            if not _has_memory(memory):
                return web.json_response(
                    {"success": False, "error": "还没有可生成家信的访谈记忆。"},
                    status=400,
                    headers=self._cors_headers(),
                )

            server_root = Path(__file__).resolve().parents[3]
            letter = _generate_family_letter_payload(memory, self.config)
            image_url = _render_family_letter_image(server_root, device_id, letter)
            return web.json_response(
                {"success": True, "letter": letter, "image_url": image_url},
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


def _render_family_letter_image(server_root: Path, device_id: str, letter: Dict[str, Any]) -> str:
    from PIL import Image, ImageDraw

    width = 1080
    padding = 88
    body_width = width - padding * 2
    title_font = _font(58, bold=True, preferred="kai")
    subtitle_font = _font(34, preferred="kai")
    body_font = _font(36, preferred="kai")
    signature_font = _font(36, preferred="kai")
    date_font = _font(30, preferred="kai")

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

    image = _letter_background(width, height)
    draw = ImageDraw.Draw(image)
    _draw_letter_border(draw, width, height)

    title_lines = _wrap_text(letter["title"], body_width, title_font, draw)
    for line in title_lines:
        line_width = draw.textlength(line, font=title_font)
        draw.text(((width - line_width) / 2, y), line, font=title_font, fill=INK)
        bbox = draw.textbbox((0, y), line, font=title_font)
        y += bbox[3] - bbox[1] + 14
    y += 2

    subtitle = letter.get("subtitle") or ""
    for line in _wrap_text(subtitle, body_width, subtitle_font, draw):
        line_width = draw.textlength(line, font=subtitle_font)
        draw.text(((width - line_width) / 2, y), line, font=subtitle_font, fill=INK_FAINT)
        bbox = draw.textbbox((0, y), line, font=subtitle_font)
        y += bbox[3] - bbox[1] + 10
    y += 34

    y = _draw_wrapped(draw, letter.get("salutation") or "亲爱的家人：", padding, y, body_width, body_font, INK, line_gap=12)
    y += 22
    for paragraph in letter.get("paragraphs") or []:
        y = _draw_wrapped(draw, f"    {paragraph}", padding, y, body_width, body_font, INK, line_gap=14)
        y += 22

    y += 22
    signature = letter.get("signature") or ""
    date = letter.get("date") or ""
    signature_width = draw.textlength(signature, font=signature_font)
    draw.text((width - padding - signature_width, y), signature, font=signature_font, fill=INK)
    y += 52
    date_width = draw.textlength(date, font=date_font)
    draw.text((width - padding - date_width, y), date, font=date_font, fill=INK_MID)

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


def _letter_background(width: int, height: int):
    from PIL import Image, ImageDraw, ImageFilter

    image = Image.new("RGB", (width, height), (246, 232, 202))
    draw = ImageDraw.Draw(image)
    for y in range(height):
        ratio = y / max(1, height - 1)
        color = (
            int(248 - 20 * ratio),
            int(235 - 18 * ratio),
            int(206 - 20 * ratio),
        )
        draw.line((0, y, width, y), fill=color)
    for index in range(26):
        x = (index * 97 + 38) % width
        y = (index * 211 + 80) % height
        r = 34 + (index % 5) * 18
        draw.ellipse((x - r, y - r, x + r, y + r), fill=(232, 214, 182))
    return image.filter(ImageFilter.GaussianBlur(8))


def _draw_letter_border(draw, width: int, height: int) -> None:
    outer = (38, 38, width - 38, height - 38)
    inner = (56, 56, width - 56, height - 56)
    draw.rectangle(outer, outline=(154, 124, 82), width=3)
    draw.rectangle(inner, outline=(196, 165, 115), width=1)
    corner = 46
    for x, y, sx, sy in (
        (64, 64, 1, 1),
        (width - 64, 64, -1, 1),
        (64, height - 64, 1, -1),
        (width - 64, height - 64, -1, -1),
    ):
        draw.line((x, y, x + sx * corner, y), fill=(166, 128, 80), width=2)
        draw.line((x, y, x, y + sy * corner), fill=(166, 128, 80), width=2)
        draw.line((x + sx * 12, y + sy * 12, x + sx * corner, y + sy * 12), fill=(196, 165, 115), width=1)
        draw.line((x + sx * 12, y + sy * 12, x + sx * 12, y + sy * corner), fill=(196, 165, 115), width=1)


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
    text = re.sub(r"\s+", " ", str(text or "")).strip()
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


def _font(size: int, bold: bool = False, preferred: str = ""):
    from PIL import ImageFont

    if preferred == "kai":
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
