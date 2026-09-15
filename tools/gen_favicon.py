# -*- coding: utf-8 -*-
"""Значки вкладки и экрана «Домой» из фирменных файлов «Сахалинской Энергии».

Источники в tools/brand/ извлечены из «Руководства по фирменному стилю»:
  favicon_se.png  — фавикон «СЭ SE» (стр. 9), идёт во вкладку браузера;
  logo_round.png  — основной круглый знак (стр. 8), идёт в значок iPad:
                    в 180 точек он читается, а «СЭ SE» из 75 точек расплылся бы.

Запуск:  python tools/gen_favicon.py
"""
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
BRAND = ROOT / "tools" / "brand"
OUT = ROOT / "app" / "frontend"
NAVY = (16, 24, 64)       # фирменный тёмно-синий #101840


def flat(im: Image.Image, bg) -> Image.Image:
    im = im.convert("RGBA")
    base = Image.new("RGB", im.size, bg)
    base.paste(im, (0, 0), im)
    return base


fav = flat(Image.open(BRAND / "favicon_se.png"), NAVY)
fav.resize((32, 32), Image.LANCZOS).save(OUT / "favicon-32.png")
fav.resize((64, 64), Image.LANCZOS).save(OUT / "favicon.ico", format="ICO",
                                          sizes=[(16, 16), (32, 32), (48, 48), (64, 64)])

logo = Image.open(BRAND / "logo_round.png").convert("RGBA")
logo = logo.crop(logo.getbbox())
touch = Image.new("RGB", (180, 180), NAVY)
side = 164
touch.paste(logo.resize((side, side), Image.LANCZOS), ((180 - side) // 2,) * 2,
            logo.resize((side, side), Image.LANCZOS))
touch.save(OUT / "apple-touch-icon.png")

for f in ("favicon.ico", "favicon-32.png", "apple-touch-icon.png"):
    print(" ", f, (OUT / f).stat().st_size, "байт")
