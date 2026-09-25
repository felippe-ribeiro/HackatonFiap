"""Fixtures de teste — tudo roda em modo simulado (sem OpenAI) e em banco temporário."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

_TMP = Path(tempfile.mkdtemp(prefix="laria-test-"))
os.environ.update(
    {
        "USE_FAKE_LLM": "true",
        "OPENAI_API_KEY": "",
        "APP_ENV": "test",
        "FOLLOWUP_ENABLED": "false",
        "DATABASE_URL": f"sqlite:///{(_TMP / 'test.db').as_posix()}",
        "RAG_INDEX_DIR": (_TMP / "index").as_posix(),
    }
)


@pytest.fixture(scope="session", autouse=True)
def _prepare_env():
    from app.db.database import init_db
    from app.rag.retriever import build_indexes
    from scripts.seed_db import carregar_imoveis

    init_db()
    carregar_imoveis()
    build_indexes()
    yield


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        yield c
