# Pitch Técnico — Lária, Agente SDR Imobiliário

> Tech Challenge — Fase 5 (Hackathon FIAP · 8IADT)
> **Aluno:** Felippe de Barros Ribeiro — **RM:** 369425

## 1. O problema (30s)

Imobiliárias perdem leads por **tempo de resposta**, **falta de follow-up** e **corretores
sobrecarregados** com contatos que ainda não estão prontos. Quem responde primeiro, e de forma
consistente, converte mais.

## 2. A solução

**Lária** é uma agente SDR de IA generativa que atende o lead 24/7 em linguagem natural,
**qualifica** enquanto conversa, **busca imóveis** de verdade, **agenda** a visita e só então
entrega ao corretor um lead quente com **resumo pronto**. Quem parou de responder recebe
**follow-up automático** com contexto.

## 3. Como funciona (arquitetura)

- **Canal desacoplado**: simulador web hoje; Telegram/WhatsApp trocando só o *adapter*
  (`runner.responder` é o único ponto de entrada).
- **Multiagente com LangGraph**: um supervisor classifica a intenção e roteia para o
  **agente de vendas** (moradia) ou o **agente de investimento**, cada um com prompt próprio e
  as mesmas 6 ferramentas (buscar imóveis, consultar conhecimento, registrar qualificação,
  listar horários, agendar, encaminhar ao corretor).
- **RAG em 2 frentes**: catálogo de imóveis (semântico + filtros) e base de conhecimento
  (financiamento, locação, investimento, processo) — sempre com **citação da fonte**.
- **Lead scoring explicável** (0–100 por regras auditáveis) — o corretor vê *por que* o lead
  está no topo da fila.
- **Observabilidade nativa**: custo, tokens, latência por etapa e caminho do agente no dashboard.

## 4. Diferenciais implementados

✅ RAG (imóveis + protocolos) · ✅ Multiagentes (LangGraph) · ✅ Memória conversacional ·
✅ Follow-up automático (APScheduler) · ✅ Observabilidade · ✅ Dashboard · ✅ Docker ·
✅ Adapter de Telegram · ✅ Modo simulado (roda sem custo de API) · ✅ Segurança/LGPD e guardrails

## 5. Demonstração (jornada, ~4 min)

1. "Procuro apê na zona sul" → intenção + qualificação progressiva, **score subindo ao vivo**.
2. "Me mostra opções" → imóveis reais via RAG → "quero visitar" → **agendamento**.
3. Nova conversa "quero investir para renda" → **roteia para o agente de investimento**.
4. Aba **Follow-up**: reengaja leads parados. Aba **Leads**: resumo para o corretor.
5. Aba **Observabilidade**: custo e latência do atendimento.

## 6. Decisões técnicas que valem destacar

| Decisão | Porquê |
|---|---|
| Vector store próprio (NumPy) | Sem dependência nativa → portável, transparente, fácil de auditar; troca por pgvector documentada |
| Modo simulado determinístico | Demo, testes e CI sem chave/custo; mesma jornada do modo real |
| Scoring por regras, não por LLM | Priorização **explicável** e estável — requisito de confiança do corretor |
| Núcleo agnóstico de canal | "Migrar depois" para Telegram/WhatsApp é plugar adapter, não reescrever |

## 7. Evolução / produção

Postgres + pgvector · worker de follow-up com fila · Telegram/WhatsApp Business ·
OpenTelemetry + Langfuse · A/B de prompts · integração com CRM real · voz (Whisper + TTS).

## 8. Números da POC

- 80 imóveis simulados · 5 cartilhas na base de conhecimento · 6 ferramentas de agente
- 14 testes automatizados · API REST + 6 telas · sobe com 1 comando (`docker compose up`)
