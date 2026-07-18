"""Детерминированный композитинг: фон НЕ генерируется вообще.

Схема (как в настоящих фотобудках, аналог green screen):
  1) nano-banana-2 генерит ТОЛЬКО человека — нужная поза/одежда/свет, чистый фон;
  2) background-remover вырезает человека (RGBA);
  3) Pillow вклеивает его в эталонный кадр локации по анкеру (позиция/масштаб
     фиксированы в locations.json) + мягкая тень под ногами + цветоподгонка.

Фон при этом байт-в-байт равен эталону — «уплыть» не может в принципе.
"""
from __future__ import annotations

import io

from PIL import Image, ImageOps, ImageFilter, ImageEnhance, ImageStat

import config
import replicate_client

BG_REMOVER = "851-labs/background-remover:a029dff38972b5fda4ec5d75d7d1cd25aeff621d2cf4946a41055d7db66b80bc"

# Промпт генерации ТОЛЬКО человека (фон нейтральный, вырежется)
PERSON_PROMPT = (
    "Photorealistic full-length photo of this exact person standing, captured head to shoes. "
    "Image 1 is their FACE — copy it precisely: same face shape, cheeks, jawline, eyes, skin tone; "
    "no beautifying, no widening, no smoothing. Image 2 shows their true BODY BUILD — match it exactly, "
    "not heavier and not slimmer. Pose: relaxed and natural, body turned slightly at an angle, weight "
    "on one leg, one hand casually in a pocket, light genuine smile — not a stiff frontal passport pose. "
    "Outfit: {OUTFIT}. Lighting: warm golden-hour coastal sunlight from the upper left, soft outdoor "
    "daylight. Background: plain light-gray seamless studio backdrop, nothing else. Full body fully "
    "visible with clear margin around; feet firmly on the ground. No text, no logos, no props, "
    "no extra people, no anatomical distortions."
)


def _remove_bg(image_bytes: bytes) -> bytes | None:
    """Вырезает человека: RGBA PNG с прозрачным фоном."""
    if not replicate_client._client:
        return None
    import concurrent.futures
    def _run():
        out = replicate_client._client.run(
            BG_REMOVER, input={"image": replicate_client._data_uri(image_bytes), "format": "png"})
        return replicate_client._read_output(out)
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        try:
            return pool.submit(_run).result(timeout=120)
        except Exception as exc:  # noqa: BLE001
            print(f"[composite] remove-bg failed: {exc}")
            return None


def _match_colors(person: Image.Image, scene: Image.Image, strength: float = 0.35) -> Image.Image:
    """Мягко подгоняет яркость/тон человека под сцену (по нижней половине кадра)."""
    scene_stat = ImageStat.Stat(scene.crop((0, scene.height // 2, scene.width, scene.height)))
    rgb = person.convert("RGB")
    person_stat = ImageStat.Stat(rgb, mask=person.split()[3])
    out = rgb
    # яркостная подгонка
    p_mean = sum(person_stat.mean) / 3 or 1.0
    s_mean = sum(scene_stat.mean) / 3
    factor = 1 + ((s_mean / p_mean) - 1) * strength
    out = ImageEnhance.Brightness(out).enhance(max(0.7, min(1.3, factor)))
    out.putalpha(person.split()[3])
    return out


def compose(person_rgba: bytes, reference_bytes: bytes, anchor: dict) -> bytes:
    """Вклеивает вырезанного человека в эталон по анкеру.
    anchor: cx (0..1 центр по X), bottom (0..1 низ ног), height (0..1 рост от высоты кадра)."""
    scene = ImageOps.exif_transpose(Image.open(io.BytesIO(reference_bytes))).convert("RGB")
    person = Image.open(io.BytesIO(person_rgba)).convert("RGBA")

    # обрезаем прозрачные поля вокруг человека
    bbox = person.split()[3].getbbox()
    if bbox:
        person = person.crop(bbox)

    target_h = int(scene.height * anchor.get("height", 0.55))
    ratio = target_h / person.height
    person = person.resize((int(person.width * ratio), target_h), Image.LANCZOS)
    person = _match_colors(person, scene)

    px = int(scene.width * anchor.get("cx", 0.35) - person.width / 2)
    py = int(scene.height * anchor.get("bottom", 0.96) - person.height)

    # мягкая контактная тень под ногами
    shadow = Image.new("RGBA", scene.size, (0, 0, 0, 0))
    sw, sh = int(person.width * 0.85), max(14, int(person.height * 0.05))
    ell = Image.new("RGBA", (sw, sh), (0, 0, 0, 0))
    from PIL import ImageDraw
    ImageDraw.Draw(ell).ellipse([0, 0, sw, sh], fill=(10, 10, 10, 110))
    ell = ell.filter(ImageFilter.GaussianBlur(6))
    shadow.paste(ell, (px + (person.width - sw) // 2, py + person.height - sh // 2), ell)

    out = scene.convert("RGBA")
    out.alpha_composite(shadow)
    out.alpha_composite(person, (px, py))

    buf = io.BytesIO()
    out.convert("RGB").save(buf, format="JPEG", quality=93)
    return buf.getvalue()


def generate_composite(face_png: bytes, body_png: bytes, reference_bytes: bytes,
                       outfit: str, anchor: dict) -> bytes | None:
    """Полный цикл одного варианта: человек → вырезка → вклейка в эталон."""
    prompt = PERSON_PROMPT.replace("{OUTFIT}", outfit)
    person = replicate_client.nano_banana([face_png, body_png], prompt)
    if not person:
        return None
    cut = _remove_bg(person)
    if not cut:
        return None
    return compose(cut, reference_bytes, anchor)
