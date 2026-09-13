# Classificação com LLM & Avaliação Científica — Gate 5

Este documento detalha os fundamentos teóricos, arquiteturais e experimentais da introdução do primeiro modelo de linguagem (LLM) no projeto **KITCHEN INTEL**, com o objetivo de comparar rigorosamente seu desempenho contra o baseline determinístico (Gate 3/4).

---

## 1. Princípio Experimental & Prevenção de Data Leakage

O objetivo do Gate 5 é responder a uma pergunta de engenharia:
> *"Um LLM supera o motor determinístico em precisão sem destruir a cobertura de mercado, a um custo e latência economicamente viáveis?"*

Para garantir que a resposta seja cientificamente válida:
1. **Separação Rígida:** O LLM opera **exclusivamente sobre o corpus de dados públicos** (`reports/evaluation_corpus_v0.1.0.csv`).
2. **Zero Data Leakage:** O payload enviado ao modelo é submetido a uma higienização estrita pela função `LLMClassifier.prepare_input`. São filtrados apenas os 7 campos permitidos:
   - `objeto_original`
   - `orgao_nome`
   - `unidade_nome`
   - `municipio`
   - `uf`
   - `valor_total_estimado`
   - `data_publicacao`
3. **Isolamento do Gabarito:** O modelo **NUNCA** recebe `human_relevant`, `human_relevance`, `human_categories`, `human_notes`, nem os campos do baseline (`baseline_relevance`, `matched_terms`, etc.).
4. **Avaliação Cega:** O gabarito anotado por William em `reports/human_annotations_v0.1.0.csv` é lido unicamente na etapa posterior de avaliação (`scripts/evaluate_llm_human.py`).

---

## 2. Escolha de Provedor e Modelo
 
### Provedor e Modelo Selecionados
- **Provedor:** Google Gemini
- **Modelo Fixo:** `gemini-2.5-flash` (ID canônico estrito retornado pela API, sem aliases mutáveis como `gemini-flash-latest`)
- **Data do Experimento:** 12 de setembro de 2026
 
### Razões da Escolha
1. **Capacidade de Raciocínio Contextual:** Apresenta excelente discernimento de contexto semântico (diferenciando ar-condicionado predial de exaustão de cozinha, ou inox laboratorial de inox alimentício).
2. **Suporte Nativo a Structured Output:** Permite requisições com `response_format={"type": "json_object"}` e conformidade JSON estrita com validação Pydantic.
3. **Custo Extremamente Acessível:**
   - **Entrada:** US$ 0,075 por 1 milhão de tokens.
   - **Saída:** US$ 0,300 por 1 milhão de tokens.
   - Classificar todo o corpus de 76 registros custa aproximadamente **US$ 0,008** (menos de 1 centavo de dólar), ordens de magnitude abaixo do teto de segurança de US$ 2,00.
4. **Respeito à Governança de Quotas e Multi-dias:**
   - O benchmark formal utiliza um **único modelo fixo** para todos os 76 registros (nunca misturando modelos diferentes para contornar cotas).
   - Suporta execução incremental multi-dias via `--max-new-calls` e retomada idempotente via cache determinístico.

### Política de Credenciais e Bloqueio
Em conformidade com a governança de segurança do projeto:
- Nenhuma chave de API é mantida em código-fonte ou versionada.
- O sistema inspeciona as variáveis de ambiente `OPENAI_API_KEY` (ou `ANTHROPIC_API_KEY`).
- Se nenhuma credencial estiver presente, o sistema **bloqueia a execução real e relata o motivo**, sem inventar respostas fakes. Toda a suíte de testes unitários opera com mocks estritos.

---

## 3. Engenharia de Prompt & Versionamento

