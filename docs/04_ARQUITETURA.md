# Arquitetura evolutiva

## Fase MVP conceitual

```text
Fontes → Coleta → Bronze → Normalização → Silver → Opportunity Engine → Gold → API → Dashboard
```

## Estado implementado até o Gate 4

As etapas **Coleta → Bronze → Normalização → Silver → Opportunity Engine → Gold → API → Dashboard** estão implementadas para PNCP. A interface é um MVP local de consulta; ela não escreve em nenhuma camada nem substitui revisão humana.

- **Bronze:** dados crus, imutáveis e próximos da fonte, preservando origem e momento de captura. No coletor PNCP, `captured_at` é sempre gerado em **UTC** (`+00:00`).
- **Silver:** dados normalizados, deduplicados e validados, ainda com ligação à origem. O Silver PNCP é reconstruível a partir dos JSON Bronze e preserva `source_file`, `source_files`, `captured_at` e a versão do schema.
- **Gold:** dados orientados ao negócio, como oportunidades, evidências e scores explicáveis. O Gate 3 produz JSONL e manifest a partir de Silver, com regras determinísticas versionadas; não usa IA e não altera Silver.
- **API:** FastAPI somente leitura que carrega o snapshot Gold JSONL mais recente e expõe saúde, estatísticas, lista, detalhe e evidências. Não há PostgreSQL neste gate: o volume é pequeno, o Gold é reconstruível e um arquivo JSONL torna o fluxo mais simples de auditar.
- **Dashboard:** SPA React/Vite que consome a API por HTTP e monta filtros, tabela, indicadores e detalhe explicável exclusivamente a partir dos campos Gold. A URL da API é configurada por `VITE_API_BASE_URL`; CORS é limitado às origens locais de desenvolvimento explicitamente permitidas.

O fluxo implementado no Gate 4 é:

```text
Browser → SPA React/Vite → HTTP GET → FastAPI → Gold JSONL (somente leitura)
```

## Estado implementado nos Gates 4.5 e 4.6 (Corpus de Avaliação e Ground Truth)

Para possibilitar benchmarking científico entre baseline determinístico, modelos de IA e revisor humano sem viés:
1. **Corpus de Avaliação Imutável (`reports/evaluation_corpus_v0.1.0.csv`):** 76 registros reais do PNCP estratificados, congelados com hash SHA-256 (`6a2961b6e1849616d163775287f24703afc3d435a871dc9569d38eecf12918f8`).
2. **Anotações Humanas Isoladas (`reports/human_annotations_v0.1.0.csv`):** arquivo separado para as anotações do revisor William, prevenindo acidentes de integridade no corpus.
3. **Mecanismo de Blind Review:** a interface web oculta as predições determinísticas em registros pendentes para anular o viés de ancoragem (anchoring bias).
4. **API de Curadoria:** endpoints `GET /review`, `GET /review/{review_id}`, `PUT /review/{review_id}` e `GET /review/export`.
5. **Script de Benchmark (`scripts/evaluate_baseline_human.py`):** realiza o join dos dois arquivos por `(review_id, source_record_id)` e exige 100% de anotações preenchidas por padrão antes de computar as métricas formais (ou `--allow-partial` para diagnóstico).

```text
Corpus Imutável (CSV) ──┐
                         ├── Join ──→ Benchmark Formal (evaluate_baseline_human.py)
Anotações Humanas (CSV) ─┘   ▲
       ▲                     │
       └─ PUT /review/{id} ──┴─ SPA React (Modo Blind Review)
```

Detalhamento em `docs/12_CORPUS_AVALIACAO.md` e `docs/13_GUIA_REVISAO_HUMANA.md`.

## Estado implementado no Gate 5 (Classificação com LLM & Avaliação)

Para avaliar cientificamente se um modelo de linguagem supera o baseline determinístico sem vazamento de dados:
1. **Zero Data Leakage:** O módulo `LLMClassifier` filtra estritamente os 7 campos públicos essenciais do edital e bloqueia qualquer acesso a `human_*` ou `baseline_*`.
2. **Chamada Direta HTTP (Sem LangChain/RAG):** Inferência direta via REST API (`httpx`) com `gpt-4o-mini` (temperature 0.0), reduzindo sobrecarga e dependências.
3. **Structured Output Rigoroso:** Resposta JSON validada por schema Pydantic (`LLMStructuredOutput`) com categorias fechadas e até 1 retry em caso de schema inválido.
4. **Cache Criptográfico de Inferência:** Cache em disco (`llm_cache_v0.1.0.json`) indexado por SHA-256 de `input_hash + provider + model + prompt_version`.
5. **Governança Orçamentária:** Trava de segurança automática de US$ 2,00 e registro de tokens/custo/latência em `reports/llm_cost_gate5.json`.
6. **Pipeline de Avaliação e Auditoria:** O script `scripts/evaluate_llm_human.py` cruza predições com as anotações de William, gerando `reports/gate5_comparison.json` e o relatório descritivo de Falsos Positivos e Falsos Negativos em `reports/gate5_error_analysis.md`.

