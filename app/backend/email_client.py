"""Отправка фото-карточки гостю по email (Яндекс SMTP)."""
from __future__ import annotations

import smtplib
import ssl
from email.message import EmailMessage
from pathlib import Path

import config

# Попыток две (465, затем 587), поэтому в худшем случае гость ждёт вдвое дольше.
# 8 сек хватает на живое соединение и держит худший случай в пределах 16 сек.
SMTP_TIMEOUT = 8


def send_card(to_email: str, card_path: Path) -> dict:
    """Отправляет карточку как вложение. Возвращает {"sent": bool, "reason": str|None}."""
    if not config.SMTP_PASS:
        # текст видит гость на экране киоска — без внутренних деталей
        return {"sent": False, "reason": "Отправка на почту пока недоступна — заберите фото по QR-коду"}

    msg = EmailMessage()
    msg["Subject"] = "Ваша карточка · «Я на Сахалине»"
    msg["From"] = f"Я на Сахалине <{config.SMTP_FROM}>"
    msg["To"] = to_email
    msg.set_content(
        "Привет!\n\n"
        "Ваша персональная фото-карточка с AI-фотоинсталляции «Я на Сахалине» "
        "прикреплена к этому письму.\n\n"
        # тот же форум, что в подвале самой карточки (locations.json → card_footer)
        "Форумы «Энергия Сахалина» и «Острова роста», 2026 г.\n",
        charset="utf-8",
    )
    msg.add_attachment(
        card_path.read_bytes(),
        maintype="image",
        subtype="png",
        filename="ya_na_sakhaline.png",
    )

    ctx = ssl.create_default_context()
    # Таймаут обязателен. Без него, когда порт SMTP закрыт (а на нашем хостинге он
    # закрыт наглухо — проверено 26.07.2026: 25, 465 и 587 уходят в таймаут ко всем
    # почтовым провайдерам), connect висит несколько минут, и гость у киоска всё
    # это время смотрит на «Отправляем…». Плюс попыток две, то есть вдвое дольше.
    first_error = None
    try:
        with smtplib.SMTP_SSL(config.SMTP_HOST, config.SMTP_PORT,
                              context=ctx, timeout=SMTP_TIMEOUT) as s:
            s.login(config.SMTP_USER, config.SMTP_PASS)
            s.send_message(msg)
        return {"sent": True, "reason": None}
    except Exception as exc:  # noqa: BLE001
        first_error = exc

    try:
        with smtplib.SMTP(config.SMTP_HOST, 587, timeout=SMTP_TIMEOUT) as s:
            s.ehlo()
            s.starttls(context=ctx)
            s.login(config.SMTP_USER, config.SMTP_PASS)
            s.send_message(msg)
        return {"sent": True, "reason": None}
    except Exception as exc:  # noqa: BLE001
        # Обе попытки в лог: без этого причина (закрытый порт, неверный пароль,
        # запрет на вход по паролю приложения) неотличимы друг от друга.
        print(f"[email] SSL:465 не сработал: {type(first_error).__name__}: {first_error}")
        print(f"[email] STARTTLS:587 не сработал: {type(exc).__name__}: {exc}")
        if isinstance(exc, smtplib.SMTPAuthenticationError):
            reason = "Почта не настроена — обратитесь к организатору"
        else:
            reason = "Не получилось отправить письмо — заберите фото по QR-коду"
        return {"sent": False, "reason": reason}
