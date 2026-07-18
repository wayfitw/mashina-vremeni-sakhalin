# «Машина времени: Сахалин» — прототип

Рабочий сквозной прототип (Этап 1–2): фото гостя → генерация 2–3 вариантов (Gemini «Nano Banana») → выбор → карточка с логотипами партнёров → печать (CUPS) + QR.

Сейчас включена одна локация — **маяк Анива** (остальные в `locations.json`, флаг `enabled`).

## Запуск

```bash
./run.sh
```
Открыть в браузере: **http://localhost:8000**

Для iPad: открыть тот же адрес по IP Mac в сети (напр. `http://192.168.x.x:8000`), Safari → «Гид-доступ».

## Настройка (backend/.env)

Скопируй `backend/.env.example` → `backend/.env` и заполни:

| Параметр | Назначение |
|---|---|
| `GEMINI_API_KEY` | Ключ из [Google AI Studio](https://aistudio.google.com/apikey). **Без ключа — демо-режим** (заглушки из фото, флоу работает). |
| `GEMINI_IMAGE_MODEL` | `gemini-2.5-flash-image` (Nano Banana) или `gemini-3-pro-image-preview` (Nano Banana Pro). |
| `VARIANTS` | Сколько вариантов генерировать (по умолчанию 3). |
| `PRINT_ENABLED` | `0` — карточка только сохраняется; `1` — реально печатать через `lpr`. |
| `PRINT_PRINTER` | Имя принтера из `lpstat -p` (пусто = принтер по умолчанию). |

## Референс локации (для лучшего качества)

Положи фото реального маяка Анива в `backend/assets/references/aniva.jpg` — оно пойдёт вторым изображением в image-to-image. Без него генерация идёт по текстовому промпту.

## Логотипы партнёров

`backend/assets/logos/*.png` (до 3, с прозрачностью). Сейчас — плейсхолдеры `01_partner.png`, `02_partner.png`. Логотипы накладываются **детерминированно** (не генерируются ИИ — ADR-1).

## Структура

```
backend/
  main.py           FastAPI: /api/generate, /api/card, /api/print, /d/{id}
  gemini_client.py  шлюз генерации (Gemini + stub), 2–3 варианта параллельно
  compositor.py     сборка карточки (фото + логотипы + подпись)
  config.py         конфигурация из .env
  locations.json    локации и промпты
  assets/           references / logos / output
frontend/
  index.html app.js styles.css   киоск-флоу под iPad
```

## Что дальше (соответствие задачам)
- Вставить `GEMINI_API_KEY`, протестировать реальную генерацию на маяке — TASK-0006.
- Зафиксировать лучший промпт по итогам теста — TASK-0003.
- Включить остальные локации (`enabled: true`) — TASK-0204.
- Реальная печать на сублимационном принтере — TASK-0303.
