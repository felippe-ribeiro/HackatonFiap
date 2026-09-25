"""Serviço de agendamento de visitas e reuniões."""

from __future__ import annotations

from datetime import datetime, time, timedelta, timezone

from sqlmodel import col, select

from app.db.database import session_scope
from app.db.models import Appointment, AppointmentStatus, Lead, LeadStatus, Property

# Janelas de atendimento da Aurora Imóveis (ver base de conhecimento)
VISITA_DIAS = {1, 2, 3, 4, 5}          # ter-sáb (Mon=0 ... Sun=6 -> ajustado abaixo)
VISITA_HORAS = list(range(9, 18))
REUNIAO_DIAS = {0, 2}                  # seg e qua
REUNIAO_HORAS = list(range(14, 18))


def _next_slots(kind: str, n: int = 6) -> list[datetime]:
    dias = REUNIAO_DIAS if kind == "reuniao" else {1, 2, 3, 4, 5}
    horas = REUNIAO_HORAS if kind == "reuniao" else VISITA_HORAS
    now = datetime.now(timezone.utc)
    cursor = (now + timedelta(hours=3)).replace(minute=0, second=0, microsecond=0)
    out: list[datetime] = []
    while len(out) < n:
        if cursor.weekday() in dias and cursor.hour in horas:
            out.append(cursor)
        cursor += timedelta(hours=1)
        if cursor > now + timedelta(days=21):
            break
    return out


def proximos_horarios(kind: str = "visita", n: int = 6) -> list[str]:
    return [dt.isoformat() for dt in _next_slots(kind, n)]


def agendar(
    lead_id: int,
    quando_iso: str,
    *,
    tipo: str = "visita",
    property_codigo: str | None = None,
    canal: str = "web",
    corretor: str | None = None,
    notes: str | None = None,
) -> Appointment:
    try:
        quando = datetime.fromisoformat(quando_iso)
    except ValueError as e:
        raise ValueError(f"data/hora inválida: {quando_iso!r}") from e
    if quando.tzinfo is None:
        quando = quando.replace(tzinfo=timezone.utc)
    if quando < datetime.now(timezone.utc):
        raise ValueError("não é possível agendar no passado")

    with session_scope() as s:
        prop_id = None
        if property_codigo:
            prop = s.exec(select(Property).where(Property.codigo == property_codigo)).first()
            prop_id = prop.id if prop else None

        appt = Appointment(
            lead_id=lead_id,
            property_id=prop_id,
            tipo=tipo,
            scheduled_for=quando,
            canal=canal,
            corretor=corretor or ("Especialista de Investimentos" if tipo == "reuniao" else "Corretor de plantão"),
            notes=notes,
            status=AppointmentStatus.AGENDADO,
        )
        s.add(appt)

        lead = s.get(Lead, lead_id)
        if lead and lead.status not in {LeadStatus.GANHO, LeadStatus.PERDIDO}:
            lead.status = LeadStatus.AGENDADO
            lead.updated_at = datetime.now(timezone.utc)
        s.flush()
        s.refresh(appt)
        return appt


def listar_agendamentos(futuros: bool = False) -> list[Appointment]:
    with session_scope() as s:
        stmt = select(Appointment).order_by(col(Appointment.scheduled_for).asc())
        if futuros:
            stmt = stmt.where(Appointment.scheduled_for >= datetime.now(timezone.utc))
        return list(s.exec(stmt).all())


def agendamentos_do_lead(lead_id: int) -> list[Appointment]:
    with session_scope() as s:
        return list(
            s.exec(
                select(Appointment)
                .where(Appointment.lead_id == lead_id)
                .order_by(col(Appointment.scheduled_for).asc())
            ).all()
        )
