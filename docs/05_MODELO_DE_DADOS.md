# Modelo de dados

Nenhum banco de dados foi criado. Esta página distingue o modelo Silver implementado no Gate 2 das entidades de negócio futuras.

## Modelo Silver atual — PNCP (`schema_version: 0.1.0`)

Cada linha do arquivo `data/silver/pncp/*.jsonl` representa uma contratação validada.

| Campo Silver | Origem / regra | Tipo |
|---|---|---|
| `source` | constante criada pelo pipeline: `PNCP` | texto |
| `source_record_id` | `numeroControlePNCP`; obrigatório, texto com espaços externos removidos | texto |
| `source_url` | `linkSistemaOrigem`, quando presente | texto ou `null` |
| `source_file` | caminho relativo do Bronze selecionado | texto |
| `source_files` | caminhos relativos de todas as capturas deduplicadas do mesmo ID | lista de texto |
| `orgao_cnpj`, `orgao_nome` | `orgaoEntidade.cnpj`, `orgaoEntidade.razaoSocial` | texto ou `null` |
| `unidade_codigo`, `unidade_nome`, `municipio`, `uf` | campos correspondentes de `unidadeOrgao` | texto ou `null` |
| `objeto_compra` | `objetoCompra`, sem reescrita; apenas `strip()` externo | texto ou `null` |
| `modalidade_codigo`, `modalidade_nome` | `modalidadeId`, `modalidadeNome` | inteiro ou `null`; texto ou `null` |
| `numero_compra`, `ano_compra`, `processo` | `numeroCompra`, `anoCompra`, `processo` | texto/integer ou `null` |
| `data_publicacao`, `data_abertura_proposta`, `data_encerramento_proposta` | campos PNCP correspondentes; validados e serializados em ISO 8601 sem atribuir fuso inexistente | texto ISO ou `null` |
| `valor_total_estimado` | `valorTotalEstimado`, validado como número | número ou `null` |
| `situacao` | `situacaoCompraNome` | texto ou `null` |
| `captured_at` | `metadata.captured_at` do Bronze, UTC no coletor atual | texto ISO 8601 |
| `normalized_at` | timestamp UTC criado pelo normalizador | texto ISO 8601 |
| `schema_version` | constante do normalizador | texto |
| `source_field_states` | metadado do normalizador: registra `absent`, `null` ou `empty` para campos opcionais selecionados | objeto |

### Identidade, ausência e deduplicação

`numeroControlePNCP` foi observado preenchido e único nos 10 registros reais do Gate 1; ele é o identificador oficial escolhido para `source_record_id`. Não foi criada chave composta. A política distingue campo ausente, `null` e texto vazio no metadado `source_field_states`; o valor canônico correspondente é `null`, nunca zero, falso ou texto inventado.

Quando várias capturas têm o mesmo ID, o normalizador mantém a de `captured_at` mais recente, preserva todos os arquivos em `source_files` e registra warning se os campos canônicos divergirem. Registros inválidos são gravados em `data/silver/pncp/rejected/` com o motivo e a referência/origem.

### Campos PNCP observados e não mapeados neste schema mínimo

Os campos observados `srp`, `amparoLegal`, `dataInclusao`, `dataAtualizacao`, `dataAtualizacaoGlobal`, `modoDisputaId`, `modoDisputaNome`, `tipoInstrumentoConvocatorioCodigo`, `tipoInstrumentoConvocatorioNome`, `situacaoCompraId`, `sequencialCompra`, `valorTotalHomologado`, `informacaoComplementar`, `justificativaPresencial`, `unidadeSubRogada`, `orgaoSubRogado`, `emendaParlamentar`, `linkProcessoEletronico`, `fontesOrcamentarias` e `usuarioNome` foram preservados no Bronze, mas não foram incluídos no canônico mínimo por não serem necessários à finalidade Silver deste gate. Nenhuma informação desses campos foi inferida.

