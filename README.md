# KITCHEN INTEL

> Nome provisório — Agentic Opportunity Intelligence

## Status

**GATE 0 — PASS · GATE 1 — PASS · GATE 2 — PASS · GATE 3 — PASS · GATE 4 — PASS · GATE 4.5 — PASS · GATE 4.6 — PASS · GATE 5 — PASS · GATE 5D — PASS · GATE 5D.1 — EM ANDAMENTO.** Há coleta PNCP para Bronze (1.760 registros), normalização Silver, Opportunity Engine/Gold determinístico (24 oportunidades relevantes identificadas), Test Set de avaliação congelado (`reports/evaluation_corpus_v0.1.0.csv`, 76 registros), anotações humanas 100% concluídas por William (`reports/human_annotations_v0.1.0.csv`), baseline determinístico formalmente avaliado (F1 51.43%), primeiro benchmark completo com LLM concluído (`openai/gpt-oss-20b` sob NVIDIA NIM: 76/76 válidos, Recall 100%, F1 64.71%), Development Set estabelecido e congelado (`reports/development_corpus_v0.1.0.csv`, 120 registros, SHA-256 verificado, zero overlap com Test Set) e ambiente de Blind Review com validação semântica estrita (HTTP 422) preparado para a anotação manual de William (0/120).

## Problema de negócio

Empresas que fornecem cozinhas institucionais/industriais, equipamentos, infraestrutura e manutenção podem depender de prospecção manual ou reativa e perder sinais públicos de compra, reforma, expansão e manutenção.

## Contexto conhecido

- O nome da empresa cliente ainda não foi informado.
- Há indicação histórica de atuação junto a ETECs/Centro Paula Souza e à Fundação CASA; isso é **contexto conhecido a validar**, não uma confirmação de relacionamento vigente.
- O MVP deverá começar pelo setor público e institucional.

## Objetivo

Transformar sinais e dados públicos em oportunidades comerciais explicáveis, priorizadas e rastreáveis para cozinhas, refeitórios e infraestrutura de alimentação.

## Escopo inicial

No Gate 0, o escopo é documental: ICP, fontes candidatas, taxonomia, arquitetura futura, modelo de dados, scoring provisório, riscos e plano de aprendizado. A implementação começa somente após os critérios do próximo gate serem aprovados.

## Público-alvo

Equipe comercial e liderança da futura empresa cliente, além do responsável pelo projeto como laboratório prático de engenharia assistida por IA.

## Princípios

- Fonte e evidência antes de recomendação.
- Explicabilidade, rastreabilidade e validação humana.
- Separação entre atratividade da oportunidade e confiança da evidência.
- Complexidade somente quando justificada.
- IA como acelerador, não como substituta de controle humano.

## Arquitetura conceitual resumida

No futuro, fontes oficiais alimentarão uma camada de dados crus (Bronze), seguida de normalização (Silver), geração de oportunidades orientadas ao negócio (Gold), consulta por API e dashboard. Uma camada agêntica poderá ser adicionada depois, sob controles e evidências.

## Roadmap em gates

0. Descoberta e fundação documental — **PASS**.
1. Coleta inicial PNCP/Centro Paula Souza — **PASS** (integração PNCP; CPS auditado, não integrado).
2. Normalização — **PASS**.
3. Opportunity Engine determinístico — **PASS**.
4. API e dashboard MVP — **PASS**.
4.5. Corpus real de avaliação e human review — **PASS**.
4.6. Human Annotation & Ground Truth — **PASS** (76/76 revisados por William).
5. Classificação com LLM & Benchmark — **PASS** (benchmark completo NVIDIA `openai/gpt-oss-20b`: 76/76, Recall 100%, F1 64.71%).
5D. Development Set & Hybrid Policy Lab — **PASS** (120 registros balanceados, SHA-256 congelado, zero overlap com Test Set).
5D.1. Blind Human Annotation (DEV) — **EM ANDAMENTO** (API e SPA prontas com validação semântica estrita HTTP 422; aguardando revisão manual de William 0/120).
6. RAG.
7. Agentic AI.
8. LLMOps.
9. Data Engineering avançado.
10. Event-driven, se justificado.
11. Cloud/CI/CD.
12. Infraestrutura como código.

Os critérios completos estão em [docs/07_GATES.md](docs/07_GATES.md).

## Objetivo de Aprendizado

O projeto também será um laboratório prático de Python, APIs, JSON, pipelines, modelagem de dados, RAG, Agentic AI, LangGraph, LLM gateways, observabilidade, avaliação de LLM, CI/CD, containers, AWS, Lakehouse, Spark, Kafka e Terraform. Essas tecnologias **não** serão adicionadas todas no início: cada uma só entra no gate em que houver necessidade e justificativa arquitetural.

## Como se orientar

Comece por [docs/00_VISAO.md](docs/00_VISAO.md) e siga a numeração dos documentos. Regras obrigatórias para agentes estão em [AGENTS.md](AGENTS.md).

## Executar a coleta PNCP

