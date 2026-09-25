"""API FastAPI do Agente SDR Imobiliário (Lária)."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import Session, col, func, select

from app import __version__
from app.config import settings
from app.db.database import engine, get_session, init_db
from app.db.models import Appointment, EventLog, Lead, Message
from app.logging_conf import get_logger
from app.rag import retriever
from app.schemas import (
    AppointmentOut,
    ChatRequest,
    ChatResponse,
    FollowupRunResponse,
    LeadDetail,
    LeadOut,
    MessageOut,
)
from app.services import followup as followup_service
from app.services.leads import missing_fields, score_breakdown
from app.services.summary import gerar_resumo, ultimo_resumo

log = get_logger("api")
scheduler = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    try:
        retriever._get_store("imoveis")  # noqa: SLF001 — valida índice
    except Exception:
        log.warning("índice RAG ausente — rode `python -m scripts.seed_db`")

    global scheduler
    if settings.followup_enabled and settings.app_env != "test":
        from apscheduler.schedulers.background import BackgroundScheduler

        scheduler = BackgroundScheduler(daemon=True)
        scheduler.add_job(
            followup_service.executar_ciclo,
            "interval",
            minutes=settings.followup_scan_interval_minutes,
            id="followup",
            next_run_time=None,
        )
        scheduler.start()
        log.info("scheduler de follow-up iniciado", extra={"event": "startup"})
    yield
    if scheduler:
        scheduler.shutdown(wait=False)


app = FastAPI(title="Lária — Agente SDR Imobiliário", version=__version__, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)


# --------------------------------------------------------------------------- #
@app.get("/")
def health():
    return {
        "app": "Lária — Agente SDR Imobiliário",
        "version": __version__,
        "modo_ia": "simulado" if settings.fake_mode else f"openai:{settings.llm_model}",
        "llm_configurada": settings.llm_enabled,
    }


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    from app.agent.runner import responder

    out = responder(req.external_id, req.message, canal=req.canal, nome=req.nome)
    return ChatResponse(
        lead_id=out.lead_id,
        reply=out.reply,
        intent=out.intent,
        score=out.score,
        temperatura=out.temperatura,
        status=out.status,
        extra=out.extra,
    )


# --------------------------------------------------------------------------- #
@app.get("/leads", response_model=list[LeadOut])
def listar_leads(status: str | None = None, session: Session = Depends(get_session)):
    stmt = select(Lead).order_by(col(Lead.score).desc(), col(Lead.updated_at).desc())
    if status:
        stmt = stmt.where(Lead.status == status)
    return list(session.exec(stmt).all())


@app.get("/leads/{lead_id}", response_model=LeadDetail)
def detalhar_lead(lead_id: int, session: Session = Depends(get_session)):
    lead = session.get(Lead, lead_id)
    if lead is None:
        raise HTTPException(404, "lead não encontrado")
    resumo = ultimo_resumo(lead_id)
    return LeadDetail(
        **lead.model_dump(),
        score_breakdown=score_breakdown(lead),
        faltando=missing_fields(lead),
        resumo=resumo.content if resumo else None,
    )


@app.get("/leads/{lead_id}/messages", response_model=list[MessageOut])
def mensagens_do_lead(lead_id: int, session: Session = Depends(get_session)):
    return list(
        session.exec(
            select(Message).where(Message.lead_id == lead_id).order_by(col(Message.created_at).asc())
        ).all()
    )


@app.post("/leads/{lead_id}/resumo")
def gerar_resumo_lead(lead_id: int):
    return {"resumo": gerar_resumo(lead_id, kind="manual")}


# --------------------------------------------------------------------------- #
@app.get("/appointments", response_model=list[AppointmentOut])
def listar_appointments(futuros: bool = False, session: Session = Depends(get_session)):
    stmt = select(Appointment).order_by(col(Appointment.scheduled_for).asc())
    if futuros:
        from datetime import datetime, timezone

        stmt = stmt.where(Appointment.scheduled_for >= datetime.now(timezone.utc))
    return list(session.exec(stmt).all())


@app.get("/imoveis/busca")
def buscar_imoveis(
    q: str = Query(..., description="consulta livre"),
    finalidade: str | None = None,
    zona: str | None = None,
    preco_max: float | None = None,
    k: int = 5,
):
    hits = retriever.buscar_imoveis(q, finalidade=finalidade, zona=zona, preco_max=preco_max, k=k)
    return [{"score": h.score, **h.metadata} for h in hits]


# --------------------------------------------------------------------------- #
@app.post("/followup/run", response_model=FollowupRunResponse)
def rodar_followup(dry_run: bool = True):
    itens = followup_service.executar_ciclo(dry_run=dry_run)
    return FollowupRunResponse(dry_run=dry_run, total=len(itens), itens=itens)


@app.get("/observabilidade/resumo")
def observabilidade(session: Session = Depends(get_session)):
    total_cost = session.exec(select(func.coalesce(func.sum(EventLog.cost_usd), 0.0))).one()
    total_tokens = session.exec(
        select(func.coalesce(func.sum(EventLog.tokens_in + EventLog.tokens_out), 0))
    ).one()
    by_name = session.exec(
        select(EventLog.name, func.count(), func.coalesce(func.avg(EventLog.latency_ms), 0))
        .group_by(col(EventLog.name))
    ).all()
    return {
        "eventos": session.exec(select(func.count()).select_from(EventLog)).one(),
        "custo_usd_estimado": round(float(total_cost), 4),
        "tokens_totais": int(total_tokens),
        "por_evento": [
            {"nome": n, "qtd": c, "latencia_media_ms": round(float(l), 1)} for n, c, l in by_name
        ],
    }


# --------------------------------------------------------------------------- #
# Adapter de mensageria (opcional) — ver app/channels/telegram.py e ARQUITETURA.md
# --------------------------------------------------------------------------- #
try:
    from app.channels.telegram import router as telegram_router

    app.include_router(telegram_router)
except Exception:  # canal opcional
    pass
