"""Отправка фото-карточки гостю по email (Яндекс SMTP)."""
from __future__ import annotations

import smtplib
import ssl
from email.message import EmailMessage
from pathlib import Path

import config


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
        "Форум «Нефть и Газ Сахалина 2026»\n"
        "IQTER — Интеллектуальные Терминалы\n",
        charset="utf-8",
    )
    msg.add_attachment(
        card_path.read_bytes(),
        maintype="image",
        subtype="png",
        filename="ya_na_sakhaline.png",
    )

    ctx = ssl.create_default_context()
    try:
        # Сначала пробуем SSL на 465
        with smtplib.SMTP_SSL(config.SMTP_HOST, config.SMTP_PORT, context=ctx) as s:
            s.login(config.SMTP_USER, config.SMTP_PASS)
            s.send_message(msg)
    except Exception:
        # Fallback: STARTTLS на 587
        with smtplib.SMTP(config.SMTP_HOST, 587) as s:
            s.ehlo()
            s.starttls(context=ctx)
            s.login(config.SMTP_USER, config.SMTP_PASS)
            s.send_message(msg)

    return {"sent": True, "reason": None}
