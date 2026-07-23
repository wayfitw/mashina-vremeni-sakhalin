"""Резервный провайдер генерации через Replicate — FLUX Kontext Pro (image-to-image).

Адаптировано из паттерна remtechnika-ai/backend/services/replicate_svc.py:
внешний вызов с таймаутом, универсальное чтение результата, graceful None при
отсутствии токена (ADR-6: Replicate — альтернатива/резерв к Gemini «Nano Banana»).
"""
from __future__ import annotations

import base64
import concurrent.futures

import httpx

import config

_IMAGE_TIMEOUT = 180  # сек — не даём внешнему вызову зависнуть

# Nano Banana (Gemini image) через Replicate — multi-image (гость + эталон сцены).
# Pro — заметно лучше держит сходство лица (конфигурируется через .env).
NANO_BANANA_MODEL = config.NANO_BANANA_MODEL
# FLUX Kontext Pro — резерв, одна картинка (только гость)
FLUX_MODEL = "black-forest-labs/flux-kontext-pro"
# Точный перенос лица на готовый кадр (InsightFace-подход, как в roop/facefusion)
FACE_SWAP_MODEL = "cdingram/face-swap:d1d6ea8c8be89d664a07a457526f7128109dee7030fdac424788d762c71ed111"

try:
    import replicate
    _client = replicate.Client(api_token=config.REPLICATE_API_TOKEN) if config.REPLICATE_API_TOKEN else None
except Exception:  # noqa: BLE001 — пакет/токен недоступны → провайдер просто выключен
    _client = None


def available() -> bool:
    return _client is not None


def _read_output(output) -> bytes | None:
    """Универсальное чтение результата Replicate (file-like / url / список)."""
    try:
        if hasattr(output, "read"):
            return output.read()
        if hasattr(output, "url"):
            return httpx.get(str(output.url), timeout=120).content
        url = str(output[0]) if hasattr(output, "__getitem__") else str(output)
        return httpx.get(url, timeout=120).content
    except Exception:
        print("[replicate] read error")
        return None


def _shrink(image_bytes: bytes, max_side: int = 1600, quality: int = 88) -> bytes:
    """Сжимает картинку до JPEG ≤max_side px: полезная нагрузка меньше в разы,
    запросы быстрее и не рвутся (connection reset на ~5 МБ base64)."""
    import io
    from PIL import Image, ImageOps
    try:
        img = ImageOps.exif_transpose(Image.open(io.BytesIO(image_bytes))).convert("RGB")
        if max(img.size) > max_side:
            img.thumbnail((max_side, max_side), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality)
        return buf.getvalue()
    except Exception:  # noqa: BLE001 — не смогли сжать, шлём как есть
        return image_bytes


def _data_uri(image_bytes: bytes, mime: str = "image/jpeg") -> str:
    return f"data:{mime};base64,{base64.b64encode(_shrink(image_bytes)).decode()}"


def _apply_model_args(inp: dict) -> dict:
    """Дополняет вход под семейство модели в NANO_BANANA_MODEL:
      - Seedream (bytedance/seedream-*): параметр `size`, без `output_format`;
      - Nano Banana (google/nano-banana*): `output_format` + `resolution`.
    По ArcFace (21.07.2026) seedream-4.5 держит лицо лучше (0.74 vs 0.31 raw)."""
    if "seedream" in NANO_BANANA_MODEL:
        inp["size"] = config.NANO_BANANA_RESOLUTION  # 2K
    else:
        inp["output_format"] = "jpg"
        if "nano-banana" in NANO_BANANA_MODEL:
            inp["resolution"] = config.NANO_BANANA_RESOLUTION
    return inp


def _nano_banana_sync(images: list[bytes], prompt: str) -> bytes | None:
    """Генерация (multi-image): гость + эталон сцены → фотореалистичная вставка
    с сохранением лица и телосложения, узнаваемым фоном, нейтральной одеждой."""
    if not _client:
        return None
    inp = _apply_model_args({
        "prompt": prompt,
        "image_input": [_data_uri(b) for b in images],
        "aspect_ratio": "3:4",
    })
    output = _client.run(NANO_BANANA_MODEL, input=inp)
    return _read_output(output)


