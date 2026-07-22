"""Конфигурация прототипа «Машина времени: Сахалин».

Все параметры читаются из переменных окружения (.env). Секретов в коде нет.
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
ASSETS = BASE_DIR / "assets"
REFERENCES = ASSETS / "references"
LOGOS = ASSETS / "logos"
OUTPUT = ASSETS / "output"
for _d in (REFERENCES, LOGOS, OUTPUT):
    _d.mkdir(parents=True, exist_ok=True)


def _load_dotenv() -> None:
    """Минимальный парсер .env без внешних зависимостей."""
    env_path = BASE_DIR / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv()

# --- Провайдер генерации (Gemini «Nano Banana») ---
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
# «Nano Banana» = gemini-2.5-flash-image; «Nano Banana Pro» = gemini-3-pro-image-preview
GEMINI_IMAGE_MODEL = os.environ.get("GEMINI_IMAGE_MODEL", "gemini-2.5-flash-image").strip()

# Сколько вариантов генерировать на один запрос (гость выбирает лучший)
VARIANTS = int(os.environ.get("VARIANTS", "3"))

# Образы (одежда) по выбору гостя — подставляются в промпт вместо {OUTFIT}.
# Для нескольких вариантов перебираются по кругу (девушкам — розовый и белый).
OUTFITS = {
    "female": [
        "a stylish modern women's athletic tracksuit in soft pink with clean white sneakers, beautiful and flattering",
        "a stylish modern women's athletic tracksuit in clean white with white sneakers, beautiful and flattering",
    ],
    "male": [
        "a plain white t-shirt, neutral dark trousers and casual gray sneakers",
        "a plain white t-shirt, neutral beige trousers and casual white sneakers",
    ],
}
DEFAULT_OUTFIT = "neutral modern casual outdoor clothing in muted colors"

# --- Резервный провайдер (Replicate, FLUX Kontext Pro) — ADR-6 ---
# Токен из https://replicate.com/account/api-tokens. Пусто → резерв выключен.
REPLICATE_API_TOKEN = os.environ.get("REPLICATE_API_TOKEN", "").strip()

# Модель генерации на Replicate. По итогам A/B-теста (18.07.2026) —
# google/nano-banana-2 в 2K: лучшее лицо БЕЗ face-swap (см. _ab_*.jpg).
# Альтернативы: bytedance/seedream-4, google/nano-banana-pro.
# По A/B с ArcFace-метрикой (21.07.2026) bytedance/seedream-4.5 держит лицо
# заметно лучше nano-banana (raw 0.74 vs 0.31; со свапом 0.85 vs 0.82) — дефолт.
NANO_BANANA_MODEL = os.environ.get(
    "NANO_BANANA_MODEL",
    "bytedance/seedream-4.5:9fe3b8282dcb9d9063b05e33210a1432801f7c5a6641db944baefcec4886761a").strip()
NANO_BANANA_RESOLUTION = os.environ.get("NANO_BANANA_RESOLUTION", "2K").strip()

# Face-swap (inswapper) работает в 128×128 → «восковое» лицо. ВЫКЛЮЧЕН по умолчанию;
# включать только как аварийный вариант, если генерация теряет сходство.
FACE_SWAP_ENABLED = os.environ.get("FACE_SWAP", "0").strip() in ("1", "true", "yes")

# Улучшение входного фото гостя через GFPGAN (для вебкамеры: чистит шум/блюр,
# делает лицо резче и красивее). Небольшой минус к ArcFace, но картинка лучше.
FACE_ENHANCE_ENABLED = os.environ.get("FACE_ENHANCE", "0").strip() in ("1", "true", "yes")

# Режим генерации:
#   composite — фон НЕ генерируется: генерим только человека, вырезаем и вклеиваем
#               в эталон (фон гарантированно неизменен). Основной режим.
#   edit      — модель редактирует эталон целиком (фон может «уплывать»). Резерв.
GEN_MODE = os.environ.get("GEN_MODE", "composite").strip()

# --- Печать ---
# По умолчанию печать ВЫКЛючена (карточка просто сохраняется) — чтобы не печатать случайно.
# Включить реальную печать через CUPS/lpr: PRINT_ENABLED=1, PRINT_PRINTER=<имя из `lpstat -p`>
PRINT_ENABLED = os.environ.get("PRINT_ENABLED", "0").strip() in ("1", "true", "yes")
PRINT_PRINTER = os.environ.get("PRINT_PRINTER", "").strip()

# Публичный базовый URL для QR (в проде — домен; локально — адрес мини-ПК)
PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "http://localhost:8000").rstrip("/")

# Срок хранения цифровой версии (часы) — для автоудаления (в проде)
DIGITAL_TTL_HOURS = int(os.environ.get("DIGITAL_TTL_HOURS", "72"))

# --- ArcFace-метрика сходства лиц (insightface) — рекомендация №1 ---
FACE_MODEL = os.environ.get("FACE_MODEL", "buffalo_l").strip()
# Гейт входного фото гостя (размер лица, один в кадре, резкость) до генерации.
FACE_GATE_ENABLED = os.environ.get("FACE_GATE", "1").strip() in ("1", "true", "yes")
# Ранжирование/отбраковка сгенерированных вариантов по сходству с гостем.
FACE_RANK_ENABLED = os.environ.get("FACE_RANK", "1").strip() in ("1", "true", "yes")
FACE_MIN_PX = int(os.environ.get("FACE_MIN_PX", "512"))          # мин. ширина лица (реком. 512)
FACE_MAX_YAW = float(os.environ.get("FACE_MAX_YAW", "25"))       # макс. поворот головы, град
FACE_MIN_BLUR = float(os.environ.get("FACE_MIN_BLUR", "40"))     # мин. резкость (var лапласиана)
FACE_SIM_THRESHOLD = float(os.environ.get("FACE_SIM_THRESHOLD", "0.45"))  # порог отбраковки варианта

# Демо-режим (заглушки) — только когда НИ ОДИН провайдер не настроен
STUB_MODE = not (bool(GEMINI_API_KEY) or bool(REPLICATE_API_TOKEN))
