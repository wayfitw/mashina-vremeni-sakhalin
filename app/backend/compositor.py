"""Композитинг фото-карточки в стиле макета (полароид).

Layout сверху вниз:
  • белая рамка-полароид;
  • фото гостя;
  • рукописная подпись поверх нижней части фото (2 строки);
  • ряд из 4 логотипов партнёров (assets/logos/01..04);
  • курсивный футер.

Подпись и футер берутся из локации (locations.json → card_caption / card_footer),
логотипы — детерминированно из assets/logos (ADR-1, ИИ их не рисует).
"""
from __future__ import annotations

import io
from pathlib import Path
from typing import List, Optional

from PIL import Image, ImageOps, ImageDraw, ImageFont, ImageFilter

import config

FONTS = config.BASE_DIR / "assets" / "fonts"

# --- размеры карточки (портрет, ~ полароид) ---
CARD_W = 1200
MARGIN = 56                       # белое поле полароида по бокам/сверху
PHOTO_RATIO = 1.30                # высота фото = ширина * ratio
LOGO_H = 96
FOOTER_GAP = 64

INK = (30, 42, 66)                # тёмно-синий текст
FOOTER_COL = (74, 92, 140)        # приглушённый синий футера


def _font(kind: str, size: int):
    """Надёжный подбор шрифта: бандл в assets/fonts → системный Linux(DejaVu) → Windows(Arial)."""
    table = {
        # подпись — рукописный с кириллицей (Caveat, как согласовано)
        "script": [FONTS / "Caveat.ttf", FONTS / "MarckScript.ttf",
                   "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Italic.ttf",
                   "C:/Windows/Fonts/segoesc.ttf", "C:/Windows/Fonts/ariali.ttf"],
        # футер — классический наборный курсив с засечками
        "italic": [FONTS / "PTSerif-Italic.ttf", FONTS / "PlayfairItalic.ttf",
                   "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Italic.ttf",
                   "C:/Windows/Fonts/ariali.ttf", "C:/Windows/Fonts/timesi.ttf"],
        "regular": [FONTS / "DejaVuSans.ttf",
                    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                    "C:/Windows/Fonts/arial.ttf"],
        "bold": [FONTS / "DejaVuSans-Bold.ttf",
                 "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                 "C:/Windows/Fonts/arialbd.ttf"],
    }
    # страховка от «квадратиков»: если специфичный шрифт не нашёлся — берём
    # бандл DejaVuSans (кириллица есть), и лишь в самом конце load_default.
    for p in list(table.get(kind, table["regular"])) + [FONTS / "DejaVuSans.ttf"]:
        try:
            return ImageFont.truetype(str(p), size)
        except Exception:
            continue
    return ImageFont.load_default()


def _load_logos() -> List[Image.Image]:
    """Логотипы в фиксированном порядке 01..04 (как в макете, слева направо)."""
    logos: List[Image.Image] = []
    if config.LOGOS.exists():
        for p in sorted(config.LOGOS.glob("0*.png")):
            try:
                logos.append(Image.open(p).convert("RGBA"))
            except Exception:
                pass
    return logos


def _text_w(draw, text, font):
    b = draw.textbbox((0, 0), text, font=font)
    return b[2] - b[0]


def build_card(generated_png: bytes,
               caption_lines: Optional[List[str]] = None,
               footer: str = "") -> bytes:
    caption_lines = caption_lines or []

    photo_w = CARD_W - 2 * MARGIN
    photo_h = int(photo_w * PHOTO_RATIO)
    photo_top = MARGIN
    logos_top = photo_top + photo_h + 54
    footer_y = logos_top + LOGO_H + FOOTER_GAP
    card_h = footer_y + 96

    card = Image.new("RGB", (CARD_W, card_h), (255, 255, 255))
    draw = ImageDraw.Draw(card)

    # --- фото ---
    photo = ImageOps.exif_transpose(Image.open(io.BytesIO(generated_png))).convert("RGB")
    photo = ImageOps.fit(photo, (photo_w, photo_h), Image.LANCZOS)

    # рукописная подпись поверх нижней части фото (белым, с мягкой тенью)
    if caption_lines:
        ov = Image.new("RGBA", photo.size, (0, 0, 0, 0))
        od = ImageDraw.Draw(ov)
        f_cap = _font("script", 74)
        line_h = 88
        y = photo.height - 40 - line_h * len(caption_lines)
        x = 46
        for ln in caption_lines:
            od.text((x + 2, y + 2), ln, font=f_cap, fill=(0, 0, 0, 130))   # тень
            od.text((x, y), ln, font=f_cap, fill=(255, 255, 255, 235))
            y += line_h
        photo = Image.alpha_composite(photo.convert("RGBA"), ov).convert("RGB")

    card.paste(photo, (MARGIN, photo_top))
    draw.rectangle([MARGIN, photo_top, MARGIN + photo_w, photo_top + photo_h],
                   outline=(214, 220, 226), width=2)

    # --- ряд логотипов ---
    # Выравнивание как на референсе: не по одной высоте, а по визуальному «весу»
    # (равная площадь). Квадратные (ТПП, САХАЛИН) выходят выше, широкие
    # (СМНМ ВИКО, DeltaЛизинг) — ниже, ряд смотрится ровным.
    logos = _load_logos()
    if logos:
        target_area = LOGO_H * LOGO_H * 2.4      # подобрано под макет
        scaled = []
        for lg in logos:
            a = lg.width / lg.height
            h = int((target_area / a) ** 0.5)
            h = max(72, min(int(LOGO_H * 1.55), h))   # квадратные ↑, широкие ↓
            scaled.append(lg.resize((max(1, int(h * a)), h), Image.LANCZOS))
        gap = 72
        total = sum(s.width for s in scaled) + gap * (len(scaled) - 1)
        # не вылезаем за поля
        if total > photo_w:
            k = photo_w / total
            scaled = [s.resize((max(1, int(s.width * k)), max(1, int(s.height * k))), Image.LANCZOS) for s in scaled]
            gap = int(gap * k)
            total = sum(s.width for s in scaled) + gap * (len(scaled) - 1)
        x = (CARD_W - total) // 2
        row_h = max(s.height for s in scaled)
        for s in scaled:
            y = logos_top + (row_h - s.height) // 2
            card.paste(s, (x, y), s)
            x += s.width + gap

    # --- футер --- (рукописный Caveat, как было согласовано)
    if footer:
        f_foot = _font("script", 44)
        fw = _text_w(draw, footer, f_foot)
        draw.text(((CARD_W - fw) // 2, footer_y), footer, font=f_foot, fill=FOOTER_COL)

    out = io.BytesIO()
    card.save(out, format="PNG")
    return out.getvalue()