def nano_banana(images: list[bytes], prompt: str, retries: int = 3) -> bytes | None:
    """Основной путь генерации. При 429 (лимит запросов/мин) ждём и повторяем —
    не отдаём гостя в резерв с «не тем» маяком. None только после всех попыток."""
    if not _client or not images:
        return None
    import time
    for attempt in range(retries):
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            fut = pool.submit(_nano_banana_sync, images, prompt)
            try:
                return fut.result(timeout=_IMAGE_TIMEOUT)
            except Exception as exc:  # noqa: BLE001
                msg = str(exc)
                if attempt < retries - 1:
                    # 429 — ждём дольше; сетевые обрывы (reset/timeout) — короткий повтор
                    wait = 25 * (attempt + 1) if "429" in msg else 5
                    print(f"[replicate] сбой ({msg[:60]}…), жду {wait}с и повторяю ({attempt + 1}/{retries})")
                    time.sleep(wait)
                    continue
                print(f"[replicate] nano-banana failed/timeout: {exc}")
                return None
    return None


# Второй проход nano-banana = диффузионный face-swap в ПОЛНОМ разрешении (рек. №2):
# без 128px-бутылочного горлышка inswapper → без «восковости», выше детализация.
NANO_SWAP_PROMPT = (
    "Image 1 is a photo of a person in a scene. Image 2 is a close-up of the SAME person's real face. "
    "Replace ONLY the face in image 1 with the exact face from image 2: same identity, same facial "
    "features, same eyes, nose, mouth, face shape and skin tone. Keep EVERYTHING else in image 1 "
    "exactly as is — pose, body, hair, clothing, background, framing and lighting must not change. "
    "Match the face lighting and skin tone to image 1. Photorealistic, seamless, natural skin texture, "
    "sharp facial detail. Do not beautify or alter the identity."
)


def _nano_face_swap_sync(frame: bytes, face_png: bytes) -> bytes | None:
    if not _client:
        return None
    inp = _apply_model_args({
        "prompt": NANO_SWAP_PROMPT,
        "image_input": [_data_uri(frame), _data_uri(face_png)],
        "aspect_ratio": "3:4",
    })
    output = _client.run(NANO_BANANA_MODEL, input=inp)
    return _read_output(output)


def nano_face_swap(frame: bytes, face_png: bytes, retries: int = 2) -> bytes | None:
    """Диффузионный face-swap вторым проходом nano-banana (рек. №2): переносит
    реальное лицо гостя на выбранный кадр в полном разрешении. None при неудаче —
    вызывающий тогда отдаёт исходный кадр (паттерн `swapped or out`)."""
    if not _client or not frame or not face_png:
        return None
    import time
    for attempt in range(retries):
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            fut = pool.submit(_nano_face_swap_sync, frame, face_png)
            try:
                return fut.result(timeout=_IMAGE_TIMEOUT)
            except Exception as exc:  # noqa: BLE001
                if attempt < retries - 1:
                    wait = 25 if "429" in str(exc) else 5
                    print(f"[replicate] nano-swap сбой ({str(exc)[:50]}…), жду {wait}с")
                    time.sleep(wait); continue
                print(f"[replicate] nano-swap failed/timeout: {exc}")
                return None
    return None


# GFPGAN — реставрация/лёгкая бьютификация лица (для входа с вебкамеры: шум, блюр, низкое разрешение)
GFPGAN_MODEL = "tencentarc/gfpgan:0fbacf7afc6c144e5be9767cff80f25aff23e52b0708f17e20f9879b2f21516c"


def _enhance_face_sync(image_bytes: bytes) -> bytes | None:
    if not _client:
        return None
    output = _client.run(GFPGAN_MODEL, input={"img": _data_uri(image_bytes), "scale": 2, "version": "v1.4"})
    return _read_output(output)