## Entidades de negócio futuras

## Modelo Gold atual — Opportunity Engine (`rules_version: 0.1.1`)

Cada linha de `data/gold/opportunities/*.jsonl` é derivada de uma linha Silver e contém: `opportunity_id`, `source`, `source_record_id`, `orgao_nome`, `orgao_cnpj`, `unidade_nome`, `municipio`, `uf`, `objeto_original`, `categories`, `matched_terms`, `negative_matches`, `relevance`, `temporal_status`, datas de publicação/abertura/encerramento, `valor_total_estimado`, `opportunity_score`, `confidence_score`, `score_breakdown`, `reason_codes`, `source_silver_file`, `source_bronze_files`, `rules_version` e `generated_at`.

`opportunity_id` é os 24 primeiros caracteres de SHA-256 de `source|source_record_id|rules_version`; por isso é determinístico para o mesmo registro e versão. Campos factuais vêm de Silver; `categories`, scores, motivos, status temporal, ID, versão e timestamps são derivados pelo motor e identificados como tal. O manifest Gold é separado dos registros.

### Contratos HTTP do Gate 4

Os schemas Pydantic em `src/api/schemas.py` são contratos de resposta HTTP, não uma segunda regra de negócio nem um novo modelo de persistência. Eles serializam e limitam a exposição do Gold para `GET /stats`, `GET /opportunities`, detalhe e evidências. O repositório da API lê Gold JSONL somente; não altera Bronze, Silver ou Gold. Caminhos retornados no lineage são relativos ao projeto, nunca caminhos absolutos da máquina.

### organizacao

`id`, `nome`, `cnpj`, `tipo`, `segmento`, `municipio`, `uf`, `fonte_origem`, `data_atualizacao`.

### oportunidade

`id`, `organizacao_id`, `objeto`, `categoria`, `descricao`, `data_publicacao`, `data_abertura`, `valor_estimado`, `status`, `url_fonte`, `fonte`, `capturado_em`.

### evidencia

`id`, `oportunidade_id`, `tipo`, `trecho`, `fonte`, `url`, `data`, `confianca`.

### score

`oportunidade_id`, `fit_segmento`, `fit_produto`, `sinal_compra`, `recencia`, `ticket`, `relacionamento`, `geografia`, `total`, `confidence`, `versao_regra`.

### status_comercial

`oportunidade_id`, `status`, `observacao`, `atualizado_em`.

## Modelos de Avaliação e Ground Truth (Gates 4.5 e 4.6)

### evaluation_corpus (reports/evaluation_corpus_v0.1.0.csv — Imutável)

| Campo | Tipo | Descrição |
|---|---|---|
| `review_id` | string (ex.: `REV-001`) | Identificador sequencial unívoco do caso de teste. |
| `source_record_id` | string | Identificador oficial no PNCP (`cnpj-modalidade-sequencial/ano`). |
| `objeto_original` | string | Objeto licitatório oficial do edital. |
| `orgao_nome` | string | Nome do órgão público licitante. |
| `unidade_nome` | string | Unidade gestora ou departamento requisitante. |
| `municipio` | string | Município do órgão licitante. |
| `uf` | string (2 char) | Unidade da Federação. |
| `valor_total_estimado` | float / vazio | Valor orçado do edital em reais. |
| `data_publicacao` | ISO 8601 string | Data/hora de publicação oficial. |
| `baseline_relevance` | string | Classificação predita pelo baseline determinístico. |
| `baseline_categories` | string | Lista de categorias casadas pelo baseline separadas por vírgula. |
| `baseline_score` | inteiro (0..100) | Opportunity score predito pelo baseline. |
| `baseline_confidence` | inteiro (0..100) | Confidence score predito pelo baseline. |
| `matched_terms` | string | Termos e categorias que geraram o match no baseline. |
| `negative_matches` | string | Termos negativos detectados pelo baseline. |

