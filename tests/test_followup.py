from datetime import datetime, timedelta, timezone

from app.services.followup import executar_ciclo, leads_para_followup
from app.services.leads import add_message, get_or_create_lead
from app.db.database import session_scope
from app.db.models import Lead


def _envelhecer(lead_id: int, horas: int):
    with session_scope() as s:
        lead = s.get(Lead, lead_id)
        antigo = datetime.now(timezone.utc) - timedelta(hours=horas)
        lead.last_inbound_at = antigo
        lead.last_outbound_at = antigo
        s.add(lead)


def test_lead_parado_entra_na_fila_e_recebe_mensagem():
    lead = get_or_create_lead("fu-1", canal="telegram")
    add_message(lead.id, "user", "oi, queria alugar algo na zona oeste")
    add_message(lead.id, "assistant", "Claro! Qual faixa de preço?")
    _envelhecer(lead.id, 48)

    assert any(l.id == lead.id for l in leads_para_followup())

    itens = executar_ciclo(dry_run=False)
    assert any(i["lead_id"] == lead.id for i in itens)

    # após enviar, não deve reaparecer imediatamente
    assert not any(l.id == lead.id for l in leads_para_followup())


def test_lead_recente_nao_entra():
    lead = get_or_create_lead("fu-2")
    add_message(lead.id, "user", "oi")
    assert not any(l.id == lead.id for l in leads_para_followup())