O prompt do sistema está versionado em [prompts/classifier_v0.1.0.txt](file:///C:/Users/kbadmin/Documents/Projetos/Cozinha%20Industrial/prompts/classifier_v0.1.0.txt).

### Componentes do Prompt
1. **Definição de Persona:** Classificador especializado em oportunidades B2B de cozinhas industriais e refeitórios institucionais.
2. **Taxonomia Fechada:** 9 categorias canônicas permitidas (`COZINHA`, `REFEITORIO`, `INOX`, `COCCAO`, `REFRIGERACAO`, `EXAUSTAO`, `LAVAGEM`, `INFRAESTRUTURA`, `ALIMENTACAO_COLETIVA`).
3. **Escala de Relevância:** Critérios objetivos para `ALTA`, `MEDIA`, `BAIXA` e `IRRELEVANTE`.
4. **Diretrizes Anti-Alucinação e Desambiguação:**
   - Coincidência de palavras isoladas não é suficiente (compreensão do objeto).
   - Exaustores prediais e climatização de escritórios não são cozinha.
   - Aço inox para necrotério, hospital ou odontologia não é cozinha.
   - Gás GLP avulso é irrelevante.
   - Serviços de alimentação/merenda são sinais indiretos (`BAIXA`).
5. **Formato JSON Estrito:** Especificação das chaves e tipos de retorno.

### Proibição de Prompt Tuning sobre o Test Set
O conjunto de 76 registros é nosso **Test Set inicial**. É terminantemente proibido realizar iterações de ajuste de prompt olhando para os erros deste teste e reavaliando sobre o mesmo corpus, pois isso configuraria **Prompt Overfitting**. Quaisquer refinamentos futuros de prompt deverão ser feitos em um **Dev Set** separado.

---

## 4. Structured Output & Validação

A resposta gerada pelo LLM é obrigatoriamente submetida à validação via Pydantic (`LLMStructuredOutput`):

```json
{
  "relevant": true,
  "relevance": "ALTA",
  "categories": ["COZINHA", "COCCAO"],
  "confidence": 95,
  "reason": "Aquisição de fogão industrial de grande porte para cozinha de hospital."
}
```

### Validações Aplicadas
- `relevant`: booleano obrigatório.
- `relevance`: enum estrito (`ALTA`, `MEDIA`, `BAIXA`, `IRRELEVANTE`).
- `categories`: subconjunto verificado contra as 9 categorias canônicas.
- `confidence`: inteiro de 0 a 100.
- `reason`: string de 3 a 2000 caracteres.

### Política de Retry
Caso o LLM retorne JSON malformado ou campos fora do schema:
- O sistema registra o erro de validação.
- Executa no máximo **1 retry** informando o erro específico ao modelo.
- Se persistir inválido, o status é registrado como `ERROR` com rastreabilidade completa, sem correções heurísticas silenciosas.

---

## 5. Cache Determinístico

Para garantir que a mesma entrada nunca gere cobrança dupla de API nem latência desnecessária:
- **Chave de Cache:** SHA-256 de `input_hash + provider + model + prompt_version`.
- **Persistência:** `data/cache/llm_cache_v0.1.0.json`.
- Ao encontrar a chave em disco, o resultado é devolvido instantaneamente com status `CACHED` e latência/custo computacional zerados.

---

## 6. Governança de Custo e Token Accounting

Para cada inferência, o sistema registra:
- `input_tokens`
- `output_tokens`
- `total_tokens`
- `latency_ms`
- `estimated_cost` (em USD)

O relatório consolidado de custos é gravado em `reports/llm_cost_gate5.json` contendo total de chamadas, chamadas em cache, percentis de latência (médio, p50, p95) e custo total.

### Trava Mandatória de Custo
Antes de processar qualquer lote, o script calcula o `ESTIMATED MAX COST`. Se a estimativa ultrapassar **US$ 2,00**, a execução é automaticamente interrompida.

---

## 7. Protocolo de Avaliação & Comparação

Após as inferências, o script `scripts/evaluate_llm_human.py`:
1. Cruza as predições com as anotações de William.
2. Calcula matriz de confusão (TP, FP, TN, FN) e métricas balanceadas (Accuracy, Precision, Recall, F1-Score).
3. Calcula concordância de categorias (Exact Match, Micro Precision, Micro Recall, Micro F1).
4. Carrega o benchmark formal do baseline (`reports/baseline_human_evaluation_v0.1.0.json`) e gera `reports/gate5_comparison.json`.
5. Elabora a análise qualitativa de Falsos Positivos e Falsos Negativos em `reports/gate5_error_analysis.md`.

---

## 8. Execução Incremental & Governança de Quotas (Gate 5)

Para lidar de forma sustentável com cotas de API (ex.: cota diária gratuita do Google AI Studio de 20 RPD por modelo) sem comprometer a integridade científica:

1. **Lotes Incrementais Seguros:** A flag `--max-new-calls N` (ex.: `--max-new-calls 15`) processa apenas registros ainda não classificados, interrompendo voluntariamente sem tentar esgotar o corpus de uma vez.
2. **Respeito a Cache Sem Duplicação:** Registros já avaliados com o mesmo `provider`, `model`, `prompt_version` e `input_hash` retornam `CACHED` instantaneamente e não consomem a cota de novas chamadas.
3. **Interrupção Limpa na Cota Diária:** Ao detectar `GenerateRequestsPerDay` ou `exceeded your current quota` (HTTP 429), o sistema dispara `DailyQuotaExhaustedError`, grava as predições válidas obtidas até então e encerra com código 0 exibindo:
   ```
   RATE_LIMIT_DAILY_REACHED
   Valid predictions: X/76
   Pending: Y
   Execute novamente após renovação da cota.
   ```
4. **Bloqueio de Avaliação Prematura:** A comparação formal contra o Ground Truth em `scripts/evaluate_llm_human.py` é bloqueada enquanto não houver 76/76 predições válidas sob exatamente o **mesmo modelo**, exibindo `BENCHMARK INCOMPLETE — X/76`.
5. **Progresso do Benchmark:** O comando `python scripts/run_llm_classification.py --progress` exibe o status de cobertura do corpus sem vazar nenhum dado de anotações humanas.

---

## 9. Benchmark B — Groq / GPT-OSS 120B

O Benchmark B é independente do Benchmark A (Gemini): usa o mesmo corpus, prompt e payload público permitido, mas arquivos de predição e de custo separados. A configuração é fixa: `groq`, `openai/gpt-oss-120b`, prompt `0.1.0`, temperatura `0.0` e `reasoning_effort=low`.

- Endpoint: `https://api.groq.com/openai/v1/chat/completions`.
- Credencial local: `GROQ_API_KEY`; nunca registrada em código, logs ou relatórios.
- Saída padrão: `reports/llm_predictions_groq_v0.1.0.jsonl`.
- Preço registrado para este experimento: US$ 0,15/1M tokens de entrada e US$ 0,60/1M tokens de saída, verificado em 2026-09-13 na [documentação oficial de modelos da Groq](https://console.groq.com/docs/models).
- A Groq informa `retry-after` em respostas 429 e headers `x-ratelimit-*` para requests e tokens; o cliente os preserva quando uma resposta válida os disponibiliza. Consulte a [documentação oficial de rate limits](https://console.groq.com/docs/rate-limits).
- A documentação oficial confirma suporte a `reasoning_effort=low` para GPT-OSS 120B; `include_reasoning=false` evita persistir raciocínio interno. Consulte a [documentação oficial de reasoning](https://console.groq.com/docs/reasoning).

O benchmark só deve iniciar após um teste de conectividade autenticado. Enquanto não houver 76 predições Groq válidas e homogêneas, avaliações contra anotações humanas permanecem bloqueadas.

---

## 10. Experimento OpenAI — GPT-5.6 Luna

O experimento OpenAI é independente dos benchmarks Gemini e Groq. A configuração é fixa: `provider=openai`, `model=gpt-5.6-luna`, prompt `0.1.0`, temperatura `0.0` e `reasoning_effort=none`. Usa `https://api.openai.com/v1/chat/completions`, endpoint oficialmente suportado pelo modelo, com Structured Outputs por JSON Schema estrito.

- Credencial exclusivamente local: `OPENAI_API_KEY`.
- Saídas segregadas: `reports/llm_predictions_openai_v0.1.0.jsonl` e `reports/llm_cost_openai_gate5.json`.
- Preço do experimento: US$ 0,20/1M tokens de entrada e US$ 1,20/1M tokens de saída, verificado em 2026-09-13 na [documentação oficial do GPT-5.6 Luna](https://developers.openai.com/api/docs/models/gpt-5.6-luna).
- O cache continua separado por `input_hash + provider + model + prompt_version`.
- Nenhuma avaliação contra anotações humanas é permitida antes de 76/76 resultados válidos e homogêneos.

---

## 11. Experimento OpenRouter

O experimento OpenRouter usa `https://openrouter.ai/api/v1/chat/completions` e a credencial local `OPENROUTER_API_KEY`. O modelo é fixo em `nvidia/nemotron-3-super-120b-a12b:free`, selecionado do catálogo atual por anunciar `structured_outputs` e contexto de 262.144 tokens; `openrouter/free` e fallback de modelo são proibidos.

As predições e custos são separados em `reports/llm_predictions_openrouter_v0.1.0.jsonl` e `reports/llm_cost_openrouter_gate5.json`. O variant `:free` tem custo efetivo zero no catálogo; limites e headers retornados pela API são preservados quando disponíveis. A seleção foi baseada na [documentação oficial de modelos](https://openrouter.ai/docs/guides/overview/models), [Structured Outputs](https://openrouter.ai/docs/guides/features/structured-outputs) e [variant :free](https://openrouter.ai/docs/guides/routing/model-variants/free).