```text
Corpus Imutável (CSV) ──(7 campos públicos)──→ LLMClassifier (gemini-2.5-flash)
                                                       │
                                                Cache SHA-256
                                                       │
                                                Validação Pydantic
                                                       ↓
                                          reports/llm_predictions_v0.1.0.jsonl
                                                       │
                                                       ├── Join (evaluate_llm_human.py)
Anotações Humanas (human_annotations_v0.1.0.csv) ──────┘
                                                       ↓
                                          reports/gate5_comparison.json
                                          reports/gate5_error_analysis.md
```

Detalhamento em `docs/14_LLM_CLASSIFICATION.md`.

### Benchmark B independente — Groq

O Gate 5 também suporta um segundo benchmark independente pelo provedor Groq, sem alterar nem reutilizar resultados do benchmark Gemini. O mesmo `LLMClassifier`, a filtragem dos 7 campos públicos e a validação Pydantic são reutilizados; o roteamento HTTP é específico do provedor. Para evitar mistura semântica, o padrão de saída é `reports/llm_predictions_groq_v0.1.0.jsonl` e o cache continua segregado criptograficamente por `input_hash + provider + model + prompt_version`.

Configuração congelada do benchmark B: `provider=groq`, `model=openai/gpt-oss-120b`, `prompt_version=0.1.0`, `temperature=0.0` e `reasoning_effort=low`. Credenciais permanecem apenas na variável local `GROQ_API_KEY`.

## Arquitetura futura

### Experimento independente — OpenAI / GPT-5.6 Luna

O experimento OpenAI reutiliza o classificador, os sete campos públicos de entrada e a validação Pydantic. Seus resultados não compartilham arquivos de predição ou de custo com Gemini ou Groq: as saídas são `reports/llm_predictions_openai_v0.1.0.jsonl` e `reports/llm_cost_openai_gate5.json`. A configuração fixa é `provider=openai`, `model=gpt-5.6-luna`, `prompt_version=0.1.0`, `temperature=0.0` e `reasoning_effort=none`. O endpoint `v1/chat/completions`, suportado oficialmente pelo modelo, usa JSON Schema estrito e a credencial somente local `OPENAI_API_KEY`.

### Experimento independente — OpenRouter

O OpenRouter é roteado por HTTP compatível com OpenAI, mas permanece segregado por provider, modelo, cache e arquivos de saída. O primeiro modelo fixado é `nvidia/nemotron-3-super-120b-a12b:free`; não se usa `openrouter/free` nem fallback automático. As saídas são `reports/llm_predictions_openrouter_v0.1.0.jsonl` e `reports/llm_cost_openrouter_gate5.json`, com JSON Schema estrito e credencial local `OPENROUTER_API_KEY`.

### Provedores Adicionais Independentes — Cerebras e NVIDIA API Catalog

Foram integrados dois novos provedores de inferência rápida e padronizada via API OpenAI-compatible:
1. **Cerebras (`https://api.cerebras.ai/v1`):** Suporte nativo a inferência ultra-rápida. Endpoint de chat completions com autenticação via `CEREBRAS_API_KEY`. O status operacional atual é BLOCKED devido à política de billing/crédito da conta (HTTP 402 `payment_required`).
2. **NVIDIA API Catalog / NIM (`https://integrate.api.nvidia.com/v1`):** Provedor de inferência corporativa NVIDIA com autenticação via `NVIDIA_API_KEY`. O modelo selecionado e validado em Smoke (5) e Sample (10) é `openai/gpt-oss-20b`, operando com `response_format={"type": "json_object"}` e validação estrita Pydantic. Saídas segregadas em `reports/llm_predictions_nvidia_v0.1.0.jsonl` e `reports/llm_cost_nvidia_gate5.json`.

## Estado implementado no Gate 5D (Development Set & Hybrid Policy Lab)

