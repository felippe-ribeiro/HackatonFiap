"""Serviço de leads: memória conversacional, perfil de qualificação e lead scoring.

O **score** é calculado por regras explícitas e auditáveis (não por caixa-preta) —
cada ponto tem justificativa, o que é importante para o corretor confiar na
priorização. Ver `SCORE_RUBRICA`.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlmodel import col, func, select

from app.db.database import session_scope
from app.db.models import Intent, Lead, LeadStatus, Message

# Campo -> (pontos, rótulo para explicação)
SCORE_RUBRICA: dict[str, tuple[int, str]] = {
    "intent": (15, "Intenção identificada (compra/aluguel/investimento)"),
    "orcamento": (20, "Orçamento / faixa de preço definida"),
    "regiao": (15, "Região de interesse definida"),
    "quartos": (10, "Nº de dormitórios definido"),
    "urgencia": (20, "Urgência declarada (prazo para decidir)"),
    "contato": (10, "Contato para retorno fornecido"),
    "pagamento": (10, "Forma de pagamento / financiamento esclarecida"),
}

URGENCIA_PESO = {"alta": 20, "media": 10, "baixa": 4}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# --------------------------------------------------------------------------- #
def get_or_create_lead(external_id: str, canal: str = "web", nome: str | None = None) -> Lead:
    with session_scope() as s:
        lead = s.exec(select(Lead).where(Lead.external_id == external_id)).first()
        if lead is None:
            lead = Lead(external_id=external_id, canal=canal, nome=nome, profile={})
            s.add(lead)
            s.flush()
        elif nome and not lead.nome:
            lead.nome = nome
        s.refresh(lead)
        return lead


def get_lead(lead_id: int) -> Lead | None:
    with session_scope() as s:
        return s.get(Lead, lead_id)


# --------------------------------------------------------------------------- #
def add_message(
    lead_id: int,
    role: str,
    content: str,
    *,
    is_followup: bool = False,
    meta: dict[str, Any] | None = None,
) -> Message:
    with session_scope() as s:
        msg = Message(
            lead_id=lead_id, role=role, content=content, is_followup=is_followup, meta=meta or {}
        )
        s.add(msg)
        lead = s.get(Lead, lead_id)
        if lead:
            now = utcnow()
            if role == "user":
                lead.last_inbound_at = now
                if lead.status == LeadStatus.NOVO:
                    lead.status = LeadStatus.EM_QUALIFICACAO
            elif role == "assistant":
                lead.last_outbound_at = now
            lead.updated_at = now
        s.flush()
        s.refresh(msg)
        return msg


def get_history(lead_id: int, limit: int = 40) -> list[Message]:
    with session_scope() as s:
        rows = s.exec(
            select(Message)
            .where(Message.lead_id == lead_id)
            .order_by(col(Message.created_at).desc(), col(Message.id).desc())
            .limit(limit)
        ).all()
        return list(reversed(rows))


# --------------------------------------------------------------------------- #
def update_profile(lead_id: int, patch: dict[str, Any]) -> Lead:
    """Mescla campos no perfil, re-deriva intenção, score, temperatura e status."""
    patch = {k: v for k, v in patch.items() if v not in (None, "", [], {})}
    with session_scope() as s:
        lead = s.get(Lead, lead_id)
        if lead is None:
            raise ValueError(f"lead {lead_id} inexistente")

        profile = dict(lead.profile)
        profile.update(patch)
        lead.profile = profile

        if patch.get("finalidade") in {"compra", "aluguel", "investimento"}:
            lead.intent = patch["finalidade"]
        if patch.get("nome") and not lead.nome:
            lead.nome = patch["nome"]
        if patch.get("contato"):
            lead.contato = patch["contato"]

        _recompute(lead)
        lead.updated_at = utcnow()
        s.add(lead)
        s.flush()
        s.refresh(lead)
        return lead


def set_status(lead_id: int, status: str, corretor: str | None = None) -> Lead:
    with session_scope() as s:
        lead = s.get(Lead, lead_id)
        if lead is None:
            raise ValueError(f"lead {lead_id} inexistente")
        lead.status = status
        if corretor:
            lead.corretor = corretor
        lead.updated_at = utcnow()
        s.add(lead)
        s.flush()
        s.refresh(lead)
        return lead


def bump_followup(lead_id: int) -> Lead:
    with session_scope() as s:
        lead = s.get(Lead, lead_id)
        lead.followup_attempts += 1
        lead.status = LeadStatus.EM_FOLLOWUP
        lead.last_outbound_at = utcnow()
        s.add(lead)
        s.flush()
        s.refresh(lead)
        return lead


# --------------------------------------------------------------------------- #
def score_breakdown(lead: Lead) -> list[dict[str, Any]]:
    p = lead.profile
    out: list[dict[str, Any]] = []

    def add(key: str, ok: bool, pts: int | None = None):
        base, label = SCORE_RUBRICA[key]
        out.append({"criterio": label, "pontos": (pts if pts is not None else base) if ok else 0, "max": base, "atendido": ok})

    add("intent", lead.intent != Intent.INDEFINIDO)
    add("orcamento", bool(p.get("orcamento_max") or p.get("ticket_investimento")))
    add("regiao", bool(p.get("zonas") or p.get("bairros")))
    add("quartos", p.get("quartos_min") is not None or lead.intent == Intent.INVESTIMENTO)
    urg = (p.get("urgencia") or "").lower()
    add("urgencia", urg in URGENCIA_PESO, URGENCIA_PESO.get(urg, 0))
    add("contato", bool(lead.contato))
    add("pagamento", bool(p.get("financiamento") or p.get("forma_pagamento")))
    return out


def _recompute(lead: Lead) -> None:
    total = sum(item["pontos"] for item in score_breakdown(lead))
    lead.score = max(0, min(100, total))
    lead.temperatura = "quente" if lead.score >= 70 else "morno" if lead.score >= 40 else "frio"

    if lead.status not in {LeadStatus.AGENDADO, LeadStatus.GANHO, LeadStatus.PERDIDO}:
        if lead.score >= 70:
            lead.status = LeadStatus.QUALIFICADO
        elif lead.status == LeadStatus.NOVO:
            lead.status = LeadStatus.EM_QUALIFICACAO


# --------------------------------------------------------------------------- #
def missing_fields(lead: Lead) -> list[str]:
    """O que ainda falta perguntar — guia o agente na qualificação."""
    p = lead.profile
    faltando: list[str] = []
    if lead.intent == Intent.INDEFINIDO:
        faltando.append("finalidade (compra, aluguel ou investimento)")
    if lead.intent == Intent.INVESTIMENTO:
        if not p.get("ticket_investimento"):
            faltando.append("ticket de investimento disponível")
        if not p.get("retorno_esperado"):
            faltando.append("expectativa de retorno")
        if not p.get("perfil_investidor"):
            faltando.append("perfil (renda mensal ou valorização)")
    else:
        if not (p.get("zonas") or p.get("bairros")):
            faltando.append("região de interesse")
        if not p.get("orcamento_max"):
            faltando.append("faixa de preço")
        if p.get("quartos_min") is None:
            faltando.append("quantidade de dormitórios")
    if not p.get("urgencia"):
        faltando.append("prazo / urgência para decidir")
    if not lead.contato:
        faltando.append("um contato para retorno")
    return faltando


# --------------------------------------------------------------------------- #
def list_leads(status: str | None = None) -> list[Lead]:
    with session_scope() as s:
        stmt = select(Lead).order_by(col(Lead.score).desc(), col(Lead.updated_at).desc())
        if status:
            stmt = stmt.where(Lead.status == status)
        return list(s.exec(stmt).all())


def pipeline_counts() -> dict[str, int]:
    with session_scope() as s:
        rows = s.exec(select(Lead.status, func.count()).group_by(col(Lead.status))).all()
        return {status: count for status, count in rows}
