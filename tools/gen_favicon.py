# -*- coding: utf-8 -*-
"""Значок вкладки из фирменного знака «Сахалин».

Берём только щит с маяком: со словом «САХАЛИН» знак в 32 точки не читается.
Фон значка белый, как в самом фирменном файле: внутри щита белый маяк, и на
тёмной подложке он превратился бы в дырку. Белые углы кадрированного щита при
этом сливаются с фоном без стыка.

Запуск:  python tools/gen_favicon.py
"""
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "app" / "backend" / "assets" / "logos_card" / "04_sakhalin.png"
OUT = ROOT / "app" / "frontend"
BG = (255, 255, 255)      # знак нарисован на белом, так и оставляем

logo = Image.open(SRC).convert("RGB")
# щит занимает верхнюю часть знака, подпись — нижнюю
top = logo.crop((0, 0, logo.width, int(logo.height * 0.58)))
# файл залит белым, а не прозрачным, поэтому границы щита ищем по «не белому»
px = top.load()
xs, ys = [], []
for y in range(top.height):
    for x in range(top.width):
        r, g, b = px[x, y]
        if 255 - min(r, g, b) > 24:
            xs.append(x); ys.append(y)
shield = top.crop((min(xs), min(ys), max(xs) + 1, max(ys) + 1))


def build(size: int) -> Image.Image:
    im = Image.new("RGB", (size, size), BG)
    side = int(size * 0.80)
    w = side if shield.width >= shield.height else int(shield.width * side / shield.height)
    h = int(shield.height * w / shield.width)
    if h > side:
        h, w = side, int(shield.width * side / shield.height)
    im.paste(shield.resize((w, h), Image.LANCZOS),
             ((size - w) // 2, (size - h) // 2))
    return im


build(180).save(OUT / "apple-touch-icon.png")
build(32).save(OUT / "favicon-32.png")
build(64).save(OUT / "favicon.ico", format="ICO",
               sizes=[(16, 16), (32, 32), (48, 48), (64, 64)])
print("щит", shield.size, "-> значки на фоне", BG)
for f in ("favicon.ico", "favicon-32.png", "apple-touch-icon.png"):
    print(" ", f, (OUT / f).stat().st_size, "байт")