def enhance_face(image_bytes: bytes, retries: int = 2) -> bytes | None:
    """GFPGAN: чистит и слегка улучшает лицо с вебкам-кадра (шум/блюр/низкое разрешение).
    None при ошибке — вызывающий тогда использует исходное фото."""
    if not _client or not image_bytes:
        return None
    import time
    for attempt in range(retries):
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            fut = pool.submit(_enhance_face_sync, image_bytes)
            try:
                return fut.result(timeout=120)
            except Exception as exc:  # noqa: BLE001
                if attempt < retries - 1:
                    time.sleep(5); continue
                print(f"[replicate] gfpgan failed/timeout: {exc}")
                return None
    return None


def sharpen_result(image_bytes: bytes, percent: int = 70) -> bytes | None:
    """Локальная резкость (unsharp mask) после свапа: чётче контуры лица/губ.
    Лицо НЕ перерисовывается → идентичность сохраняется 1:1 и нет «двоения»,
    которое давал блендинг с GFPGAN."""
    try:
        import io
        from PIL import Image, ImageFilter
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        img = img.filter(ImageFilter.UnsharpMask(radius=2, percent=max(0, percent), threshold=3))
        buf = io.BytesIO(); img.save(buf, format="PNG")
        return buf.getvalue()
    except Exception as exc:  # noqa: BLE001
        print(f"[sharpen] failed: {exc}")
        return None


def refine_swap(image_bytes: bytes, alpha: float = 0.3) -> bytes | None:
    """Доработка после свапа: GFPGAN чистит/красивит лицо, но «перерисовывает» →
    блендим его лишь на alpha (30%) с оригиналом свапа — чистим кожу, сохраняя
    сходство (ArcFace: чистый свап 0.835 → бленд 30% 0.808 при заметно красивее)."""
    gf = enhance_face(image_bytes)
    if not gf:
        return None
    try:
        import io
        from PIL import Image
        base = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        enh = Image.open(io.BytesIO(gf)).convert("RGB").resize(base.size, Image.LANCZOS)
        out = Image.blend(base, enh, max(0.0, min(1.0, alpha)))
        buf = io.BytesIO(); out.save(buf, format="PNG")
        return buf.getvalue()
    except Exception as exc:  # noqa: BLE001
        print(f"[refine] blend failed: {exc}")
        return None


def _face_swap_sync(target: bytes, face: bytes) -> bytes | None:
    if not _client:
        return None
    output = _client.run(FACE_SWAP_MODEL, input={
        "input_image": _data_uri(target),
        "swap_image": _data_uri(face),
    })
    return _read_output(output)


def face_swap(target: bytes, face: bytes) -> bytes | None:
    """Финальный шаг: переносит НАСТОЯЩЕЕ лицо гостя на сгенерированный кадр.
    Nano-banana ставит сцену/тело/одежду, swap гарантирует сходство 1:1.
    None при ошибке — тогда отдаём кадр без свапа (лучше, чем ничего)."""
    if not _client:
        return None
    import time
    for attempt in range(2):
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            fut = pool.submit(_face_swap_sync, target, face)
            try:
                return fut.result(timeout=120)
            except Exception as exc:  # noqa: BLE001
                if "429" in str(exc) and attempt == 0:
                    print("[replicate] face-swap 429, жду 25с")
                    time.sleep(25)
                    continue
                print(f"[replicate] face-swap failed: {exc}")
                return None
    return None


def _edit_sync(image_bytes: bytes, prompt: str) -> bytes | None:
    if not _client:
        return None
    output = _client.run(
        FLUX_MODEL,
        input={
            "prompt": prompt,
            "input_image": _data_uri(image_bytes),
            "output_format": "jpg",
            "output_quality": 92,
            "safety_tolerance": 2,
        },
    )
    return _read_output(output)


def edit_image(image_bytes: bytes, prompt: str) -> bytes | None:
    """image-to-image: вставить гостя (image_bytes) в сцену по инструкции prompt.
    Возвращает None при недоступности/ошибке/таймауте — не роняет пайплайн."""
    if not _client:
        return None
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        fut = pool.submit(_edit_sync, image_bytes, prompt)
        try:
            return fut.result(timeout=_IMAGE_TIMEOUT)
        except Exception as exc:  # noqa: BLE001
            print(f"[replicate] edit failed/timeout: {exc}")
            return None