### human_annotations (reports/human_annotations_v0.1.0.csv — Gravável por William)

| Campo | Tipo / Valores | Descrição |
|---|---|---|
| `review_id` | string (ex.: `REV-001`) | Chave estrangeira ligando ao corpus imutável. |
| `source_record_id` | string | Chave de verificação de integridade referencial. |
| `human_relevant` | booleano (`TRUE` / `FALSE`) | Classificação de pertinência ao domínio por William. |
| `human_relevance` | enum (`ALTA`, `MEDIA`, `BAIXA`, `IRRELEVANTE`) | Grau de relevância atribuído por William. |
| `human_categories` | string (lista separada por vírgula) | Categorias de cozinha profissional confirmadas por William. |
| `human_confidence` | inteiro (`1` a `5`) | Grau de certeza da anotação de William. |
| `human_notes` | string (máx 1000 char) | Justificativa técnica do revisor. |
| `reviewed_at` | ISO 8601 string | Timestamp UTC de gravação da anotação humana. |

## Modelos de Classificação LLM (Gate 5)

### LLMStructuredOutput (Schema de Resposta do Modelo)

| Campo | Tipo / Valores | Descrição |
|---|---|---|
| `relevant` | booleano (`true` / `false`) | Pertencimento ao domínio de cozinha profissional/institucional. |
| `relevance` | enum (`ALTA`, `MEDIA`, `BAIXA`, `IRRELEVANTE`) | Grau de atratividade comercial do edital. |
| `categories` | lista de strings | Categorias presentes no edital (subconjunto das 9 canônicas). |
| `confidence` | inteiro (0..100) | Certeza da classificação atribuída pelo modelo. |
| `reason` | string (3..2000 char) | Justificativa técnica concisa da decisão do modelo. |

### LLMClassificationResult (reports/llm_predictions_v0.1.0.jsonl — Auditoria de Inferência)

| Campo | Tipo | Descrição |
|---|---|---|
| `review_id` | string (ex.: `REV-001`) | Identificador do caso no corpus imutável. |
| `source_record_id` | string | Identificador oficial do processo no PNCP. |
| `relevant` | booleano / nulo | Predição binária gerada pelo modelo. |
| `relevance` | string / nulo | Predição de relevância (`ALTA`, `MEDIA`, `BAIXA`, `IRRELEVANTE`). |
| `categories` | lista de strings | Categorias de domínio identificadas pelo modelo. |
| `confidence` | inteiro (0..100) / nulo | Grau de confiança reportado pelo modelo. |
| `reason` | string / nulo | Explicação textual da decisão. |
| `provider` | string | Provedor de LLM utilizado (`openai`). |
| `model` | string | Nome do modelo (`gpt-4o-mini`). |
| `prompt_version` | string | Versão do system prompt (`0.1.0`). |
| `input_hash` | string (SHA-256) | Hash canônico dos 7 campos públicos enviados. |
| `output_raw` | string / nulo | Resposta bruta em texto gerada pelo modelo. |
| `input_tokens` | inteiro | Quantidade de tokens de entrada cobrados. |
| `output_tokens` | inteiro | Quantidade de tokens de saída cobrados. |
| `total_tokens` | inteiro | Soma de tokens de entrada e saída. |
| `latency_ms` | float | Tempo de resposta da chamada em milissegundos. |
| `estimated_cost` | float | Custo monetário estimado em USD. |
| `status` | enum (`SUCCESS`, `ERROR`, `BLOCKED`, `CACHED`) | Estado de execução da inferência. |
| `error` | string / nulo | Mensagem de erro caso a chamada ou validação falhe. |
| `classified_at` | ISO 8601 string | Timestamp UTC do momento da classificação. |

### OperationalClassificationResult (Modelo de Inferência Operacional com Failover)

