"""ArcFace-метрика сходства лиц (insightface buffalo_l).

Рекомендация старшего разработчика, п.1: объективная «линейка» сходства вместо
оценки на глаз. Локально, на CPU, ~сотни мс на кадр. Используется для:
  • гейта входного фото (размер лица, один в кадре, резкость) до генерации;
  • ранжирования сгенерированных вариантов по сходству с гостем;
  • отбраковки вариантов ниже порога.

Один и тот же детектор (SCRFD из buffalo_l) заодно точнее Haar-каскада в facecrop.py.
"""
from __future__ import annotations

import io
import threading
from typing import Optional

import numpy as np
from PIL import Image, ImageOps

import config

_app = None
_lock = threading.Lock()


def available() -> bool:
    """Пытается лениво инициализировать модель. False, если insightface/модель недоступны."""
    return _get_app() is not None


def _get_app():
    global _app
    if _app is None:
        with _lock:
            if _app is None:
                try:
                    from insightface.app import FaceAnalysis
                    app = FaceAnalysis(name=config.FACE_MODEL, providers=["CPUExecutionProvider"])
                    app.prepare(ctx_id=-1, det_size=(640, 640))
                    _app = app
                except Exception as exc:  # noqa: BLE001 — метрика не должна ронять сервис
                    print(f"[face_metric] инициализация не удалась: {exc}")
                    _app = False  # помечаем как «пробовали и не смогли»
    return _app or None


def _to_bgr(image_bytes: bytes) -> np.ndarray:
    img = ImageOps.exif_transpose(Image.open(io.BytesIO(image_bytes))).convert("RGB")
    return np.array(img)[:, :, ::-1]  # RGB -> BGR для insightface/cv2


def _faces(image_bytes: bytes):
    app = _get_app()
    if app is None:
        return []
    try:
        return app.get(_to_bgr(image_bytes))
    except Exception as exc:  # noqa: BLE001
        print(f"[face_metric] detect error: {exc}")
        return []


def _largest(faces):
    return max(faces, key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1])) if faces else None


def embedding(image_bytes: bytes) -> Optional[np.ndarray]:
    """512-мерный нормированный эмбеддинг крупнейшего лица (или None)."""
    f = _largest(_faces(image_bytes))
    return None if f is None else f.normed_embedding


def similarity(emb_a: Optional[np.ndarray], emb_b: Optional[np.ndarray]) -> float:
    """Косинусное сходство (оба эмбеддинга нормированы) в диапазоне ~[-1..1]."""
    if emb_a is None or emb_b is None:
        return 0.0
    return float(np.dot(emb_a, emb_b))


def _blur_var(image_bytes: bytes) -> float:
    """Дисперсия лапласиана — мера резкости (чем меньше, тем более размыто)."""
    try:
        import cv2
        arr = _to_bgr(image_bytes)
        gray = cv2.cvtColor(arr, cv2.COLOR_BGR2GRAY)
        return float(cv2.Laplacian(gray, cv2.CV_64F).var())
    except Exception:  # noqa: BLE001
        return 1e9  # не смогли посчитать — не блокируем по резкости


def check_input(image_bytes: bytes) -> tuple[bool, str, dict]:
    """Гейт входного фото гостя. (ok, причина-для-показа, инфо-для-логов)."""
    app = _get_app()
    if app is None:
        return True, "ok", {"gate": "disabled"}  # метрика недоступна — не мешаем флоу
    faces = _faces(image_bytes)
    if not faces:
        return False, "Лицо не распознано — встаньте прямо перед камерой.", {}
    if len(faces) > 1:
        return False, "В кадре несколько лиц — нужно, чтобы был один человек.", {"faces": len(faces)}
    f = faces[0]
    w = int(f.bbox[2] - f.bbox[0])
    info: dict = {"face_px": w, "det_score": round(float(f.det_score), 3)}
    if w < config.FACE_MIN_PX:
        return False, "Подойдите ближе — лицо слишком мелкое в кадре.", info
    pose = getattr(f, "pose", None)
    if pose is not None:
        yaw = abs(float(pose[1]))
        info["yaw_deg"] = round(yaw, 1)
        if yaw > config.FACE_MAX_YAW:
            return False, "Смотрите прямо в камеру — голова слишком повёрнута.", info
    blur = _blur_var(image_bytes)
    info["blur_var"] = round(blur, 1)
    if blur < config.FACE_MIN_BLUR:
        return False, "Кадр смазан — держите камеру ровно и переснимите.", info
    return True, "ok", info


def rank_variants(guest_bytes: bytes, variants: list[bytes]) -> list[tuple[int, float]]:
    """[(индекс_варианта, сходство_с_гостем)] по убыванию сходства. Пустой список,
    если метрика недоступна (тогда вызывающий сохраняет исходный порядок)."""
    if _get_app() is None:
        return []
    ref = embedding(guest_bytes)
    if ref is None:
        return []
    scored = [(i, similarity(ref, embedding(v))) for i, v in enumerate(variants)]
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored
