"""Observabilidade: trilha de eventos (nós, tools, chamadas de LLM) no banco + logs.

Cada passo relevante do agente vira um `EventLog` — o dashboard usa isso para
mostrar latência, custo estimado e caminho percorrido em cada atendimento.
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Any

from app.db.database import session_scope
from app.db.models import EventLog
from app.logging_conf import get_logger

log = get_logger("observability")


def record_event(
    *,
    type: str,
    name: str,
    lead_id: int | None = None,
    data: dict[str, Any] | None = None,
    tokens_in: int = 0,
    tokens_out: int = 0,
    cost_usd: float = 0.0,
    latency_ms: int = 0,
) -> None:
    try:
        with session_scope() as s:
            s.add(
                EventLog(
                    lead_id=lead_id,
                    type=type,
                    name=name,
                    data=data or {},
                    tokens_in=tokens_in,
                    tokens_out=tokens_out,
                    cost_usd=cost_usd,
                    latency_ms=latency_ms,
                )
            )
    except Exception:  # observabilidade nunca pode quebrar o fluxo principal
        log.exception("falha ao gravar EventLog")

    log.info(
        f"{type}:{name}",
        extra={
            "event": f"{type}:{name}",
            "lead_id": lead_id,
            "tokens": tokens_in + tokens_out,
            "cost_usd": cost_usd,
            "latency_ms": latency_ms,
        },
    )


@contextmanager
def trace(type: str, name: str, lead_id: int | None = None, **data: Any):
    """Mede latência de um bloco e grava o evento ao final.

    with trace("node", "agente_vendas", lead_id=1) as ctx:
        ...
        ctx["tokens_out"] = 120
    """
    start = time.perf_counter()
    ctx: dict[str, Any] = {"tokens_in": 0, "tokens_out": 0, "cost_usd": 0.0, "data": dict(data)}
    try:
        yield ctx
    finally:
        latency = int((time.perf_counter() - start) * 1000)
        record_event(
            type=type,
            name=name,
            lead_id=lead_id,
            data=ctx.get("data") or {},
            tokens_in=int(ctx.get("tokens_in", 0)),
            tokens_out=int(ctx.get("tokens_out", 0)),
            cost_usd=float(ctx.get("cost_usd", 0.0)),
            latency_ms=latency,
        )
