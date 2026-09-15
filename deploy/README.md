# Развёртывание на VPS (AEZA)

Веб-приложение (генерация + карточки + QR) разворачивается в облаке; камера и
принтер остаются на физическом стенде.

## Требования
- Ubuntu 22.04/24.04, 2+ CPU, **4 ГБ RAM** (insightface/onnxruntime), 10 ГБ диска.
- GPU не нужен: генерация идёт через Replicate API, локально считается только
  метрика лица (ArcFace на CPU).
- Домен, направленный A-записью на IP сервера — **обязателен** (см. HTTPS ниже).

## 1. Установка

```bash
ssh root@IP_СЕРВЕРА
apt-get update && apt-get install -y git
git clone https://github.com/wayfitw/sakhalin-energy-photo.git /opt/sakhalin-energy-photo
bash /opt/sakhalin-energy-photo/deploy/install.sh
```

Скрипт ставит системные пакеты, создаёт venv, ставит зависимости, поднимает
systemd-сервис `sakhalin-energy` на `127.0.0.1:8000`.

## 2. Ключи

```bash
nano /opt/sakhalin-energy-photo/app/backend/.env
```

| Параметр | Значение |
|---|---|
| `REPLICATE_API_TOKEN` | токен с replicate.com — **без него демо-режим (заглушки)** |
| `PUBLIC_BASE_URL` | `https://ваш-домен` — иначе QR будет вести на localhost |
| `PRINT_ENABLED` | `0` на сервере (принтер стоит на стенде, не здесь) |

После правки: `systemctl restart sakhalin-energy`

### Режим генерации и порог лица

Значения по умолчанию в коде — не те, с которыми киоск работал на форуме.
Свежий `.env` из примера уже содержит рабочие, но если правите вручную,
проверьте два параметра:

| Параметр | Рабочее значение | Что будет иначе |
|---|---|---|
| `GEN_MODE` | `edit` | При `composite` гость вклеивается в эталон как есть. Всё, что есть на эталоне локации — посторонние люди, водяные знаки фотобанка, — попадёт на карточку каждому гостю. |
| `FACE_MIN_PX` | `250` | По умолчанию 512. Вебка столько почти не выдаёт, и гость получает «Подойдите ближе — лицо слишком мелкое в кадре». |

Там же включаются `FACE_ENHANCE`, `FACE_DESHADOW` и `FACE_SWAP` — без них
сходство с гостем заметно ниже.

## 3. nginx + HTTPS

```bash
cp /opt/sakhalin-energy-photo/deploy/nginx.conf /etc/nginx/sites-available/sakhalin-energy
nano /etc/nginx/sites-available/sakhalin-energy      # заменить server_name на домен
ln -s /etc/nginx/sites-available/sakhalin-energy /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx

apt-get install -y certbot python3-certbot-nginx
certbot --nginx -d ваш-домен
```

> ⚠️ **HTTPS обязателен.** Браузеры дают доступ к веб-камере (`getUserMedia`)
> только на `https://` или `localhost`. По голому `http://IP` съёмка с камеры
> работать не будет — гость увидит «камера недоступна».

## 4. Проверка

```bash
curl -s localhost:8000/api/health          # {"ok":true,...}
systemctl status sakhalin-energy
journalctl -u sakhalin-energy -f           # логи генерации
```

Открыть `https://ваш-домен` — должен появиться экран «Сахалинская Энергия».

## Обновление

```bash
cd /opt/sakhalin-energy-photo && git pull
app/backend/.venv/bin/pip install -q -r app/backend/requirements.txt
systemctl restart sakhalin-energy
```

## Замечания по эксплуатации
- **Генерация платная** (Replicate) — следите за балансом, иначе `/api/generate`
  начнёт отдавать ошибки.
- Одна генерация занимает 2–5 минут (3 варианта), поэтому в nginx выставлены
  таймауты 600 с. Не уменьшайте их.
- Результаты копятся в `app/backend/assets/output/` — периодически чистить.
- Печать (`lpr`/CUPS) работает только там, где физически подключён принтер.
