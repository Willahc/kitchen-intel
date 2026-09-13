# Governança e Metodologia do Development Set — Gate 5D

## 1. Por que o DEV SET existe

No aprendizado de máquina e no desenvolvimento de sistemas baseados em LLM, a contaminação do conjunto de teste (*data snooping* ou *test set leakage*) é uma das principais fontes de falha metodológica e degradação em produção.

Até o Gate 5, o projeto Kitchen Intel dispunha exclusivamente do **Test Set** (`reports/evaluation_corpus_v0.1.0.csv`, 76 registros), congelado com hash SHA-256 e anotado pelo revisor humano William (`reports/human_annotations_v0.1.0.csv`). Esse conjunto serviu como padrão-ouro para avaliar o baseline determinístico e o primeiro benchmark com LLM (`openai/gpt-oss-20b`).

Para que seja possível realizar:
- **Prompt Engineering e Tuning** (ex.: Prompt v0.2.0 para desambiguar alimentos in natura vs serviços de refeição);
- **Calibração de Thresholds de Score e Confiança**;
- **Desenho e Ajuste Fino de Guardrails Negativos** (regras determinísticas de veto);
- **Experimentação de Políticas Híbridas de Decisão** (Ensemble Baseline + LLM);

é **estritamente proibido** utilizar os 76 registros do Test Set para selecionar regras ou ajustar parâmetros. O **Development Set** (`development_corpus_v0.1.0.csv`) foi criado especificamente para prover um laboratório experimental governado, seguro e representativo.

---

## 2. Diferença Metodológica: DEV vs TEST

| Dimensão | Development Set (`dev-0.1.0`) | Test Set (`evaluation_corpus_v0.1.0`) |
|---|---|---|
| **Finalidade** | Experimentação, prompt tuning, calibração de regras e ensemble | Avaliação formal, imparcial e final de performance |
| **Volume** | **120 registros** reais do PNCP | **76 registros** reais do PNCP |
| **Namespace de ID** | `DEV-001` a `DEV-120` | `REV-001` a `REV-076` |
| **Janela Temporal** | **2026-09-11T08:30:19** a **2026-09-12T23:27:11** | **2026-09-08T04:00:06** a **2026-09-11T08:30:06** |
| **Overlap** | **ZERO absoluto** (`source_record_id` e texto) | **ZERO absoluto** com DEV |
| **Anotação Humana** | `reports/development_annotations_v0.1.0.csv` | `reports/human_annotations_v0.1.0.csv` |
| **Modo de Revisão** | **Blind Review Estrito** (sem predições ou scores) | Blind Review Inicial / Auditoria pós-benchmark |
| **Permissão de Ajuste** | **SIM** — Prompts e thresholds podem ser otimizados aqui | **NÃO** — Nenhum tuning pode olhar para estes dados |

---

## 3. Política Rígida de Não-Overlap e Deduplicação

Para assegurar independência estatística absoluta entre DEV e TEST:
1. **Deduplicação por `source_record_id`:** O conjunto de identificadores do DEV set possui interseção vazia com o Test Set:
   $$\text{DEV\_IDs} \cap \text{TEST\_IDs} = \emptyset \quad (\text{overlap} = 0)$$
2. **Deduplicação por Hash de Texto Normalizado:** Foi aplicado algoritmo de limpeza e remoção de acentos/pontuações no objeto da contratação para garantir que nenhum edital do DEV seja duplicata textual de edital do TEST. Quatro registros brutos que apresentavam colisão textual exata com o Test Set foram sumariamente descartados.
3. **Deduplicação Interna:** Todos os 120 registros do DEV possuem `source_record_id` distintos e hashes textuais distintos entre si.

---

## 4. Estratégia de Amostragem Estratificada

Amostras aleatórias puras do PNCP são dominadas em 98% por compras hospitalares, medicamentos, pavimentação ou serviços de TI. Para tornar o DEV SET um ambiente de aprendizado eficaz, aplicou-se amostragem balanceada em 5 classes fundamentais:

| Bucket de Amostragem | Quantidade | Percentual | Descrição e Propósito Metodológico |
|---|:---:|:---:|---|
| **POTENTIAL_RELEVANT** | **30** | 25.0% | Sinais explícitos de cozinha industrial, cocção, refrigeração comercial, balcões térmicos, lavagem pesada, alimentação escolar ou refeições prontas. |
| **HARD_NEGATIVES** | **30** | 25.0% | Casos de alta confusão léxica: compras isoladas de carnes, hortifrúti e gêneros sem serviço; utensílios domésticos; produtos de limpeza/copa; mobiliário escolar comum. |
| **NEGATIVE_CONTEXT** | **20** | 16.7% | Termos com regras negativas explícitas no motor ou no prompt: climatização/ar-condicionado predial, odontologia, necrotérios, postos de saúde, botijões de GLP avulsos, combustíveis. |
| **AMBIGUOUS / BORDERLINE** | **20** | 16.7% | Casos limítrofes que demandam julgamento humano: manutenção predial mista, itens em aço inoxidável em contextos neutros, reformas civis gerais. |
| **OBVIOUS_NEGATIVES** | **20** | 16.7% | Negativos fáceis e representativos da distribuição geral do setor público: material de escritório, softwares, TI, veículos, extintores de incêndio. |
| **Total DEV SET** | **120** | **100.0%** | Amostra estratificada balanceada para experimentação |

