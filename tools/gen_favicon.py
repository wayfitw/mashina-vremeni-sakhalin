# -*- coding: utf-8 -*-
"""Значки вкладки и экрана «Домой» из фирменных файлов «Сахалинской Энергии».

Источник — основной круглый знак из «Руководства по фирменному стилю» (стр. 8),
tools/brand/logo_round.png. Фавикон «СЭ SE» (tools/brand/favicon_se.png) заказчик
попросил не использовать: и во вкладке, и на iPad — основной знак.
Во вкладке углы прозрачные, чтобы круг смотрелся одинаково на светлой и тёмной теме.

Запуск:  python tools/gen_favicon.py
"""
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
BRAND = ROOT / "tools" / "brand"
OUT = ROOT / "app" / "frontend"
NAVY = (16, 24, 64)       # фирменный тёмно-синий #101840

logo = Image.open(BRAND / "logo_round.png").convert("RGBA")
logo = logo.crop(logo.getbbox())

logo.resize((32, 32), Image.LANCZOS).save(OUT / "favicon-32.png")
logo.resize((256, 256), Image.LANCZOS).save(OUT / "favicon.ico", format="ICO",
                                            sizes=[(16, 16), (32, 32), (48, 48), (64, 64)])
touch = Image.new("RGB", (180, 180), NAVY)
side = 164
touch.paste(logo.resize((side, side), Image.LANCZOS), ((180 - side) // 2,) * 2,
            logo.resize((side, side), Image.LANCZOS))
touch.save(OUT / "apple-touch-icon.png")

for f in ("favicon.ico", "favicon-32.png", "apple-touch-icon.png"):
    print(" ", f, (OUT / f).stat().st_size, "байт")
