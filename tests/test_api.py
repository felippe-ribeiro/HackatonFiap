def test_health(client):
    r = client.get("/")
    assert r.status_code == 200
    assert r.json()["modo_ia"].startswith("simulado")


def test_chat_fluxo_basico(client):
    r = client.post(
        "/chat",
        json={"external_id": "api-1", "message": "Quero comprar apartamento na zona sul", "canal": "web"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["intent"] == "compra"
    assert body["reply"]
    assert body["lead_id"] > 0


def test_chat_qualifica_e_lista_lead(client):
    ext = "api-2"
    for msg in [
        "quero alugar na zona oeste",
        "até 4 mil de aluguel",
        "2 quartos",
        "tenho pressa, mudança mês que vem",
        "meu email é cliente@teste.com",
        "pode me mostrar as opções?",
    ]:
        r = client.post("/chat", json={"external_id": ext, "message": msg})
        assert r.status_code == 200

    lead_id = r.json()["lead_id"]
    detail = client.get(f"/leads/{lead_id}").json()
    assert detail["intent"] == "aluguel"
    assert detail["score"] >= 60
    assert "reply" not in detail  # sanity


def test_busca_imoveis_endpoint(client):
    r = client.get("/imoveis/busca", params={"q": "studio para investir", "k": 3})
    assert r.status_code == 200
    assert len(r.json()) <= 3