---

## 5. Protocolo de Blind Review (Revisão às Cegas)

Para anular o **viés de ancoragem** (*anchoring bias*), William revisará o DEV SET sem qualquer pista gerada por modelos ou regras:

1. **Endpoints Dedicados:**
   - `GET /review/dev`: Lista de resumo e progresso dos 120 itens DEV.
   - `GET /review/dev/export`: Exportação do CSV de anotações do DEV.
   - `GET /review/dev/{review_id}`: Detalhe do edital em **Modo Blind Estrito**.
   - `PUT /review/dev/{review_id}`: Persistência exclusiva em `reports/development_annotations_v0.1.0.csv`.
2. **Máscara Total de Predições:**
   - No endpoint `/review/dev/{review_id}`, o atributo `baseline` é serializado como `null`.
   - Nenhuma categoria sugerida, score determinístico, termo casado (`matched_terms`), código de exclusão (`negative_matches`) ou predição de LLM é enviada para o cliente de revisão.
   - O revisor visualiza apenas os 7 campos oficiais públicos do PNCP (`objeto_original`, `orgao_nome`, `unidade_nome`, `municipio`, `uf`, `valor_total_estimado`, `data_publicacao`) e os campos de preenchimento humano.

---

## 6. Versionamento e Congelamento (Freeze)

O Development Set está formalmente congelado sob a versão:
$$\text{corpus\_version} = \text{dev-0.1.0}$$

Metadados persistidos em `reports/development_corpus_v0.1.0.manifest.json`:
- **Arquivo CSV:** `reports/development_corpus_v0.1.0.csv`
- **Total de Registros:** 120
- **SHA-256:** `c2da2b5e6e1206252f75640d1085d55fd8839a923625eb92dd5a5215ad3240a1`
- **Janela de Publicação:** `2026-09-11T08:30:19` a `2026-09-12T23:27:11`
- **Arquivo de Anotações:** `reports/development_annotations_v0.1.0.csv` (120 linhas preparadas, campos humanos vazios)

---

## 7. Regras Estritas Contra Vazamento (Zero Leakage)

1. **Test Set Intocado:** Nenhuma alteração foi ou será feita em `reports/evaluation_corpus_v0.1.0.csv` ou `reports/human_annotations_v0.1.0.csv`.
2. **Isolamento de Tuning:** Toda futura iteração de prompt (ex.: Prompt v0.2.0), novas regras determinísticas ou calibração de hiperparâmetros de ensemble será avaliada contra o DEV SET anotado por William.
3. **Avaliação Final no Test Set:** Uma política ou modelo candidato só será submetido ao Test Set de 76 registros após validação conclusiva no DEV SET. O Test Set continuará sendo executado uma única vez por hipótese madura, reportando as métricas definitivas sem retroalimentação.

---

## 8. Validação Semântica da Curadoria e Interface Blind (Gate 5D.1)

Para prevenir erros de inconsistência lógica durante a anotação manual por William:

1. **Validação Semântica Estrita (Cross-Field):**
   - Se `human_relevant == FALSE`: `human_relevance` deve ser obrigatoriamente `IRRELEVANTE` e `human_categories` deve ser uma lista vazia (`[]`).
   - Se `human_relevant == TRUE`: `human_relevance` deve ser obrigatoriamente `ALTA`, `MEDIA` ou `BAIXA` (nunca `IRRELEVANTE`).
   - `human_categories` aceita exclusivamente o subconjunto das 9 categorias canônicas (`COZINHA`, `REFEITORIO`, `INOX`, `COCCAO`, `REFRIGERACAO`, `EXAUSTAO`, `LAVAGEM`, `INFRAESTRUTURA`, `ALIMENTACAO_COLETIVA`).
   - Violações são rejeitadas com status HTTP 422 (*Unprocessable Entity*) e mensagem explicativa em português.
2. **Interface de Revisão Neutra (Blind UI):**
   - William alterna entre *Development Set* (120 registros) e *Test Set* (76 registros) com um clique na interface.
   - No modo DEV, predições determinísticas e de IA estão totalmente desabilitadas e nenhum botão de revelar predição existe.
   - Estatísticas parciais de distribuição de rótulos por classe são omitidas durante o processo para prevenir viés de indução/balanceamento artificial.
   - Navegação facilitada com "Anterior", "Próximo", "Ir para próximo pendente", atalho para avançar automaticamente e indicador de progresso $X / 120$.
   - Toda anotação persiste imediatamente em `reports/development_annotations_v0.1.0.csv`.

