# Lária — Agente SDR Imobiliário com IA Generativa

> Tech Challenge — Fase 5 (Hackathon FIAP · 8IADT) · Prova de Conceito de um agente SDR
> (Sales Development Representative) para o mercado imobiliário.
>
> **Aluno:** Felippe de Barros Ribeiro

**Lária** é a agente virtual de pré-vendas da *Aurora Imóveis* (imobiliária fictícia de São Paulo).
Ela atende leads em linguagem natural, **qualifica**, identifica **intenção** (compra, aluguel ou
investimento), **busca imóveis** numa base simulada via RAG, **agenda visitas/reuniões**, faz
**follow-up automático** de quem some e entrega um **resumo inteligente** para o corretor humano —
tudo observável num **dashboard**.

---

## 🧠 Como a IA é usada

| Recurso | Implementação |
|---|---|
| **LLM** | OpenAI `gpt-4o-mini` (configurável) via LangChain |
| **Orquestração multiagente** | **LangGraph**: nó supervisor `classificar_intencao` → roteia para `agente_vendas` ou `agente_investimento` (ambos ReAct agents com ferramentas) |
| **Ferramentas do agente** | `buscar_imoveis`, `consultar_conhecimento`, `registrar_dados_do_lead`, `listar_horarios`, `agendar_visita`, `encaminhar_para_corretor` |
| **RAG** | Índice vetorial próprio (NumPy + embeddings `text-embedding-3-small`), 2 coleções: **imóveis** (busca semântica + filtro estruturado) e **base de conhecimento** (financiamento, locação, investimento, processo de compra) com **citação da fonte** |
| **Memória conversacional** | Histórico persistido por lead (SQLite) + perfil estruturado incremental |
| **Lead scoring** | Regras **explicáveis** (0–100), cada ponto com justificativa — ver painel "Score explicável" |
| **Follow-up** | Job APScheduler + geração de mensagem contextual pela LLM |
| **Observabilidade** | Trilha de eventos (nós, tools, tokens, custo estimado, latência) + logs JSON |
| **Modo simulado** | Sem `OPENAI_API_KEY`, um motor determinístico reproduz a jornada (demo/CI/testes) |

> **Segurança:** a Lária não aprova crédito, não dá parecer jurídico e sempre encaminha a
> decisão final ao corretor humano. Coleta apenas dados necessários ao atendimento (LGPD).

---

## 🏗️ Arquitetura (resumo)

```
Canal (Simulador web / Telegram / API)
        │  runner.responder(external_id, texto, canal)   ← ponto único, agnóstico de canal
        ▼
  LangGraph  ──►  classificar_intencao ──►  agente_vendas / agente_investimento (ReAct + tools)
        │                                        │
        ▼                                        ▼
   SQLite (leads, mensagens,             RAG (imóveis + base de conhecimento)
   agendamentos, resumos, eventos)
        │
        ▼
   Dashboard (Streamlit)  +  Follow-up automático (APScheduler)
```

Detalhes, decisões e caminho de escala em [`ARQUITETURA.md`](ARQUITETURA.md).
Relatório técnico completo em [`RELATORIO_TECNICO.md`](RELATORIO_TECNICO.md) / [`RELATORIO_TECNICO.pdf`](RELATORIO_TECNICO.pdf).
Pitch técnico em [`PITCH.md`](PITCH.md) · Roteiro do vídeo em [`ROTEIRO_VIDEO.md`](ROTEIRO_VIDEO.md).

> Os PDFs são gerados a partir dos `.md` com `python -m scripts.gerar_pdf`
> (requer `pip install -r requirements-dev.txt`).

---

## 🚀 Como executar

### Opção A — local (Python 3.12+)

```bash
python -m venv .venv
source .venv/Scripts/activate      # Windows Git Bash / PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt

cp .env.example .env                # opcional: coloque sua OPENAI_API_KEY
python -m scripts.seed_db           # cria banco + base de imóveis + índice RAG + leads demo

# Terminal 1 — API
uvicorn app.main:app --reload

# Terminal 2 — Dashboard + Simulador
streamlit run dashboard/Home.py
```

- Dashboard: <http://localhost:8501>  ·  API docs: <http://localhost:8000/docs>
- **Sem chave da OpenAI?** Funciona em *modo simulado* (respostas determinísticas). Para IA real,
  preencha `OPENAI_API_KEY` no `.env`.

### Opção B — Docker

```bash
cp .env.example .env                # coloque OPENAI_API_KEY (ou USE_FAKE_LLM=true)
docker compose up --build
```

API em `:8000`, dashboard em `:8501`, dados num volume persistente.

### Opção C — bot de Telegram (diferencial)

```bash
# crie um bot no @BotFather e coloque TELEGRAM_BOT_TOKEN no .env
python -m app.channels.telegram    # long-polling, não precisa de URL pública
```

---

## 🎬 Roteiro de demonstração (jornada completa)

1. **Simulador** → "Estou procurando apartamento na zona sul" → agente entende a **intenção**.
2. Responder preço, dormitórios, urgência → ver o **score subir** no painel lateral em tempo real.
3. "Pode me mostrar as opções?" → agente traz imóveis reais da base (**RAG**).
4. "Quero agendar uma visita" → agente oferece horários e **agenda** (aba *Agendamentos*).
5. "Quero investir para renda" (nova conversa) → roteamento para o **agente de investimento**.
6. Aba **Follow-up** → simular/executar reengajamento de leads parados.
7. Aba **Leads** → abrir um lead, ver **score explicável**, transcrição e **resumo para o corretor**.
8. Aba **Observabilidade** → custo estimado, latência por etapa e caminho do agente.

---

## 🧪 Testes

```bash
pytest -q                      # 14 testes (modo simulado, sem custo de API)
python -m scripts.avaliar      # mini-suite de avaliação (extração, RAG imóveis, RAG conhecimento)
```

Cobrem extração de sinais, lead scoring, RAG (imóveis + conhecimento), endpoints da API e
follow-up. Rodam em modo simulado (sem custo de API).

---

## 📁 Estrutura

```
app/
  agent/         graph (LangGraph), tools, prompts, simple_agent (modo simulado), runner
  rag/           vector_store (NumPy) + retriever (2 índices)
  services/      leads (scoring), scheduling, followup, summary
  channels/      telegram (webhook + polling)
  observability/ tracing (EventLog)
  db/            models (SQLModel), database
  main.py        API FastAPI
dashboard/       Streamlit (Home + 5 páginas)
scripts/         gerar_imoveis, seed_db
data/            imoveis.json, base_conhecimento/*.md, índice e banco (gerados)
tests/
```

---

## 📦 Entregáveis do desafio

| Item | Onde |
|---|---|
| Repositório + README | este repo |
| Arquitetura da solução | [`ARQUITETURA.md`](ARQUITETURA.md) |
| Relatório técnico | [`RELATORIO_TECNICO.md`](RELATORIO_TECNICO.md) |
| Demonstração funcional | Simulador + Dashboard |
| Pitch técnico | [`PITCH.md`](PITCH.md) |
| Explicação da IA utilizada | seção "Como a IA é usada" + `RELATORIO_TECNICO.md` §5 |
| Dockerfile | [`Dockerfile`](Dockerfile) + [`docker-compose.yml`](docker-compose.yml) |
