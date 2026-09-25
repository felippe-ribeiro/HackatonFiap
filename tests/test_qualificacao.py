from app.agent.tools import extrair_sinais
from app.services.leads import get_or_create_lead, missing_fields, score_breakdown, update_profile


def test_extrair_sinais_compra_zona_sul():
    p = extrair_sinais("Estou procurando apartamento na zona sul, uns 2 quartos, até 900 mil")
    assert p["finalidade"] == "compra"
    assert "zona sul" in p["zonas"]
    assert p["quartos_min"] == 2
    assert p["orcamento_max"] == 900_000


def test_extrair_sinais_investimento_e_urgencia():
    p = extrair_sinais("Quero investir 500 mil em imóvel para renda, com pressa")
    assert p["finalidade"] == "investimento"
    assert p["ticket_investimento"] == 500_000
    assert p["urgencia"] == "alta"


def test_extrair_contato():
    assert extrair_sinais("meu email é joao@teste.com")["contato"] == "joao@teste.com"
    assert extrair_sinais("me liga no (11) 98888-7777")["contato"].startswith("(11)")


def test_score_sobe_com_qualificacao():
    lead = get_or_create_lead("test-score-1")
    assert lead.score == 0
    lead = update_profile(
        lead.id,
        {
            "finalidade": "compra",
            "zonas": ["zona sul"],
            "orcamento_max": 800_000,
            "quartos_min": 2,
            "urgencia": "alta",
            "contato": "a@b.com",
            "financiamento": "pré-aprovado",
        },
    )
    assert lead.score >= 90
    assert lead.temperatura == "quente"
    assert lead.status == "qualificado"
    assert missing_fields(lead) == []


def test_score_breakdown_soma_bate_com_score():
    lead = get_or_create_lead("test-score-2")
    lead = update_profile(lead.id, {"finalidade": "aluguel", "zonas": ["zona oeste"]})
    total = sum(c["pontos"] for c in score_breakdown(lead))
    assert total == lead.score
