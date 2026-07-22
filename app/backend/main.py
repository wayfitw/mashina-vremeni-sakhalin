"""«Машина времени: Сахалин» — прототип (Этап 1/2).

Сквозной флоу: фото гостя → генерация 2–3 вариантов (Gemini Nano Banana) →
выбор → композитинг карточки с логотипами → печать (CUPS/lpr) + QR.
"""
from __future__ import annotations

import io
import json
import subprocess
import sys

# Windows: консоль по умолчанию cp1252, а логи/print содержат кириллицу —
# без этого обработчик ошибки сам падает с UnicodeEncodeError (500 вместо чистого 502).
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001 — не критично, если поток не поддерживает
        pass
import uuid
from pathlib import Path
from typing import Optional

import qrcode
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

import config
import gemini_client
import compositor
import facecrop
import face_metric

app = FastAPI(title="Машина времени: Сахалин — прототип")


@app.on_event("startup")
def _warm_face_metric():
    # прогрев ArcFace-модели, чтобы первый гость не ждал загрузку onnx
    if config.FACE_GATE_ENABLED or config.FACE_RANK_ENABLED:
        face_metric.available()

LOCATIONS = json.loads((config.BASE_DIR / "locations.json").read_text(encoding="utf-8"))
FRONTEND = config.BASE_DIR.parent / "frontend"


def _save(data: bytes, name: str) -> str:
    (config.OUTPUT / name).write_bytes(data)
    return name


# ---------------- API ----------------

@app.get("/api/health")
def health():
    return {"ok": True, "stub_mode": config.STUB_MODE, "model": config.GEMINI_IMAGE_MODEL,
            "variants": config.VARIANTS, "print_enabled": config.PRINT_ENABLED}


@app.get("/api/locations")
def locations():
    return [
        {"id": v["id"], "title": v["title"], "subtitle": v["subtitle"], "enabled": v["enabled"]}
        for v in LOCATIONS.values()
    ]


@app.post("/api/check-photo")
async def check_photo(photo: UploadFile = File(...)):
    """Живая проверка кадра до генерации (для экрана съёмки): ok + причина."""
    data = await photo.read()
    ok, reason, info = face_metric.check_input(data)
    return {"ok": ok, "reason": reason, "info": info}


@app.post("/api/generate")
async def generate(location: str = Form(...), photo: UploadFile = File(...),
                   outfit: str = Form("male")):
    loc = LOCATIONS.get(location)
    if not loc or not loc["enabled"]:
        raise HTTPException(400, "Локация недоступна")

    guest_bytes = await photo.read()

    # гейт входного фото: плохой кадр → просьба переснять, а не плохая карточка
    if config.FACE_GATE_ENABLED:
        ok, reason, info = face_metric.check_input(guest_bytes)
        print(f"[gate] ok={ok} {info}")
        if not ok:
            raise HTTPException(422, reason)

    # СЫРОЙ кроп лица для face-swap — истинная идентичность гостя, ДО GFPGAN
    # (GFPGAN «причёсывает» лицо и снижает сходство, поэтому свап опирается на сырое)
    face_raw, _ = facecrop.crops(guest_bytes)

    # улучшение входа с вебкамеры: GFPGAN чистит шум/блюр и делает лицо красивее
    if config.FACE_ENHANCE_ENABLED:
        import replicate_client
        enhanced = replicate_client.enhance_face(guest_bytes)
        if enhanced:
            guest_bytes = enhanced
            print("[enhance] лицо улучшено через GFPGAN")

    # два кадра гостя: крупное лицо (для точных черт) + корпус (для телосложения)
    face_png, body_png = facecrop.crops(guest_bytes)

    # отладка: сохраняем, что реально уходит в модель (смотреть при проблемах качества)
    debug_id = uuid.uuid4().hex[:6]
    _save(guest_bytes, f"dbg_{debug_id}_raw.jpg")
    _save(face_png, f"dbg_{debug_id}_face.png")
    _save(body_png, f"dbg_{debug_id}_body.png")

    from PIL import Image, ImageOps
    ref_path = config.REFERENCES / loc["reference"]
    reference = None
    if ref_path.exists():
        rimg = ImageOps.exif_transpose(Image.open(ref_path)).convert("RGB")
        rbuf = io.BytesIO(); rimg.save(rbuf, format="PNG"); reference = rbuf.getvalue()

    # промпты с разными нарядами по выбранному образу (девушкам — розовый/белый)
    outfits = config.OUTFITS.get(outfit, [config.DEFAULT_OUTFIT])
    gender = "young woman" if outfit == "female" else "young man"

    if config.GEN_MODE == "composite" and reference:
        # основной режим: фон не генерируется — человек вклеивается в эталон
        import person_composite
        variants = []
        for i in range(config.VARIANTS):
            out = person_composite.generate_composite(
                face_png, body_png, reference,
                outfits[i % len(outfits)], loc.get("anchor", {}))
            if out:
                variants.append(out)
        if not variants:
            raise HTTPException(502, "Генерация не удалась (composite). Попробуйте ещё раз.")
    else:
        prompts = [loc["prompt"].replace("{OUTFIT}", outfits[i % len(outfits)]).replace("{GENDER}", gender)
                   for i in range(config.VARIANTS)]
        try:
            variants = gemini_client.generate_variants(prompts, face_png, reference,
                                                       body_png=body_png, swap_face=face_raw)
        except gemini_client.GenerationError as exc:
            raise HTTPException(502, str(exc))

    # ранжирование по сходству с гостем (ArcFace): лучший кадр — первым; слабые
    # (ниже порога) отбраковываются, но хотя бы один вариант всегда остаётся.
    sims: list = [None] * len(variants)
    if config.FACE_RANK_ENABLED:
        ranking = face_metric.rank_variants(guest_bytes, variants)
        if ranking:
            kept = [(i, s) for i, s in ranking if s >= config.FACE_SIM_THRESHOLD] or ranking[:1]
            variants = [variants[i] for i, _ in kept]
            sims = [round(s, 3) for _, s in kept]
            print(f"[rank] similarities: {[round(s, 3) for _, s in ranking]} → оставлено {len(variants)}")

    session_id = uuid.uuid4().hex[:8]
    out = []
    for i, data in enumerate(variants):
        name = f"gen_{session_id}_{i}.png"
        _save(data, name)
        out.append({"id": name, "url": f"/files/{name}", "similarity": sims[i] if i < len(sims) else None})

    return {"session": session_id, "location": loc["title"], "variants": out,
            "stub_mode": config.STUB_MODE}


