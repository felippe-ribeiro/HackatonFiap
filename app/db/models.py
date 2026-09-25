"""Modelo de dados da solução (SQLModel / SQLAlchemy).

Entidades principais:
- Property      : base simulada de imóveis (fonte do RAG)
- Lead          : contato em atendimento + perfil de qualificação
- Message       : histórico conversacional (memória de longo prazo)
- Appointment   : visitas / reuniões agendadas
- LeadSummary   : resumo inteligente gerado para o corretor
- EventLog      : trilha de observabilidade (tokens, custo, latência, nós)
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from sqlalchemy import JSON, Column, Text
from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# --------------------------------------------------------------------------- #
# Enums de domínio
# --------------------------------------------------------------------------- #
class Intent(StrEnum):
    COMPRA = "compra"
    ALUGUEL = "aluguel"
    INVESTIMENTO = "investimento"
    INDEFINIDO = "indefinido"


class LeadStatus(StrEnum):
    NOVO = "novo"
    EM_QUALIFICACAO = "em_qualificacao"
    QUALIFICADO = "qualificado"
    AGENDADO = "agendado"
    EM_FOLLOWUP = "em_followup"
    GANHO = "ganho"
    PERDIDO = "perdido"


class Channel(StrEnum):
    WEB = "web"
    WHATSAPP = "whatsapp"
    VOZ = "voz"


class AppointmentStatus(StrEnum):
    AGENDADO = "agendado"
    CONFIRMADO = "confirmado"
    REALIZADO = "realizado"
    CANCELADO = "cancelado"


# --------------------------------------------------------------------------- #
# Tabelas
# --------------------------------------------------------------------------- #
class Property(SQLModel, table=True):
    __tablename__ = "properties"

    id: int | None = Field(default=None, primary_key=True)
    codigo: str = Field(index=True, unique=True)
    titulo: str
    tipo: str = Field(index=True)                 # apartamento, casa, studio, cobertura...
    finalidade: str = Field(index=True)           # venda | aluguel
    cidade: str = Field(index=True)
    bairro: str = Field(index=True)
    zona: str = Field(index=True)                 # zona sul, zona oeste...
    preco: float = Field(index=True)
    condominio: float = 0.0
    iptu: float = 0.0
    quartos: int = Field(default=0, index=True)
    suites: int = 0
    banheiros: int = 0
    vagas: int = 0
    area_util: float = 0.0
    ano_construcao: int | None = None
    rentabilidade_aluguel_pct: float | None = None   # % a.a. estimada (investidor)
    descricao: str = Field(sa_column=Column(Text))
    caracteristicas: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    status: str = Field(default="disponivel", index=True)
    created_at: datetime = Field(default_factory=utcnow)


class Lead(SQLModel, table=True):
    __tablename__ = "leads"

    id: int | None = Field(default=None, primary_key=True)
    external_id: str = Field(index=True, unique=True)  # id de sessão / telefone
    nome: str | None = None
    contato: str | None = None
    canal: str = Field(default=Channel.WEB, index=True)
    intent: str = Field(default=Intent.INDEFINIDO, index=True)
    status: str = Field(default=LeadStatus.NOVO, index=True)
    score: int = Field(default=0, index=True)          # 0-100 (lead scoring)
    temperatura: str = Field(default="frio")           # frio | morno | quente
    profile: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    corretor: str | None = None
    followup_attempts: int = 0
    created_at: datetime = Field(default_factory=utcnow, index=True)
    updated_at: datetime = Field(default_factory=utcnow)
    last_inbound_at: datetime | None = Field(default=None, index=True)
    last_outbound_at: datetime | None = None


class Message(SQLModel, table=True):
    __tablename__ = "messages"

    id: int | None = Field(default=None, primary_key=True)
    lead_id: int = Field(index=True, foreign_key="leads.id")
    role: str = Field(index=True)                      # user | assistant | system | tool
    content: str = Field(sa_column=Column(Text))
    meta: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    is_followup: bool = False
    created_at: datetime = Field(default_factory=utcnow, index=True)


class Appointment(SQLModel, table=True):
    __tablename__ = "appointments"

    id: int | None = Field(default=None, primary_key=True)
    lead_id: int = Field(index=True, foreign_key="leads.id")
    property_id: int | None = Field(default=None, foreign_key="properties.id")
    tipo: str = "visita"                               # visita | reuniao
    scheduled_for: datetime = Field(index=True)
    canal: str = Channel.WEB
    corretor: str | None = None
    status: str = Field(default=AppointmentStatus.AGENDADO, index=True)
    notes: str | None = None
    created_at: datetime = Field(default_factory=utcnow)


class LeadSummary(SQLModel, table=True):
    __tablename__ = "lead_summaries"

    id: int | None = Field(default=None, primary_key=True)
    lead_id: int = Field(index=True, foreign_key="leads.id")
    kind: str = "handoff"                              # handoff | manual | followup
    content: str = Field(sa_column=Column(Text))
    created_at: datetime = Field(default_factory=utcnow, index=True)


class EventLog(SQLModel, table=True):
    __tablename__ = "event_logs"

    id: int | None = Field(default=None, primary_key=True)
    lead_id: int | None = Field(default=None, index=True)
    type: str = Field(index=True)                      # llm | tool | node | guardrail | followup
    name: str = Field(index=True)
    data: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    latency_ms: int = 0
    created_at: datetime = Field(default_factory=utcnow, index=True)
