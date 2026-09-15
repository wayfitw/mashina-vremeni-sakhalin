# app — киоск «Сахалинская Энергия»

Обзор проекта, настройки и запуск — в [README в корне](../README.md).
Развёртывание на сервере — в [deploy/README.md](../deploy/README.md).

## Быстрый запуск

```bat
app\run.bat
```

```bash
app/run.sh
```

Скрипт создаёт venv, ставит зависимости и поднимает сервер на **http://localhost:8000**.
Нужен **Python 3.10+** и интернет: при первом запуске скачиваются модели insightface `buffalo_l`.
Камера в браузере работает только на `localhost` или по `https://`.

## Структура

```
backend/
  main.py             FastAPI: генерация, карточка, QR, почта, очередь печати
  gemini_client.py    шлюз генерации (цепочка провайдеров + демо-режим)
  replicate_client.py Replicate: nano-banana-pro / seedream, face-swap
  facecrop.py         кропы лица и корпуса
  face_metric.py      ArcFace: проверка входного кадра и ранжирование по сходству
  compositor.py       карточка: фото + подпись + логотип + поздравление
  person_composite.py режим composite (вклейка в реальное фото)
  email_client.py     отправка карточки гостю
  config.py           конфигурация из .env
  locations.json      локации и промпты
  assets/
    references/       эталонные фото локаций
    logos/            знаки для интерфейса (белые) и _brand_cap.png для худи
    logos_card/       знаки для карточки (цветные)
    output/           кадры и карточки гостей (не в git)
frontend/
  index.html app.js styles.css   киоск-флоу
  media/              контур острова и круглый знак для фона
```
