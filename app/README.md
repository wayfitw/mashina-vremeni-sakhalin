# «Машина времени: Сахалин» — прототип

Сквозной AI фото-киоск: фото гостя → генерация 2–3 фотореалистичных вариантов в локации Сахалина → выбор → карточка с логотипами партнёров → печать (CUPS) + QR.

Сейчас включена одна локация — **маяк Анива** (остальные в `backend/locations.json`, флаг `enabled`).

## Быстрый запуск

**Windows:**
```bat
app\run.bat
```

**macOS / Linux:**
```bash
app/run.sh
```

Скрипт сам создаёт venv, ставит зависимости и поднимает сервер. Открыть в браузере: **http://localhost:8000**

Требуется **Python 3.10+** и интернет (при первом запуске автоматически скачиваются модели insightface `buffalo_l` для метрики сходства лиц).

## Ключи (backend/.env)

Скопируй `backend/.env.example` → `backend/.env` (скрипт делает это сам при первом запуске) и заполни:

| Параметр | Назначение |
|---|---|
| `REPLICATE_API_TOKEN` | **Основной провайдер генерации.** Токен из [replicate.com/account](https://replicate.com/account/api-tokens). Модель по умолчанию — `bytedance/seedream-4.5` (лучшее сходство лица по A/B). **Без токена — демо-режим** (заглушки из фото, флоу работает). Генерация платная (оплата с баланса Replicate). |
| `NANO_BANANA_MODEL` | Модель генерации на Replicate. По умолчанию `bytedance/seedream-4.5:<version>`. Альтернатива: `google/nano-banana-2`. |
| `FACE_SWAP` | `1` — переносить настоящее лицо гостя (inswapper) поверх генерации для точного сходства; `0` — только генерация. |
| `GEMINI_API_KEY` | Необязательно. Запасной провайдер Google (нужен биллинг). |
| `VARIANTS` | Сколько вариантов генерировать (по умолчанию 3). |
| `PRINT_ENABLED` / `PRINT_PRINTER` | Печать через `lpr` (CUPS, только macOS/Linux). `0` = карточка только сохраняется. |
| `PUBLIC_BASE_URL` | База для QR. Локально `http://localhost:8000`. |

> Порт по умолчанию — **8000**. Если занят, поменяй в `run.bat`/`run.sh` и в `PUBLIC_BASE_URL`.

## Как устроена генерация

1. Фото гостя проходит **гейт качества** (insightface): лицо от N px, поворот, резкость, одно лицо в кадре — иначе просьба переснять.
2. Вырезаются два кадра гостя: лицо (для черт) + корпус (для телосложения).
3. Вместе с эталонным фото локации (`backend/assets/references/aniva_clean.png`) уходят в модель (Seedream 4.5).
4. Опционально face-swap (реальное лицо 1:1), затем варианты **ранжируются по сходству** (ArcFace) — гость видит лучшие.
5. Выбор → карточка с логотипами + QR.

## Фоновое видео (необязательно)

`frontend/media/intro.mp4` — зацикленный фон сайта — **не в репозитории** (большой файл, в `.gitignore`). Без него сайт работает, фон — тёмный/постер. Чтобы вернуть: положи свой `intro.mp4` в `frontend/media/`.

## Структура

```
backend/
  main.py            FastAPI: /api/generate, /api/card, /api/print, /d/{id}
  gemini_client.py   шлюз генерации (цепочка провайдеров + stub)
  replicate_client.py Replicate: Seedream/nano-banana, face-swap
  facecrop.py        кропы лица/корпуса
  face_metric.py     ArcFace: гейт входа + ранжирование по сходству
  compositor.py      сборка карточки (фото + логотипы + подпись)
  person_composite.py альтернативный composite-режим (вклейка в реальное фото)
  config.py          конфигурация из .env
  locations.json     локации и промпты
  assets/            references / logos / output
frontend/
  index.html app.js styles.css   киоск-флоу
```
