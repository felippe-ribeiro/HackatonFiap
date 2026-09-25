"""Follow-up automático: reengaja leads que pararam de responder.

Regra: lead com última mensagem do cliente há mais de `FOLLOWUP_AFTER_HOURS`,
status ainda em aberto e menos de `FOLLOWUP_MAX_ATTEMPTS` tentativas.
A mensagem é gerada pela LLM mantendo o contexto da conversa e registrada como
mensagem de saída (canal real enviaria via Telegram/WhatsApp).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlmodel import col, or_, select

from app.config import settings
from app.db.database import session_scope
from app.db.models import Lead, LeadStatus, Message
from app.llm import approx_tokens, chat_complete, estimate_cost
from app.logging_conf import get_logger
from app.observability.tracing import record_event
from app.services.leads import add_message, bump_followup, get_history, missing_fields

log = get_logger("followup")

_ABERTOS = {
    LeadStatus.NOVO,
    LeadStatus.EM_QUALIFICACAO,
    LeadStatus.QUALIFICADO,
    LeadStatus.EM_FOLLOWUP,
}

_SYSTEM = (
    "Você é a Lária, agente SDR da Aurora Imóveis. Escreva UMA mensagem curta "
    "(máx. 2 frases), cordial e natural, para retomar o contato com um cliente que "
    "parou de responder. Referencie algo concreto da conversa. Sem parecer robô, "
    "sem pressão. Termine com uma pergunta leve que facilite a resposta."
)


def leads_para_followup(agora: datetime | None = None) -> list[Lead]:
    agora = agora or datetime.now(timezone.utc)
    limite = agora - timedelta(hours=settings.followup_after_hours)
    with session_scope() as s:
        stmt = (
            select(Lead)
            .where(col(Lead.status).in_(_ABERTOS))
            .where(Lead.followup_attempts < settings.followup_max_attempts)
            .where(Lead.last_inbound_at.is_not(None))
            .where(Lead.last_inbound_at < limite)
            .where(
                or_(
                    Lead.last_outbound_at.is_(None),
                    Lead.last_outbound_at <= Lead.last_inbound_at,
                    Lead.last_outbound_at < limite,
                )
            )
        )
        return list(s.exec(stmt).all())


def gerar_mensagem_followup(lead: Lead) -> str:
    history = get_history(lead.id, limit=12)
    transcricao = "\n".join(
        f"{'Cliente' if m.role == 'user' else 'Lária'}: {m.content}"
        for m in history
        if m.role in ("user", "assistant")
    )
    faltando = missing_fields(lead)
    tentativa = lead.followup_attempts + 1

    if settings.fake_mode:
        alvo = faltando[0] if faltando else "seguir com a busca"
        return (
            f"Oi{(' ' + lead.nome) if lead.nome else ''}! Passando para retomar nossa conversa. "
            f"Quando puder, me diz sobre {alvo} que já adianto algumas opções pra você. 🙂"
        )

    prompt = (
        f"Tentativa de follow-up nº {tentativa}.\n"
        f"Nome do cliente: {lead.nome or 'desconhecido'}\n"
        f"Intenção: {lead.intent}\n"
        f"O que ainda falta saber: {', '.join(faltando) or 'nada crítico'}\n\n"
        f"Conversa até agora:\n{transcricao or '(cliente iniciou e não detalhou)'}"
    )
    msg = chat_complete(_SYSTEM, prompt, temperature=0.6)
    record_event(
        type="llm",
        name="followup_message",
        lead_id=lead.id,
        tokens_in=approx_tokens(_SYSTEM + prompt),
        tokens_out=approx_tokens(msg),
        cost_usd=estimate_cost(
            settings.llm_model, approx_tokens(_SYSTEM + prompt), approx_tokens(msg)
        ),
    )
    return msg.strip()


def executar_ciclo(dry_run: bool = False, agora: datetime | None = None) -> list[dict]:
    """Roda um ciclo de follow-up. Retorna o que foi (ou seria) enviado."""
    resultados: list[dict] = []
    for lead in leads_para_followup(agora):
        msg = gerar_mensagem_followup(lead)
        resultados.append(
            {
                "lead_id": lead.id,
                "nome": lead.nome,
                "canal": lead.canal,
                "tentativa": lead.followup_attempts + 1,
                "mensagem": msg,
            }
        )
        if not dry_run:
            add_message(lead.id, "assistant", msg, is_followup=True, meta={"tipo": "followup"})
            bump_followup(lead.id)
            record_event(
                type="followup", name="enviado", lead_id=lead.id,
                data={"tentativa": lead.followup_attempts + 1, "canal": lead.canal},
            )
    log.info(
        f"ciclo de follow-up: {len(resultados)} lead(s)",
        extra={"event": "followup:ciclo", "tokens": 0},
    )
    return resultados
