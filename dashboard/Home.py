"""Painel de acompanhamento — visão geral."""

from __future__ import annotations

import plotly.express as px
import streamlit as st

from _shared import STATUS_ORDEM, leads_df, page

page("Visão Geral", "📊")

st.title("📊 Visão Geral — Pipeline de Leads")

df = leads_df()
if df.empty:
    st.info("Sem leads ainda. Rode `python -m scripts.seed_db` ou use o **Simulador**.")
    st.stop()

from app.services.scheduling import listar_agendamentos

col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("Leads", len(df))
col2.metric("Quentes 🔥", int((df["temperatura"] == "quente").sum()))
col3.metric("Qualificados", int(df["status"].isin(["qualificado", "agendado"]).sum()))
col4.metric("Visitas/reuniões", len(listar_agendamentos(futuros=True)))
col5.metric("Score médio", round(df["score"].mean(), 1))

st.divider()
c1, c2 = st.columns([3, 2])

with c1:
    st.subheader("Funil por status")
    funil = (
        df["status"].value_counts().reindex(STATUS_ORDEM).dropna().reset_index()
    )
    funil.columns = ["status", "leads"]
    fig = px.funnel(funil, x="leads", y="status")
    fig.update_layout(height=380, margin=dict(l=10, r=10, t=10, b=10))
    st.plotly_chart(fig, width='stretch')

with c2:
    st.subheader("Distribuição de temperatura")
    temp = df["temperatura"].value_counts().reset_index()
    temp.columns = ["temperatura", "leads"]
    fig2 = px.pie(
        temp, names="temperatura", values="leads", hole=0.5,
        color="temperatura",
        color_discrete_map={"quente": "#e5484d", "morno": "#f2a900", "frio": "#3b82f6"},
    )
    fig2.update_layout(height=380, margin=dict(l=10, r=10, t=10, b=10))
    st.plotly_chart(fig2, width='stretch')

st.subheader("Leads por canal")
canal = df.groupby(["canal", "temperatura"]).size().reset_index(name="leads")
fig3 = px.bar(canal, x="canal", y="leads", color="temperatura",
              color_discrete_map={"quente": "#e5484d", "morno": "#f2a900", "frio": "#3b82f6"})
fig3.update_layout(height=320, margin=dict(l=10, r=10, t=10, b=10))
st.plotly_chart(fig3, width='stretch')

st.divider()
st.subheader("🔥 Top leads para o corretor agir agora")
top = df[df["temperatura"] != "frio"].sort_values("score", ascending=False).head(8)
st.dataframe(top, width='stretch', hide_index=True)
