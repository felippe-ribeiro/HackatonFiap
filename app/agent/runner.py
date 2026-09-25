"""Ponto de entrada único e agnóstico de canal.

Web (Streamlit), API (FastAPI) e adapters de mensageria (Telegram/WhatsApp)
chamam somente `responder(...)`. Trocar de canal = trocar o adapter, não o núcleo.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.config import settings
from app.db.models import Lead
from app.logging_conf import get_logger
from app.observability.tracing import trace
from app.services.leads import add_message, get_history, get_or_create_lead

log = get_logger("agent.runner")


@dataclass
class AgentReply:
    lead_id: int
    reply: str
    intent: str
    score: int
    temperatura: str
    status: str
    extra: dict[str, Any] = field(default_factory=dict)


def _history_to_langchain(lead_id: int, limit: int = 20) -> list:
    from langchain_core.messages import AIMessage, HumanMessage

    out: list = []
    for m in get_history(lead_id, limit=limit):
        if m.role == "user":
            out.append(HumanMessage(content=m.content))
        elif m.role == "assistant":
            out.append(AIMessage(content=m.content))
    return out


def responder(external_id: str, texto: str, canal: str = "web", nome: str | None = None) -> AgentReply:
    lead: Lead = get_or_create_lead(external_id, canal=canal, nome=nome)
    add_message(lead.id, "user", texto, meta={"canal": canal})

    # Rede de segurança determinística: extrai sinais óbvios da mensagem e atualiza o
    # perfil mesmo que o LLM demore a chamar `registrar_dados_do_lead`. Mantém o
    # painel de qualificação e o score coerentes com o que o cliente já disse.
    from app.agent.tools import extrair_sinais
    from app.services.leads import update_profile

    sinais = extrair_sinais(texto)
    if sinais:
        update_profile(lead.id, sinais)

    with trace("node", "atendimento", lead_id=lead.id, canal=canal) as ctx:
        if settings.fake_mode:
            from app.agent import simple_agent

            out = simple_agent.responder(lead.id, texto, canal)
        else:
            from app.agent.graph import responder_via_graph

            history = _history_to_langchain(lead.id)
            out = responder_via_graph(lead.id, canal, history)
        ctx["data"] = {"modo": "simulado" if settings.fake_mode else "openai", "intent": out.get("intent")}

    reply = out.get("reply") or "Desculpe, não entendi. Pode reformular?"
    add_message(lead.id, "assistant", reply, meta={"canal": canal, "engine": out.get("route", "simple")})

    # snapshot atualizado
    lead = get_or_create_lead(external_id, canal=canal)
    extra = {k: v for k, v in out.items() if k not in {"reply", "intent"}}
    return AgentReply(
        lead_id=lead.id,
        reply=reply,
        intent=lead.intent,
        score=lead.score,
        temperatura=lead.temperatura,
        status=lead.status,
        extra=extra,
    )
