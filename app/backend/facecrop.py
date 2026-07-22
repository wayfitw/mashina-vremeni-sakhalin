"""Авто-обрезка фото гостя до «голова + плечи».

Убирает лишнее из кадра (комната, предметы, посторонние), даже если гость стоял
далеко — модель получает чистый крупный портрет и точно берёт лицо человека.
Если лицо не найдено — центральная вертикальная обрезка (fallback).
"""
from __future__ import annotations

import io

from PIL import Image, ImageOps

# opencv может быть недоступен/битый — тогда работаем без детекции лица (центр-кроп)
try:
    import numpy as np
    import cv2
    _CASCADE = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    if _CASCADE.empty():
        _CASCADE = None
except Exception:  # noqa: BLE001
    cv2 = None
    _CASCADE = None


def crops(image_bytes: bytes) -> tuple[bytes, bytes]:
    """Возвращает (крупное_лицо, корпус_по_пояс) как два PNG.
    Лицо отдельно — чтобы модель точно скопировала черты; корпус — чтобы видела
    реальное телосложение. Оба уходят в модель вместе с эталоном сцены."""
    img = ImageOps.exif_transpose(Image.open(io.BytesIO(image_bytes))).convert("RGB")
    W, H = img.size

    faces = []
    if _CASCADE is not None:
        gray = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2GRAY)
        faces = _CASCADE.detectMultiScale(gray, scaleFactor=1.15, minNeighbors=5,
                                          minSize=(int(min(W, H) * 0.06), int(min(W, H) * 0.06)))
    if len(faces):
        x, y, w, h = max(faces, key=lambda f: f[2] * f[3])
        cx, cy = x + w / 2, y + h / 2
        # 1) крупное лицо: теснее кадрируем (лицо крупнее в референсе → выше сходство)
        fw = max(w * 1.7, 512 if W >= 512 else W)
        fh = fw * 1.25
        face_box = (max(0, int(cx - fw / 2)), max(0, int(cy - fh * 0.45)),
                    min(W, int(cx + fw / 2)), min(H, int(cy + fh * 0.55)))
        face_img = img.crop(face_box)
    else:
        # лицо не нашли — верхняя центральная треть
        face_img = img.crop((int(W * 0.25), 0, int(W * 0.75), int(H * 0.5)))

    # крупный резкий эталон лица: апскейл до мин. 1024 px по длинной стороне
    # (рек. ⑤ — реф от 1024 px заметно улучшает сходство)
    _MIN_FACE = 1024
    if max(face_img.size) < _MIN_FACE:
        _s = _MIN_FACE / max(face_img.size)
        face_img = face_img.resize((int(face_img.width * _s), int(face_img.height * _s)), Image.LANCZOS)

    body_png = crop_to_face(image_bytes)          # корпус по пояс (существующая логика)
    fbuf = io.BytesIO(); face_img.save(fbuf, format="PNG")
    return fbuf.getvalue(), body_png


def crop_to_face(image_bytes: bytes) -> bytes:
    """Возвращает PNG с обрезкой до головы и плеч. Ориентация — вертикальная 3:4."""
    img = ImageOps.exif_transpose(Image.open(io.BytesIO(image_bytes))).convert("RGB")
    W, H = img.size

    faces = []
    if _CASCADE is not None:
        gray = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2GRAY)
        faces = _CASCADE.detectMultiScale(gray, scaleFactor=1.15, minNeighbors=5,
                                          minSize=(int(min(W, H) * 0.06), int(min(W, H) * 0.06)))

    if len(faces):
        # самое крупное лицо
        x, y, w, h = max(faces, key=lambda f: f[2] * f[3])
        cx, cy = x + w / 2, y + h / 2
        # рамка «по пояс»: модель должна ВИДЕТЬ телосложение гостя, иначе выдумает его.
        # Лицо — в верхней четверти кадра, ниже — плечи/грудь/талия.
        box_w = w * 4.2
        box_h = box_w * 4 / 3            # вертикаль 3:4
        left = cx - box_w / 2
        top = cy - box_h * 0.22          # чуть места над головой, основное — корпус ниже
        # защита от «мыла»: если вырезка получается слишком мелкой (< 640 px по ширине),
        # расширяем её до минимума — лучше больше фона, чем размазанное лицо
        min_w = 640
        if box_w < min_w and W >= min_w:
            grow = min_w / box_w
            box_w *= grow; box_h *= grow
            left = cx - box_w / 2
            top = cy - box_h * 0.22
    else:
        # fallback: центральная вертикальная область, верхняя часть кадра
        box_w = min(W, H * 3 / 4)
        box_h = box_w * 4 / 3
        left = (W - box_w) / 2
        top = max(0, H * 0.05)

    # клампим в границы изображения
    left = max(0, min(left, W - 1))
    top = max(0, min(top, H - 1))
    right = min(W, left + box_w)
    bottom = min(H, top + box_h)
    crop = img.crop((int(left), int(top), int(right), int(bottom)))

    buf = io.BytesIO()
    crop.save(buf, format="PNG")
    return buf.getvalue()
