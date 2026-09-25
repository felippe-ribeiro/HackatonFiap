"""Schemas de entrada/saída da API."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    external_id: str = Field(..., description="id da sessão/lead (telefone, uuid, chat_id...)")
    message: str = Field(..., min_length=1, max_length=4000)
    canal: str = "web"
    nome: str | None = None


class ChatResponse(BaseModel):
    lead_id: int
    reply: str
    intent: str
    score: int
    temperatura: str
    status: str
    extra: dict[str, Any] = {}


class ScoreCriterio(BaseModel):
    criterio: str
    pontos: int
    max: int
    atendido: bool


class LeadOut(BaseModel):
    id: int
    external_id: str
    nome: str | None
    contato: str | None
    canal: str
    intent: str
    status: str
    score: int
    temperatura: str
    profile: dict[str, Any]
    corretor: str | None
    followup_attempts: int
    created_at: datetime
    updated_at: datetime
    last_inbound_at: datetime | None


class LeadDetail(LeadOut):
    score_breakdown: list[ScoreCriterio] = []
    faltando: list[str] = []
    resumo: str | None = None


class MessageOut(BaseModel):
    id: int
    role: str
    content: str
    is_followup: bool
    created_at: datetime


class AppointmentOut(BaseModel):
    id: int
    lead_id: int
    property_id: int | None
    tipo: str
    scheduled_for: datetime
    canal: str
    corretor: str | None
    status: str
    notes: str | None


class FollowupItem(BaseModel):
    lead_id: int
    nome: str | None
    canal: str
    tentativa: int
    mensagem: str


class FollowupRunResponse(BaseModel):
    dry_run: bool
    total: int
    itens: list[FollowupItem]
