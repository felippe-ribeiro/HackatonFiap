"""Agenda de visitas e reuniões."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from _shared import page

page("Agendamentos", "📅")

from app.services.leads import get_lead
from app.services.scheduling import listar_agendamentos

st.title("📅 Visitas e Reuniões")

ags = listar_agendamentos()
if not ags:
    st.info("Nenhum agendamento. Use o Simulador e peça para *agendar uma visita*.")
    st.stop()

rows = []
for a in ags:
    lead = get_lead(a.lead_id)
    rows.append(
        {
            "quando": a.scheduled_for,
            "tipo": a.tipo,
            "lead": (lead.nome or lead.external_id) if lead else a.lead_id,
            "canal": a.canal,
            "corretor": a.corretor,
            "status": a.status,
            "imóvel_id": a.property_id,
        }
    )
df = pd.DataFrame(rows).sort_values("quando")

c1, c2, c3 = st.columns(3)
c1.metric("Total", len(df))
c2.metric("Visitas", int((df["tipo"] == "visita").sum()))
c3.metric("Reuniões (investimento)", int((df["tipo"] == "reuniao").sum()))

st.dataframe(df, width='stretch', hide_index=True)
