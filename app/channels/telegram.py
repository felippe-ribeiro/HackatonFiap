"""Adapter de Telegram (diferencial: canal de mensageria real).

Dois modos, mesma lógica de negócio:
- **webhook**  : POST /webhook/telegram  (para deploy com URL pública)
- **polling**  : `python -m app.channels.telegram`  (local, sem URL pública)

Migração a partir do simulador web: o simulador já chama `runner.responder(...)`.
Aqui só traduzimos o update do Telegram para essa mesma chamada.
"""

from __future__ import annotations

import time

import httpx
from fastapi import APIRouter, Request

from app.agent.runner import responder
from app.config import settings
from app.logging_conf import get_logger

log = get_logger("channel.telegram")
router = APIRouter(tags=["telegram"])

_API = "https://api.telegram.org/bot{token}/{method}"


def _send_message(chat_id: int | str, text: str) -> None:
    if not settings.telegram_bot_token:
        log.warning("TELEGRAM_BOT_TOKEN ausente — resposta não enviada")
        return
    url = _API.format(token=settings.telegram_bot_token, method="sendMessage")
    try:
        httpx.post(url, json={"chat_id": chat_id, "text": text}, timeout=15)
    except Exception:
        log.exception("falha ao enviar mensagem ao Telegram")


def _handle_update(update: dict) -> None:
    msg = update.get("message") or update.get("edited_message") or {}
    chat = msg.get("chat") or {}
    chat_id = chat.get("id")
    text = (msg.get("text") or "").strip()
    if not chat_id or not text:
        return

    nome = (chat.get("first_name") or "").strip() or None
    if text.startswith("/start"):
        _send_message(
            chat_id,
            "Oi! Aqui é a Lária, da Aurora Imóveis 🏠 Me conta o que você procura: "
            "comprar, alugar ou investir?",
        )
        return

    out = responder(f"tg-{chat_id}", text, canal="telegram", nome=nome)
    _send_message(chat_id, out.reply)
    log.info(
        "mensagem telegram processada",
        extra={"event": "telegram:msg", "lead_id": out.lead_id},
    )


@router.post("/webhook/telegram")
async def telegram_webhook(request: Request):
    update = await request.json()
    _handle_update(update)
    return {"ok": True}


# --------------------------------------------------------------------------- #
# Long-polling (execução local)
# --------------------------------------------------------------------------- #
def run_polling() -> None:
    if not settings.telegram_bot_token:
        raise SystemExit("Defina TELEGRAM_BOT_TOKEN no .env para rodar o bot.")
    from app.db.database import init_db

    init_db()
    offset = 0
    log.info("bot de Telegram em long-polling. Ctrl+C para sair.")
    base = _API.format(token=settings.telegram_bot_token, method="getUpdates")
    while True:
        try:
            resp = httpx.get(base, params={"offset": offset, "timeout": 25}, timeout=30)
            for update in resp.json().get("result", []):
                offset = update["update_id"] + 1
                _handle_update(update)
        except KeyboardInterrupt:
            break
        except Exception:
            log.exception("erro no loop de polling; retry em 3s")
            time.sleep(3)


if __name__ == "__main__":
    run_polling()