Instale as dependências e execute sempre com período e limite explícitos:

```powershell
python -m pip install -r requirements.txt
python scripts/collect_pncp.py --start-date 20260911 --end-date 20260911 --modality-code 6 --page-size 10 --max-pages 1
```

As datas usam `AAAAMMDD`. A API oficial atualmente exige `page-size` mínimo de 10. O script salva respostas brutas em `data/bronze/pncp/`; ele não classifica oportunidades nem executa qualquer regra comercial.

## Executar a normalização PNCP

```powershell
python scripts/normalize_pncp.py
```

O comando lê apenas Bronze, gera um snapshot JSON Lines e manifest em `data/silver/pncp/` e nunca altera os arquivos de origem. Use `--limit N` somente para limitar registros processados localmente.

## Executar o Opportunity Engine

```powershell
python scripts/build_opportunities.py --as-of 2026-09-12
python scripts/run_gate3_baseline.py --as-of 2026-09-12
```

O primeiro comando lê Silver e grava Gold rastreável; o segundo executa os Golden Cases e salva `reports/baseline_gate3.json`. Ambos usam regras determinísticas versionadas em `config/opportunity_rules.json`.

## Executar a API e o dashboard MVP

O Gate 4 oferece somente consulta local e de leitura sobre o snapshot Gold mais recente; não há autenticação, banco de dados ou escrita de dados pela interface.

Em um terminal, instale as dependências Python e inicie a API:

```powershell
python -m pip install -r requirements.txt
python -m uvicorn src.api.app:app --host 127.0.0.1 --port 8000
```

Em outro terminal, inicie a SPA React/Vite:

```powershell
Set-Location frontend
npm install
npm run dev
```

O frontend usa `VITE_API_BASE_URL` (veja `frontend/.env.example`) para definir a URL da API. A documentação dos endpoints, filtros e limitações está em [docs/11_API_E_DASHBOARD.md](docs/11_API_E_DASHBOARD.md).

## Executar o Corpus de Avaliação e Avaliação Humana (Gates 4.5 e 4.6)

Para gerar deterministicamente o dataset balanceado para revisão humana (`reports/evaluation_corpus_v0.1.0.csv`):

```powershell
python scripts/build_human_review_corpus.py
```

Para executar a curadoria humana:
1. Inicie a API (`python -m uvicorn src.api.app:app --host 127.0.0.1 --port 8000`)
2. Inicie a interface web (`cd frontend; npm run dev`)
3. Acesse `http://localhost:5173` e abra a aba **"Revisão Humana & Ground Truth (Corpus v0.1.0)"**.
4. O modo **Blind Review** oculta as predições do sistema por padrão para anular o viés de ancoragem. As anotações são salvas imediatamente em `reports/human_annotations_v0.1.0.csv`.

Para calcular as métricas formais contra o Ground Truth:

```powershell
# Execução padrão (exige 100% dos 76 registros revisados):
python scripts/evaluate_baseline_human.py

# Inspeção preliminar de métricas parciais durante o processo:
python scripts/evaluate_baseline_human.py --allow-partial
```

Enquanto houver registros pendentes, a avaliação formal é bloqueada com status informativo, garantindo que ausência de preenchimento nunca seja tratada como dado falso. Documentação metodológica em [docs/12_CORPUS_AVALIACAO.md](docs/12_CORPUS_AVALIACAO.md) e manual de curadoria em [docs/13_GUIA_REVISAO_HUMANA.md](docs/13_GUIA_REVISAO_HUMANA.md).

## Executar a Classificação com LLM e Avaliação (Gate 5)

O Gate 5 introduz a classificação por LLM sob o modelo fixo `gemini-2.5-flash` (temperature 0.0) diretamente via HTTP, sem LangChain, operando sobre os 7 campos públicos sem vazamento de dados.

Para verificar o progresso atual do benchmark sem realizar chamadas de rede:

```powershell
python scripts/run_llm_classification.py --progress
```

Para estimar previamente o custo máximo da inferência:

```powershell
python scripts/run_llm_classification.py --phase full --estimate-cost
```

Para executar a classificação em lotes incrementais seguros (máx. 15 novas chamadas por vez):

```powershell
python scripts/run_llm_classification.py --phase full --max-new-calls 15
```

Registros já processados são devolvidos instantaneamente do cache determinístico (`data/cache/llm_cache_v0.1.0.json`) sem consumir cota. Ao atingir a cota diária do modelo (`RATE_LIMIT_DAILY_REACHED`), o script grava os resultados consolidados e realiza uma interrupção limpa com código 0.

Para avaliar o resultado contra o Ground Truth e comparar com o Baseline:

```powershell
python scripts/evaluate_llm_human.py
```
*(A avaliação formal permanece bloqueada com status `BENCHMARK INCOMPLETE — X/76` até que todos os 76 registros tenham sido concluídos sob o mesmo modelo).*

Documentação metodológica completa em [docs/14_LLM_CLASSIFICATION.md](docs/14_LLM_CLASSIFICATION.md).
