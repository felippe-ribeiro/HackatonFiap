"""Camada de acesso ao modelo de linguagem e a embeddings.

Suporta dois modos:
- **real**  : usa a OpenAI (chat + embeddings) quando há OPENAI_API_KEY válida;
- **simulado**: motor determinístico local (USE_FAKE_LLM=true ou sem chave),
  para rodar a demo, os testes e o CI sem custo de API.
"""

from __future__ import annotations

import hashlib
import math
import re
from functools import lru_cache

from app.config import settings
from app.logging_conf import get_logger

log = get_logger(__name__)

# Preço aproximado por 1M de tokens (USD) — usado na estimativa de custo/observabilidade.
_PRICE_PER_MTOK: dict[str, tuple[float, float]] = {
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
    "gpt-4.1-mini": (0.40, 1.60),
    "text-embedding-3-small": (0.02, 0.0),
    "text-embedding-3-large": (0.13, 0.0),
}

_EMBED_DIM = 256


def estimate_cost(model: str, tokens_in: int, tokens_out: int) -> float:
    p_in, p_out = _PRICE_PER_MTOK.get(model, (0.0, 0.0))
    return round((tokens_in * p_in + tokens_out * p_out) / 1_000_000, 6)


def approx_tokens(text: str) -> int:
    """Estimativa barata (~4 chars/token) — evita dependência dura do tiktoken."""
    return max(1, len(text) // 4)


# --------------------------------------------------------------------------- #
# Chat model
# --------------------------------------------------------------------------- #
@lru_cache
def get_chat_model(temperature: float | None = None):
    """Retorna um ChatOpenAI configurado. Só deve ser chamado em modo real."""
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        model=settings.llm_model,
        temperature=settings.llm_temperature if temperature is None else temperature,
        api_key=settings.openai_api_key,
        timeout=40,
        max_retries=2,
    )


def chat_complete(system: str, user: str, temperature: float | None = None) -> str:
    """Chamada simples system+user -> texto. Funciona nos dois modos."""
    if settings.fake_mode:
        return _fake_completion(system, user)

    from langchain_core.messages import HumanMessage, SystemMessage

    model = get_chat_model(temperature)
    resp = model.invoke([SystemMessage(content=system), HumanMessage(content=user)])
    return resp.content if isinstance(resp.content, str) else str(resp.content)


def _fake_completion(system: str, user: str) -> str:
    """Resposta determinística mínima para o modo simulado."""
    u = user.lower()
    if "json" in system.lower() or "responda apenas" in system.lower():
        return "{}"
    if "resumo" in system.lower() or "resuma" in u:
        return (
            "Resumo (modo simulado): lead demonstrou interesse, coletadas informações "
            "básicas de perfil. Recomenda-se contato de um corretor para dar sequência."
        )
    return (
        "Modo simulado ativo — configure OPENAI_API_KEY para respostas reais. "
        "Posso te ajudar a encontrar um imóvel: me conte a região, a finalidade "
        "(compra, aluguel ou investimento) e a faixa de preço."
    )


# --------------------------------------------------------------------------- #
# Embeddings
# --------------------------------------------------------------------------- #
def embed_texts(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    if settings.fake_mode:
        return [_hash_embedding(t) for t in texts]

    from openai import OpenAI

    client = OpenAI(api_key=settings.openai_api_key)
    resp = client.embeddings.create(model=settings.embedding_model, input=texts)
    return [d.embedding for d in resp.data]


def embed_query(text: str) -> list[float]:
    return embed_texts([text])[0]


_TOKEN_RE = re.compile(r"[a-zà-ú0-9]{2,}")


def _hash_embedding(text: str, dim: int = _EMBED_DIM) -> list[float]:
    """Embedding pseudo-semântico determinístico (hashing trick + L2 norm).

    Não substitui um modelo real, mas dá recuperação por sobreposição de termos —
    suficiente para demonstrar o pipeline de RAG offline.
    """
    vec = [0.0] * dim
    tokens = _TOKEN_RE.findall(text.lower())
    for tok in tokens:
        h = int(hashlib.md5(tok.encode()).hexdigest(), 16)
        idx = h % dim
        sign = 1.0 if (h >> 8) % 2 == 0 else -1.0
        vec[idx] += sign
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]
