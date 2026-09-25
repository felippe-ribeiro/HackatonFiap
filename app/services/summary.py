"""Resumo inteligente do atendimento para o corretor."""

from __future__ import annotations

from app.db.database import session_scope
from app.db.models import Lead, LeadSummary
from app.llm import approx_tokens, chat_complete, estimate_cost
from app.config import settings
from app.observability.tracing import record_event
from app.services.leads import get_history, missing_fields, score_breakdown

_SYSTEM = (
    "Você é um assistente que resume atendimentos de pré-venda imobiliária para "
    "corretores. Seja objetivo, factual e use apenas o que está na conversa. "
    "Não invente dados. Estruture em tópicos curtos."
)

_TEMPLATE = """Gere um resumo do lead para o corretor, no formato:

**Lead:** <nome ou 'não informado'> — <intenção>
**Temperatura:** <quente/morno/frio> (score <n>/100)
**Resumo da necessidade:** 2 a 3 frases.
**Dados coletados:**
- <campo>: <valor>
**Pendências para o corretor confirmar:**
- <item>
**Próximo passo sugerido:** <uma frase>

Contexto estruturado:
{contexto}

Transcrição (mais recente por último):
{transcricao}
"""


def _fallback_summary(lead: Lead) -> str:
    p = lead.profile
    linhas = [
        f"**Lead:** {lead.nome or 'não informado'} — {lead.intent}",
        f"**Temperatura:** {lead.temperatura} (score {lead.score}/100)",
        "**Dados coletados:**",
    ]
    for k, v in p.items():
        linhas.append(f"- {k}: {v}")
    if lead.contato:
        linhas.append(f"- contato: {lead.contato}")
    faltando = missing_fields(lead)
    if faltando:
        linhas.append("**Pendências para o corretor confirmar:**")
        linhas += [f"- {f}" for f in faltando]
    linhas.append("**Próximo passo sugerido:** entrar em contato e confirmar as pendências acima.")
    return "\n".join(linhas)


def gerar_resumo(lead_id: int, kind: str = "handoff", persist: bool = True) -> str:
    with session_scope() as s:
        lead = s.get(Lead, lead_id)
        if lead is None:
            raise ValueError(f"lead {lead_id} inexistente")
        lead_snapshot = lead

    history = get_history(lead_id, limit=30)
    transcricao = "\n".join(
        f"{'Cliente' if m.role == 'user' else 'Agente'}: {m.content}"
        for m in history
        if m.role in ("user", "assistant")
    )
    contexto = (
        f"intent={lead_snapshot.intent}; score={lead_snapshot.score}; "
        f"status={lead_snapshot.status}; profile={lead_snapshot.profile}; "
        f"contato={lead_snapshot.contato}; "
        f"criterios={[c for c in score_breakdown(lead_snapshot)]}"
    )

    if settings.fake_mode:
        content = _fallback_summary(lead_snapshot)
    else:
        prompt = _TEMPLATE.format(contexto=contexto, transcricao=transcricao or "(sem mensagens)")
        content = chat_complete(_SYSTEM, prompt, temperature=0.2)
        record_event(
            type="llm",
            name="gerar_resumo",
            lead_id=lead_id,
            tokens_in=approx_tokens(_SYSTEM + prompt),
            tokens_out=approx_tokens(content),
            cost_usd=estimate_cost(
                settings.llm_model, approx_tokens(_SYSTEM + prompt), approx_tokens(content)
            ),
        )

    if persist:
        with session_scope() as s:
            s.add(LeadSummary(lead_id=lead_id, kind=kind, content=content))
    return content


def ultimo_resumo(lead_id: int) -> LeadSummary | None:
    from sqlmodel import col, select

    with session_scope() as s:
        return s.exec(
            select(LeadSummary)
            .where(LeadSummary.lead_id == lead_id)
            .order_by(col(LeadSummary.created_at).desc())
        ).first()
