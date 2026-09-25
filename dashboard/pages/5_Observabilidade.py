"""Observabilidade: caminho do agente, latência e custo estimado por atendimento."""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st
from sqlmodel import col, select

from _shared import page

page("Observabilidade", "🔍")

from app.db.database import session_scope
from app.db.models import EventLog

st.title("🔍 Observabilidade")

with session_scope() as s:
    events = s.exec(select(EventLog).order_by(col(EventLog.created_at).desc()).limit(500)).all()

if not events:
    st.info("Sem eventos ainda. Converse no Simulador para gerar trilha.")
    st.stop()

df = pd.DataFrame(
    [
        {
            "quando": e.created_at,
            "tipo": e.type,
            "evento": e.name,
            "lead_id": e.lead_id,
            "tokens": e.tokens_in + e.tokens_out,
            "custo_usd": e.cost_usd,
            "latência_ms": e.latency_ms,
        }
        for e in events
    ]
)

c1, c2, c3, c4 = st.columns(4)
c1.metric("Eventos", len(df))
c2.metric("Tokens (estim.)", int(df["tokens"].sum()))
c3.metric("Custo estimado", f"US$ {df['custo_usd'].sum():.4f}")
c4.metric("Latência média", f"{df['latência_ms'].mean():.0f} ms")

st.subheader("Latência média por etapa")
lat = df[df["latência_ms"] > 0].groupby("evento")["latência_ms"].mean().reset_index()
if not lat.empty:
    fig = px.bar(lat.sort_values("latência_ms"), x="latência_ms", y="evento", orientation="h")
    fig.update_layout(height=340, margin=dict(l=10, r=10, t=10, b=10))
    st.plotly_chart(fig, width='stretch')

st.subheader("Chamadas por tipo")
tipo = df["tipo"].value_counts().reset_index()
tipo.columns = ["tipo", "qtd"]
st.plotly_chart(px.pie(tipo, names="tipo", values="qtd", hole=0.5), width='stretch')

st.subheader("Trilha recente")
st.dataframe(df.head(120), width='stretch', hide_index=True)
