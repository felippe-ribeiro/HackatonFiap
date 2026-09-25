"""Follow-up automático: quem está parado e o que a Lária enviaria."""

from __future__ import annotations

import streamlit as st

from _shared import page

page("Follow-up", "🔁")

from app.config import settings
from app.services.followup import executar_ciclo, leads_para_followup

st.title("🔁 Follow-up Automático")

st.caption(
    f"Regra: sem resposta do cliente há mais de **{settings.followup_after_hours}h**, "
    f"status em aberto e menos de **{settings.followup_max_attempts}** tentativas. "
    f"Em produção roda a cada {settings.followup_scan_interval_minutes} min (APScheduler)."
)

alvos = leads_para_followup()
st.metric("Leads elegíveis agora", len(alvos))

col1, col2 = st.columns(2)
if col1.button("👁️ Simular (dry-run)", width='stretch'):
    st.session_state["fu"] = ("dry", executar_ciclo(dry_run=True))
if col2.button("📨 Executar e registrar", type="primary", width='stretch'):
    st.session_state["fu"] = ("real", executar_ciclo(dry_run=False))

modo, itens = st.session_state.get("fu", (None, []))
if modo:
    st.success(f"{'Simulação' if modo == 'dry' else 'Enviado'}: {len(itens)} mensagem(ns).")
    for it in itens:
        with st.chat_message("assistant"):
            st.caption(
                f"→ {it['nome'] or it['lead_id']} · canal {it['canal']} · tentativa {it['tentativa']}"
            )
            st.write(it["mensagem"])

if alvos:
    st.divider()
    st.subheader("Fila de follow-up")
    for l in alvos:
        st.write(
            f"#{l.id} · {l.nome or l.external_id} · {l.intent} · score {l.score} · "
            f"última msg do cliente: {l.last_inbound_at:%d/%m %Hh}"
        )