Para viabilizar experimentação, tuning de prompts (Prompt v0.2.0), calibração de guardrails determinísticos e políticas de ensemble sem violar a integridade estatística do Test Set:
1. **Separação Formal TRAIN / DEV / TEST:**
   - `TEST SET` (`reports/evaluation_corpus_v0.1.0.csv`, 76 registros): Imutável e permanentemente congelado para avaliação final.
   - `DEV SET` (`reports/development_corpus_v0.1.0.csv`, 120 registros): Coletado de janela temporal posterior ao Test Set (`2026-09-11` a `2026-09-12`), com IDs dedicados (`DEV-001` a `DEV-120`), zero overlap absoluto e balanceamento em 5 buckets (30 potenciais relevantes, 30 hard negatives, 20 negative context, 20 óbvios negativos e 20 ambíguos/borderline).
2. **Blind Review Nativo na API (`/review/dev`):**
   - Endpoints dedicados `GET /review/dev`, `GET /review/dev/export`, `GET /review/dev/{id}` e `PUT /review/dev/{id}`.
   - Modo blind estrito: o payload de detalhe do edital mascara completamente as predições e scores (`baseline: null`), garantindo que a anotação humana de William seja isenta de viés de ancoragem.
   - Validação semântica estrita (Gate 5D.1): coerência obrigatória entre `human_relevant` e `human_relevance` (`FALSE` exige `IRRELEVANTE` e categorias vazias; `TRUE` exige `ALTA`/`MEDIA`/`BAIXA`), com rejeição HTTP 422 em combinações inconsistentes.
   - Interface SPA atualizada com suporte bidirecional (Dev Set / Test Set), desativação de categorias em itens irrelevantes e avanço automático.
   - Persistência isolada em `reports/development_annotations_v0.1.0.csv`. Detalhes em `docs/17_DEVELOPMENT_SET.md`.

### Camada Multi-Provider Failover & Provider Cascade (Operacional Futura)

Para suportar alta disponibilidade e resiliência em inferências operacionais futuras sem corromper benchmarks científicos:
1. **Separação Rígida de Modos:**
   - `BENCHMARK_MODE`: Provedor e modelo fixos, sem fallback. Qualquer falha gera erro e interrompe a execução, preservando integridade estatística da amostra (ex.: Gate 5).
   - `PRODUCTION_MODE`: Habilita a cascata declarativa (`config/provider_routing.json`) com prioridade de provedores (ex.: OpenRouter → Gemini → Groq → OpenAI → Determinístico).
2. **Circuit Breaker Determinístico:** Cada provedor possui estados `CLOSED`, `OPEN` e `HALF_OPEN`, isolando provedores com falhas recorrentes e permitindo testes controlados após período de cooldown.
3. **Fallback Determinístico Final:** Se todos os LLMs falharem, o sistema recorre ao motor determinístico (`provider_used="deterministic"`, `model_used="rules_v0.1.1"`), com tokens e custos zerados.
4. **Rastreabilidade e Trilha de Tentativas:** Toda resposta operacional gera `OperationalClassificationResult` contendo a lista completa de `attempt_traces` (provedor, modelo, tentativa, latência, código HTTP, status, erro higienizado sem secrets). Detalhes em `docs/16_MULTI_PROVIDER_FAILOVER.md`.

```text

Gold
  ↓
Agentic Layer
  ├── Scout Agent
  ├── Signal Agent
  ├── Evidence Agent
  ├── RAG Agent
  ├── Scoring Agent
  ├── Commercial Analyst Agent
  └── Evaluator / Guardrail
```

A camada agêntica só poderá operar sobre dados rastreáveis e produzir saídas estruturadas validáveis. Scores determinísticos permanecem governados por regras documentadas.

## Tecnologias futuras: critério de entrada

| Tecnologia | Só entra quando... |
|---|---|
| LangGraph | houver workflow multi-etapas com estado, ferramentas e necessidade clara de orquestração. |
| pgvector/vector DB | RAG exigir recuperação semântica com corpus e avaliação definidos. |
| LiteLLM / gateway LLM | houver mais de um provedor/modelo ou necessidade real de governar custos, limites e roteamento. |
| Observabilidade | houver pipeline ou LLM em operação que exija tracing, métricas e auditoria. |
| Avaliação de LLM | houver uso de LLM com conjunto de casos e critérios mensuráveis. |
| AWS | requisitos de deploy, segurança, escala ou serviços gerenciados justificarem cloud. |
| Spark | volume ou complexidade justificarem processamento distribuído. |
| Kafka | houver necessidade real de processamento orientado a eventos ou streaming. |
| Terraform | infraestrutura cloud recorrente precisar ser versionada e reproduzida. |

Qualquer alteração arquitetural futura atualiza este documento.
