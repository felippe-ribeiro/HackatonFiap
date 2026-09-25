"""Utilidades compartilhadas pelas páginas do painel (Streamlit)."""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from app.config import settings  # noqa: E402
from app.db.database import init_db  # noqa: E402

TEMP_COR = {"quente": "#e5484d", "morno": "#f2a900", "frio": "#3b82f6"}
STATUS_ORDEM = [
    "novo", "em_qualificacao", "qualificado", "agendado", "em_followup", "ganho", "perdido",
]


@st.cache_resource
def _bootstrap() -> bool:
    init_db()
    return True


def page(title: str, icon: str = "🏠") -> None:
    st.set_page_config(page_title=f"Lária · {title}", page_icon=icon, layout="wide")
    _bootstrap()
    modo = "🟢 OpenAI" if not settings.fake_mode else "🟡 Simulado (sem API)"
    st.caption(f"Lária — Agente SDR Imobiliário · Aurora Imóveis · modo IA: {modo}")


def brl(v: float | None) -> str:
    if not v:
        return "—"
    return f"R$ {v:,.0f}".replace(",", ".")


def leads_df() -> pd.DataFrame:
    from app.services.leads import list_leads

    rows = []
    for l in list_leads():
        rows.append(
            {
                "id": l.id,
                "nome": l.nome or l.external_id,
                "canal": l.canal,
                "intenção": l.intent,
                "status": l.status,
                "score": l.score,
                "temperatura": l.temperatura,
                "atualizado": l.updated_at,
                "tentativas_followup": l.followup_attempts,
            }
        )
    return pd.DataFrame(rows)
