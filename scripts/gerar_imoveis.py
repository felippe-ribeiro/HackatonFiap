"""Gera a base simulada de imóveis (data/imoveis.json) de forma determinística.

Uso:  python -m scripts.gerar_imoveis

Os valores buscam uma faixa plausível para São Paulo (2024/2025): studios de ~R$ 250–500 mil,
apartamentos de 2 dorm. de ~R$ 450 mil a R$ 1,1 mi conforme a região e o estado do imóvel.
"""

from __future__ import annotations

import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "imoveis.json"

RNG = random.Random(42)

BAIRROS = {
    "zona sul": ["Moema", "Vila Mariana", "Campo Belo", "Brooklin", "Saúde", "Jabaquara", "Chácara Klabin", "Cursino"],
    "zona oeste": ["Pinheiros", "Perdizes", "Vila Madalena", "Butantã", "Lapa", "Pompeia", "Vila Leopoldina"],
    "zona norte": ["Santana", "Tucuruvi", "Água Fria", "Mandaqui", "Casa Verde"],
    "zona leste": ["Tatuapé", "Mooca", "Anália Franco", "Vila Prudente", "Belém"],
    "centro": ["Higienópolis", "Bela Vista", "República", "Consolação", "Santa Cecília"],
}
# Peso das zonas (o roteiro de demo acontece em zona sul / oeste)
ZONA_PESOS = {"zona sul": 34, "zona oeste": 26, "zona norte": 14, "zona leste": 14, "centro": 12}

TIPOS = ["apartamento"] * 6 + ["studio"] * 3 + ["cobertura"] + ["casa"] + ["casa em condomínio"]

CARACTERISTICAS = [
    "varanda gourmet", "academia", "piscina", "portaria 24h", "salão de festas",
    "coworking", "pet place", "playground", "quadra poliesportiva", "sacada integrada",
    "armários planejados", "ar-condicionado", "vaga para visitante", "gerador",
    "próximo ao metrô", "reformado", "andar alto", "vista livre", "sol da manhã",
    "aceita financiamento", "mobiliado", "lavanderia coletiva", "bicicletário",
]

PROXIMIDADES = [
    "a 400m da estação de metrô", "em frente a um parque", "próximo a escolas e hospitais",
    "a 10 min do centro empresarial", "com comércio e serviços na esquina",
    "em rua tranquila e arborizada", "a uma quadra da av. principal",
]

# R$/m² de referência por zona (imóvel padrão, estado médio)
M2_ZONA = {
    "zona sul": 9800, "zona oeste": 8900, "centro": 7200, "zona norte": 5600, "zona leste": 6100,
}
FATOR_TIPO = {"studio": 0.92, "apartamento": 1.0, "cobertura": 1.3, "casa": 1.05, "casa em condomínio": 1.15}


def _preco_venda(tipo: str, zona: str, area: float, fator_condicao: float) -> float:
    base = area * M2_ZONA[zona] * FATOR_TIPO[tipo] * fator_condicao
    return round(base, -3)


def gerar(n: int = 120) -> list[dict]:
    zonas_pool = [z for z, w in ZONA_PESOS.items() for _ in range(w)]
    imoveis: list[dict] = []
    for i in range(1, n + 1):
        zona = RNG.choice(zonas_pool)
        bairro = RNG.choice(BAIRROS[zona])
        tipo = RNG.choice(TIPOS)
        finalidade = "aluguel" if RNG.random() < 0.33 else "venda"

        if tipo == "studio":
            quartos, area = 0, RNG.randint(22, 42)
        elif tipo in ("casa", "casa em condomínio"):
            quartos = RNG.randint(3, 5)
            area = RNG.randint(42 * quartos, 65 * quartos)
        elif tipo == "cobertura":
            quartos = RNG.randint(2, 4)
            area = RNG.randint(30 * quartos + 25, 48 * quartos + 35)
        else:  # apartamento — distribuição puxada para 1–3 dorm.
            quartos = RNG.choices([1, 2, 3, 4], weights=[18, 40, 30, 12])[0]
            area = RNG.randint(20 * quartos + 14, 32 * quartos + 16)

        suites = min(quartos, RNG.randint(0, 2)) if quartos else 0
        banheiros = max(1, quartos - RNG.randint(0, 1))
        vagas = 0 if (tipo == "studio" and RNG.random() < 0.55) else RNG.randint(1, min(3, max(1, quartos)))

        ano = RNG.randint(1975, 2024)
        # imóvel mais antigo / sem reforma => desconto; reformado / novo => ágio
        fator_condicao = RNG.uniform(0.70, 1.12)
        if ano < 1995 and RNG.random() < 0.6:
            fator_condicao = min(fator_condicao, RNG.uniform(0.70, 0.9))

        preco_venda = max(230_000, _preco_venda(tipo, zona, area, fator_condicao))
        if finalidade == "aluguel":
            preco = max(1300, round(preco_venda * RNG.uniform(0.0038, 0.0058), -1))
            condominio = round(area * RNG.uniform(9, 22), -1)
            rentab = None
        else:
            preco = preco_venda
            condominio = round(area * RNG.uniform(8, 20), -1)
            aluguel_estimado = preco * RNG.uniform(0.0034, 0.0056)
            rentab = round(aluguel_estimado * 12 / preco * 100, 2)

        carac = RNG.sample(CARACTERISTICAS, RNG.randint(3, 7))
        if ano >= 2015:
            carac = sorted(set(carac) | {"aceita financiamento"})
        prox = RNG.choice(PROXIMIDADES)
        titulo = f"{tipo.capitalize()} {('de ' + str(quartos) + ' dorm.') if quartos else 'studio'} em {bairro}"
        descricao = (
            f"{titulo}, {area} m² de área útil, {bairro} ({zona}, São Paulo). "
            f"{(str(quartos) + ' dormitórios') if quartos else 'Ambiente integrado (studio)'}"
            f"{f', sendo {suites} suíte(s)' if suites else ''}, "
            f"{banheiros} banheiro(s), {vagas} vaga(s) de garagem. Construído em {ano}. "
            f"Imóvel {prox}. Diferenciais: {', '.join(carac)}. "
            f"Ideal para quem busca {'renda com locação' if rentab else 'morar bem'} na região {zona}."
        )

        imoveis.append(
            {
                "codigo": f"AUR-{i:04d}",
                "titulo": titulo,
                "tipo": tipo,
                "finalidade": finalidade,
                "cidade": "São Paulo",
                "bairro": bairro,
                "zona": zona,
                "preco": float(preco),
                "condominio": float(condominio),
                "iptu": round(preco_venda * 0.0006, 2),
                "quartos": quartos,
                "suites": suites,
                "banheiros": banheiros,
                "vagas": vagas,
                "area_util": float(area),
                "ano_construcao": ano,
                "rentabilidade_aluguel_pct": rentab,
                "descricao": descricao,
                "caracteristicas": carac,
                "status": "disponivel",
            }
        )
    return imoveis


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    dados = gerar(120)
    OUT.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")
    zs = sum(1 for x in dados if x["zona"] == "zona sul" and x["finalidade"] == "venda")
    print(f"{len(dados)} imóveis gravados em {OUT.relative_to(ROOT)} ({zs} em zona sul p/ venda)")


if __name__ == "__main__":
    main()
