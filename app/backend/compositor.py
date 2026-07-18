"""Композитинг фото-карточки (полароид-стиль).

Логотипы партнёров и подпись накладываются ДЕТЕРМИНИРОВАННО поверх выбранного
кадра (ADR-1) — модель их не рисует. Логотипы берутся из assets/logos (до 3 шт.).
"""
from __future__ import annotations

import io
from pathlib import Path
from typing import List

from PIL import Image, ImageOps, ImageDraw, ImageFont

import config

# Размер карточки (пиксели). Пропорция ~ фотокарточка 10x15, поле снизу под бренд.
CARD_W, CARD_H = 1200, 1800
MARGIN = 60
PHOTO_TOP = 60
PHOTO_H = 1320               # зона фото
BAND_TOP = PHOTO_TOP + PHOTO_H + 30
TEAL = (11, 85, 99)


def _font(size: int, bold: bool = False):
    candidates = [
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _load_logos(limit: int = 3) -> List[Image.Image]:
    logos = []
    if config.LOGOS.exists():
        for p in sorted(config.LOGOS.glob("*.png"))[:limit]:
            try:
                logos.append(Image.open(p).convert("RGBA"))
            except Exception:
                pass
    return logos


def build_card(generated_png: bytes, caption: str = "Я на Сахалине",
               subcaption: str = "Нефть и Газ Сахалина 2026") -> bytes:
    card = Image.new("RGB", (CARD_W, CARD_H), (255, 255, 255))
    draw = ImageDraw.Draw(card)

    # --- фото ---
    photo = Image.open(io.BytesIO(generated_png)).convert("RGB")
    photo = ImageOps.exif_transpose(photo)
    photo_area = (CARD_W - 2 * MARGIN, PHOTO_H)
    photo = ImageOps.fit(photo, photo_area, Image.LANCZOS)
    card.paste(photo, (MARGIN, PHOTO_TOP))
    # тонкая рамка вокруг фото
    draw.rectangle([MARGIN, PHOTO_TOP, MARGIN + photo_area[0], PHOTO_TOP + photo_area[1]],
                   outline=(210, 216, 218), width=2)

    # --- подпись ---
    f_cap = _font(58, bold=True)
    f_sub = _font(34)
    draw.text((MARGIN, BAND_TOP), caption, fill=TEAL, font=f_cap)
    draw.text((MARGIN, BAND_TOP + 72), subcaption, fill=(90, 107, 111), font=f_sub)

    # --- логотипы партнёров (правый нижний угол ряда) ---
    logos = _load_logos()
    if logos:
        target_h = 90
        gap = 40
        scaled = []
        for lg in logos:
            ratio = target_h / lg.height
            scaled.append(lg.resize((int(lg.width * ratio), target_h), Image.LANCZOS))
        total_w = sum(s.width for s in scaled) + gap * (len(scaled) - 1)
        x = CARD_W - MARGIN - total_w
        y = BAND_TOP + 30
        for s in scaled:
            card.paste(s, (x, y), s)
            x += s.width + gap
        # подпись «Партнёры»
        draw.text((CARD_W - MARGIN - total_w, y - 34), "Партнёры:", fill=(150, 160, 163), font=_font(24))

    out = io.BytesIO()
    card.save(out, format="PNG")
    return out.getvalue()
