# Roadmap por gates

| Gate | Objetivo | Aprendizado | Critério de PASS |
|---|---|---|---|
| 0 — Descoberta e Fundação — PASS | documentação, ICP, fontes, taxonomia, modelo, arquitetura e riscos | fundação e rastreabilidade | todos os documentos criados; nenhuma implementação funcional; hipóteses identificadas como hipóteses |
| 1 — Coleta PNCP/CPS — PASS | primeiro pipeline real | Python, HTTP, JSON, paginação, timeout, retries, persistência Bronze | PNCP oficial validado; coleta limitada real e Bronze preservado; CPS auditado sem integração por falta de API clara/atual validada |
| 2 — Normalização — PASS | criar Silver | schema, validação, deduplicação | schema derivado de payload real; Bronze imutável; Silver validado, deduplicável e rastreável; rejeições auditáveis; testes e execução real aprovados |
| 3 — Opportunity Engine determinístico — PASS | regras e priorização | classificação lexical, scoring explicável | regras versionadas, Golden Cases, métricas, Gold rastreável e resultados auditáveis |
| 4 — API e Dashboard MVP — PASS | consulta e visualização | API, filtros, consulta, visualização | FastAPI somente leitura e SPA local consultam Gold real; filtros, paginação, detalhe explicável, testes backend e build frontend aprovados; Bronze/Silver e baseline Gate 3 preservados |
| 4.5 — Corpus Real de Avaliação e Human Review — PASS | ground truth real e avaliação humana | amostragem direcionada, matriz de confusão, F1 Score | 1.760 registros PNCP reais coletados; 24 relevantes identificados pelo baseline determinístico; corpus representativo de 76 registros reais congelado em `reports/evaluation_corpus_v0.1.0.csv` (`v0.1.0`) com SHA-256 registrado; campos `human_*` estritamente vazios; script de métricas independente e testes aprovados |
| 4.6 — Human Annotation & Ground Truth — PASS | curadoria humana de referência | rotulagem por William, blind review | 76/76 registros revisados por William em `reports/human_annotations_v0.1.0.csv`; baseline avaliado: Accuracy 77.63%, Precision 37.50%, Recall 81.82%, F1 51.43% |
| 5 — Classificação com LLM & Benchmark — PASS | enriquecer classificação | prompting, structured output, avaliação regra vs LLM | benchmark completo NVIDIA `openai/gpt-oss-20b`: 76/76 válidos, Accuracy 84.21%, Precision 47.83%, Recall 100.00%, F1 64.71% (supera baseline em +13.28 pp de F1); prompt v0.1.0 e rules v0.1.1 congelados |
| 5D — Development Set & Hybrid Policy Lab — PASS | governança experimental sem vazamento | separação DEV/TEST, amostragem balanceada, imutabilidade | 120 registros coletados da janela posterior, balanceados em 5 buckets, zero overlap com Test Set, manifest e hash SHA-256 congelados |
| 5D.1 — Blind Human Annotation (DEV) — EM ANDAMENTO | curadoria humana de calibração | blind review estrito, validação semântica cruzada, interface web | API e SPA preparadas com validação semântica estrita (HTTP 422), máscara total de predições, 122 testes aprovados; aguardando revisão manual de William (0/120) |
| 6 — RAG | recuperação fundamentada | embeddings, vector DB, recuperação, grounding | respostas ancoradas em evidências recuperadas |
| 7 — Agentic AI | workflow agêntico | LangGraph, estado, tool calling, multi-step workflow | guardrails e avaliação demonstram controle |
| 8 — LLMOps | operação de LLM | LiteLLM, custos, tokens, latência, tracing, avaliações | métricas e limites operacionais definidos |
| 9 — Data Engineering avançado | escala batch | Lakehouse, Spark, batch | volume/complexidade justificam adoção |
| 10 — Event-driven | streaming, se necessário | Kafka/streaming | necessidade de eventos comprovada |
| 11 — Cloud/CI/CD | entrega operacional | Docker, GitHub Actions, AWS, deploy, rollback | deploy repetível e rollback testado |
| 12 — Infra as Code | infraestrutura reproduzível | Terraform | infraestrutura cloud justifica versionamento declarativo |

Todo gate deve registrar PASS/FAIL com evidências antes de avançar.