| Campo | Tipo | Descrição |
|---|---|---|
| `request_id` | string | Identificador único unívoco da requisição de inferência. |
| `provider_requested` | string | Provedor originalmente solicitado na cabeça da cascata. |
| `model_requested` | string | Modelo originalmente solicitado. |
| `provider_used` | string | Provedor que efetivamente produziu a resposta (`deterministic` se fallback final). |
| `model_used` | string | Modelo que efetivamente produziu a resposta (`rules_v0.1.1` se fallback final). |
| `fallback_used` | booleano | Indica se houve chaveamento em relação ao alvo primário. |
| `fallback_level` | inteiro (0..N) | Nível hierárquico do provedor acionado (0 = primário). |
| `fallback_reason` | string / nulo | Motivo canônico do failover do provedor anterior. |
| `providers_attempted` | lista de strings | Ordem dos provedores consultados durante a cascata. |
| `prompt_version` | string | Versão do system prompt (`0.1.0`). |
| `input_hash` | string (SHA-256) | Hash dos 7 campos públicos higienizados. |
| `relevant` | booleano / nulo | Predição binária de pertinência. |
| `relevance` | string / nulo | Grau de relevância comercial (`ALTA`, `MEDIA`, `BAIXA`, `IRRELEVANTE`). |
| `categories` | lista de strings | Categorias de domínio atribuídas. |
| `confidence` | inteiro (0..100) / nulo | Grau de confiança na predição. |
| `reason` | string / nulo | Justificativa técnica da decisão. |
| `input_tokens` | inteiro | Total de tokens de entrada consumidos pelo provedor utilizado. |
| `output_tokens` | inteiro | Total de tokens de saída gerados. |
| `total_tokens` | inteiro | Total de tokens computados. |
| `latency_ms` | float | Latência total da inferência em milissegundos. |
| `estimated_cost` | float | Custo monetário estimado em USD (0.0 se determinístico). |
| `started_at` | ISO 8601 string | Timestamp UTC de início do roteamento. |
| `finished_at` | ISO 8601 string | Timestamp UTC de término do processamento. |
| `attempt_traces` | lista de objetos | Trilha de auditoria detalhada de cada tentativa na cascata. |
| `status` | enum (`SUCCESS`, `ERROR`) | Status final do pipeline operacional. |
| `error` | string / nulo | Mensagem descritiva caso todos os provedores e fallbacks falhem. |

### AttemptTrace (Sub-schema de Rastreabilidade de Tentativas)

| Campo | Tipo | Descrição |
|---|---|---|
| `provider` | string | Nome do provedor testado nesta tentativa. |
| `model` | string | Nome do modelo invocado. |
| `attempt_number` | inteiro | Ordem sequencial da tentativa nesta requisição (1, 2, ...). |
| `started_at` | ISO 8601 string | Timestamp UTC de disparo da tentativa. |
| `finished_at` | ISO 8601 string | Timestamp UTC de encerramento da tentativa. |
| `http_status` | inteiro / nulo | Código de status HTTP retornado (ex.: 200, 429, 502, null). |
| `status` | string | Estado da tentativa (`SUCCESS`, `FAILED`, `SKIPPED`, `RATE_LIMITED`). |
| `error_type` | string / nulo | Categoria canônica do erro (`RATE_LIMITED`, `TIMEOUT`, `PROVIDER_5XX`, `CIRCUIT_OPEN`, etc.). |
| `latency_ms` | float | Tempo de resposta individual desta tentativa em ms. |
| `retry_count` | inteiro | Quantidade de retries executados no nível de transporte. |
| `error_message_sanitized` | string / nulo | Mensagem de erro higienizada com remoção estrita de credenciais. |

## Relações e governança futuras

Uma organização pode ter várias oportunidades; uma oportunidade pode ter várias evidências e um registro de score por versão de regra. O campo `cnpj` é opcional até haver fonte confiável. Ausência de valor, data ou CNPJ não deve ser convertida em valor negativo ou inferido. Novos campos exigem atualização deste documento.