@app.post("/api/card")
def make_card(variant_id: str = Form(...)):
    src = config.OUTPUT / variant_id
    if not src.exists():
        raise HTTPException(404, "Вариант не найден")
    card = compositor.build_card(src.read_bytes())
    card_id = f"card_{uuid.uuid4().hex[:8]}.png"
    _save(card, card_id)

    # QR на цифровую версию
    qr_url = f"{config.PUBLIC_BASE_URL}/d/{card_id}"
    qr = qrcode.make(qr_url)
    qbuf = io.BytesIO(); qr.save(qbuf, format="PNG")
    qr_id = f"qr_{card_id}"
    _save(qbuf.getvalue(), qr_id)

    return {"card_id": card_id, "card_url": f"/files/{card_id}",
            "qr_url": f"/files/{qr_id}", "digital_url": qr_url}


@app.post("/api/print")
def print_card(card_id: str = Form(...)):
    path = config.OUTPUT / card_id
    if not path.exists():
        raise HTTPException(404, "Карточка не найдена")
    if not config.PRINT_ENABLED:
        return {"printed": False, "reason": "Печать выключена (PRINT_ENABLED=0). Карточка сохранена.",
                "path": str(path)}
    cmd = ["lpr"]
    if config.PRINT_PRINTER:
        cmd += ["-P", config.PRINT_PRINTER]
    cmd.append(str(path))
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=30)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, f"Ошибка печати: {exc}")
    return {"printed": True, "printer": config.PRINT_PRINTER or "default"}


@app.get("/d/{card_id}", response_class=HTMLResponse)
def digital(card_id: str):
    if not (config.OUTPUT / card_id).exists():
        raise HTTPException(404, "Не найдено")
    return f"""<!doctype html><html lang=ru><head><meta charset=utf-8>
<meta name=viewport content='width=device-width,initial-scale=1'>
<title>Я на Сахалине</title>
<style>body{{margin:0;background:#0b5563;color:#fff;font-family:-apple-system,Arial,sans-serif;text-align:center}}
img{{max-width:92%;margin:24px auto;border-radius:12px;box-shadow:0 8px 30px rgba(0,0,0,.4)}}
a{{display:inline-block;margin:12px;padding:14px 24px;background:#fff;color:#0b5563;border-radius:10px;text-decoration:none;font-weight:700}}</style>
</head><body><h2>Ваша карточка · Машина времени: Сахалин</h2>
<img src='/files/{card_id}'><br><a href='/files/{card_id}' download>Скачать фото</a></body></html>"""


# ---------------- Статика ----------------

app.mount("/files", StaticFiles(directory=str(config.OUTPUT)), name="files")
if FRONTEND.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND), html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
