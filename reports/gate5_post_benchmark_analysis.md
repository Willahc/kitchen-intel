# Análise Técnica Pós-Benchmark — Gate 5: Classificação LLM vs Baseline

**Projeto:** KITCHEN INTEL — Agentic Opportunity Intelligence  
**Gate:** GATE 5 (Classificação com LLM e Avaliação Comparativa)  
**Data da Análise:** 2026-09-13  
**Status do Corpus:** TEST SET IMUTÁVEL CONGELADO (`evaluation_corpus_v0.1.0.csv`, 76 registros)  
**Status da Anotação:** GROUND TRUTH CONGELADO (`human_annotations_v0.1.0.csv`, revisor William)  

---

## 1. Resumo Executivo dos Resultados

Nesta sessão, concluiu-se o primeiro benchmark completo (76/76 registros) de um Modelo de Linguagem no projeto Kitchen Intel, utilizando o provedor **NVIDIA API Catalog** (`openai/gpt-oss-20b`, temperature 0.0, prompt 0.1.0) sob rigoroso isolamento e zero data leakage.

### Comparativo Consolidado

| Métrica | Baseline Determinístico (`rules_v0.1.1`) | NVIDIA NIM (`openai/gpt-oss-20b`) | Delta (pp) |
|---|:---:|:---:|:---:|
| **True Positives (TP)** | 9 | **11** | +2 |
| **False Positives (FP)** | 15 | **12** | -3 |
| **True Negatives (TN)** | 50 | **53** | +3 |
| **False Negatives (FN)** | 2 | **0** | **-2 (100% Recall)** |
| **Acurácia Binária** | 77.63% | **84.21%** | +6.58 pp |
| **Precisão Binária** | 37.50% | **47.83%** | +10.33 pp |
| **Recall Binário** | 81.82% | **100.00%** | +18.18 pp |
| **F1-Score** | 51.43% | **64.71%** | +13.28 pp |
| **Relevance Accuracy** | 73.68% | **71.05%** | -2.63 pp |
| **Category Micro F1** | 76.19% | **91.67%** | +15.48 pp |
| **Category Exact Match** | 72.73% | **81.82%** | +9.09 pp |

---

## 2. Caracterização Técnica dos 12 Falsos Positivos da NVIDIA

O modelo NVIDIA identificou 12 editais como relevantes (`relevant=True`) que o revisor William classificou como irrelevantes (`human_relevant=False`). A análise caso a caso revela padrões semânticos e contextuais claros:

| Review ID | Objeto Resumido | Predição NVIDIA | Baseline | Ground Truth | Taxonomia do Erro |
|---|---|---|---|---|---|
| **REV-001** | Manutenção em máquinas e equipamentos de cozinha industrial (Comando de Operações Especiais) | `ALTA` (COZINHA, COCCAO, conf 95) | `ALTA` (score 90) | `IRRELEVANTE` | `GENERIC_MAINTENANCE` |
| **REV-003** | Manutenção de roçadeiras, máquinas de costura, fogão industrial, freezer, etc. (Mun. Sarandi) | `MEDIA` (COCCAO, REFRIGERACAO, conf 80) | `ALTA` (score 85) | `IRRELEVANTE` | `GENERIC_MAINTENANCE` |
| **REV-005** | Manutenção corretiva de marquise e cobertura do refeitório (Centro Tecnológico da Marinha) | `ALTA` (INFRAESTRUTURA, conf 90) | `ALTA` (score 85) | `IRRELEVANTE` | `INFRASTRUCTURE_AMBIGUITY` |
| **REV-006** | Reforma de mesas/cadeiras escolares e bancos de refeitório | `MEDIA` (REFEITORIO, conf 85) | `ALTA` (score 80) | `IRRELEVANTE` | `EQUIPMENT_AMBIGUITY` |
| **REV-008** | Materiais de consumo, limpeza e utensílios para serviço de copeiragem (MEC) | `BAIXA` (ALIMENTACAO_COLETIVA, COZINHA, conf 80) | `MEDIA` (score 77) | `IRRELEVANTE` | `FOOD_SERVICE_ADJACENCY` |
| **REV-009** | Aquisição de gêneros alimentícios (carnes, pães) para refeitório (IF Teixeira de Freitas) | `BAIXA` (ALIMENTACAO_COLETIVA, conf 95) | `MEDIA` (score 77) | `IRRELEVANTE` | `FOOD_SERVICE_ADJACENCY` |
| **REV-017** | Registro de preços para mesas e bancos de refeitório escolar | `ALTA` (REFEITORIO, conf 95) | `MEDIA` (score 67) | `IRRELEVANTE` | `EQUIPMENT_AMBIGUITY` |
| **REV-022** | Conjunto de mesas e bancos para refeitório escolar (Rede Municipal) | `ALTA` (REFEITORIO, conf 95) | `MEDIA` (score 64) | `IRRELEVANTE` | `EQUIPMENT_AMBIGUITY` |
| **REV-023** | Gêneros alimentícios, carnes e frios para merenda escolar | `BAIXA` (ALIMENTACAO_COLETIVA, conf 95) | `BAIXA` (score 63) | `IRRELEVANTE` | `FOOD_SERVICE_ADJACENCY` |
| **REV-024** | Fornecimento de gêneros alimentícios (Merenda Escolar) | `BAIXA` (ALIMENTACAO_COLETIVA, conf 90) | `BAIXA` (score 63) | `IRRELEVANTE` | `FOOD_SERVICE_ADJACENCY` |
| **REV-041** | Termômetros digitais culinários e para freezer/geladeira | `MEDIA` (REFRIGERACAO, conf 90) | `IRRELEVANTE` (score 0) | `IRRELEVANTE` | `CATEGORY_OVERMATCH` |
| **REV-053** | Utensílios domésticos para padaria social e banco de alimentos | `MEDIA` (COZINHA, conf 80) | `IRRELEVANTE` (score 0) | `IRRELEVANTE` | `DOMAIN_OVERREACH` |

### Detalhamento por Causa Provável (Taxonomia)

1. **FOOD_SERVICE_ADJACENCY (4 casos — 33.3%):**
   - Casos: REV-008, REV-009, REV-023, REV-024.
   - Diagnóstico: O prompt v0.1.0 orientava que merenda escolar e alimentação coletiva fossem tratadas como relevância `BAIXA` (sinal indireto de operação de cozinha). O modelo seguiu a diretriz e marcou `relevant=True` com relevância `BAIXA`. Contudo, William considerou compras de alimentos puros (carnes, hortifrúti) fora do escopo de engenharia/equipamentos.

2. **EQUIPMENT_AMBIGUITY (4 casos — 33.3%):**
   - Casos: REV-006, REV-017, REV-022, REV-041.
   - Diagnóstico: O modelo interpretou mobiliário escolar de refeitório (mesas e bancos) e termômetros digitais culinários como pertinentes à categoria `REFEITORIO` / `REFRIGERACAO`. William considera mobiliário escolar de madeira/fórmica fora do escopo de cozinha industrial pesada/inox.

3. **GENERIC_MAINTENANCE (2 casos — 16.7%):**
   - Casos: REV-001, REV-003.
   - Diagnóstico: Em REV-001, a manutenção pura de máquinas em quartel militar foi descartada por William por se tratar de serviço de manutenção sem fornecimento de bens ou fora da praça comercial. Em REV-003, o contrato de manutenção misturava máquinas de costura e roçadeiras com fogão/freezer.

4. **INFRASTRUCTURE_AMBIGUITY (1 caso — 8.3%):**
   - Caso: REV-005.
   - Diagnóstico: Reforma de telhado/marquise de refeitório foi interpretada como obra civil de refeitório (`INFRAESTRUTURA`), mas na prática era engenharia predial genérica.

5. **DOMAIN_OVERREACH (1 caso — 8.3%):**
   - Caso: REV-053.
   - Diagnóstico: "Utensílios domésticos" para padaria social. O modelo ancorou na expressão "padaria social e banco de alimentos", extrapolando para cozinha profissional.

---

## 3. Caracterização dos 2 Falsos Negativos do Baseline

O baseline determinístico perdeu 2 oportunidades que William validou como relevantes. O modelo NVIDIA identificou ambos com sucesso (eliminando completamente os FNs):

### Caso REV-033
- **Objeto Oficial:** `CONTRATAÇÃO DE EMPRESA ESPECIALIZADA PARA FORNECIMENTO PARCELADO DE GÊNEROS ALIMENTÍCIOS, COM ENTREGA PONTO A PONTO NAS UNIDADES ESCOLARES DA REDE MUNICIPAL DE ENSINO, DESTINADOS À EXECUÇÃO DA ALIMENTAÇÃO ESCOLAR DOS ALUNOS ATENDIDOS PELA SECRETARIA MUNICIPAL DE EDUCAÇÃO DO MUNICÍPIO DE SANTA GERTRUDES/SP...`
- **Ground Truth (William):** `relevant=True`, `relevance=MEDIA`, `categories=['ALIMENTACAO_COLETIVA']`.
- **Baseline Determinístico:** `relevant=False`, `relevance=IRRELEVANTE`, `score=0`.
- **NVIDIA:** `relevant=True`, `relevance=BAIXA`, `categories=['ALIMENTACAO_COLETIVA']`, `confidence=90`.
- **Causa da Perda pelo Baseline:** **`VOCABULARY_GAP`**. As regras determinísticas buscavam os termos "merenda escolar" e "cozinha", mas o edital utilizou a expressão formal "alimentação escolar" conjugada com "entrega ponto a ponto". O dicionário estático de regras 0.1.1 não possuía sinônimo mapeado para esta variação léxica. O LLM reconheceu o sentido semântico imediatamente.

### Caso REV-044
- **Objeto Oficial:** `REGISTRO DE PREÇOS PARA CONTRATAÇÃO DE EMPRESA PARA FORNECIMENTO EVENTUAL DE KITS LANCHE, DESTINADOS AO ATENDIMENTO DAS DEMANDAS DAS SECRETARIAS MUNICIPAIS DE CULTURA, SAÚDE, ESPORTE E DESENVOLVIMENTO ECONÔMICO E SOCIAL DO MUNICÍPIO DE MONTE MOR/SP...`
- **Ground Truth (William):** `relevant=True`, `relevance=MEDIA`, `categories=['ALIMENTACAO_COLETIVA']`.
- **Baseline Determinístico:** `relevant=False`, `relevance=IRRELEVANTE`, `score=0`.
- **NVIDIA:** `relevant=True`, `relevance=BAIXA`, `categories=['ALIMENTACAO_COLETIVA']`, `confidence=90`.
- **Causa da Perda pelo Baseline:** **`INDIRECT_SIGNAL` / `VOCABULARY_GAP`**. A expressão "kits lanche" representa fornecimento pronto de alimentação coletiva institucional, ausente do vocabulário estático das regras 0.1.1. O LLM compreendeu o serviço de alimentação coletiva subjacente.

---

## 4. Matriz de Concordância e Complementaridade (76 Casos)

### 4.1 Tabela Global de Concordância

| Categoria de Decisão | Quantidade | Percentual | Detalhe |
|---|:---:|:---:|---|
| **Ambos Acertaram (Both Correct)** | **57** | 75.00% | 48 TNs e 9 TPs comuns |
| **Apenas Baseline Acertou (Baseline Only)** | **2** | 2.63% | REV-041 e REV-053 (NVIDIA gerou FP) |
| **Apenas NVIDIA Acertou (NVIDIA Only)** | **7** | 9.21% | 2 FNs corrigidos (REV-033, REV-044) + 5 FPs corrigidos (REV-002, REV-004, REV-007, REV-019, REV-020) |
| **Ambos Erraram (Both Wrong)** | **10** | 13.16% | FPs compartilhados (REV-001, REV-003, REV-005, REV-006, REV-008, REV-009, REV-017, REV-022, REV-023, REV-024) |
| **Total Avaliado** | **76** | 100.0% | Corpus de avaliação integral |

### 4.2 Concordância Segmentada por Relevância do Ground Truth

- **ALTA (1 caso):** Ambos acertaram (100%).
- **MEDIA (8 casos):** Ambos acertaram em 6; NVIDIA acertou exclusivamente em 2 (REV-033, REV-044); Baseline acertou em 0 exclusivos.
- **BAIXA (2 casos):** Ambos acertaram (100%).
- **IRRELEVANTE (65 casos):** Ambos acertaram em 48; Baseline acertou exclusivamente em 2; NVIDIA acertou exclusivamente em 5; Ambos erraram em 10.

### 4.3 Concordância Segmentada por Categoria do Ground Truth

- **COZINHA (9 casos):** Ambos acertaram todos os 9 casos (100% de convergência em editais centrais de cozinha).
- **ALIMENTACAO_COLETIVA (3 casos):** Ambos acertaram 1; NVIDIA acertou exclusivamente 2 (REV-033 e REV-044).
- **SEM CATEGORIA / IRRELEVANTE (65 casos):** 48 acertos mútuos, 10 erros mútuos, 5 acertos exclusivos NVIDIA, 2 acertos exclusivos Baseline.

### 4.4 Balanço de Complementaridade

- **Erros do baseline corrigidos pelo LLM:** **7 casos** (taxa de recuperação de 41.2% dos erros do baseline).
- **Acertos do baseline degradados pelo LLM:** **2 casos** (degradação residual de apenas 3.4% dos acertos do baseline).
- **Ganho Líquido:** **+5 acertos adicionais**, elevando a acurácia de 77.63% para 84.21% e o Recall para 100%.

---

## 5. Hipóteses para Arquitetura Híbrida (Conceitual — Sem Implementação)

A complementaridade observada fundamenta o desenho de arquiteturas híbridas determinístico-cognitivas:

### Estratégia A: Baseline como Pré-Filtro de Alto Recall → LLM como Verificador Semântico
- **Fluxo:** O baseline determinístico avalia 100% dos editais. Apenas editais com `baseline_relevance in (ALTA, MEDIA, BAIXA)` são submetidos ao LLM.
- **Vantagens:** Redução de ~70% das chamadas e dos custos com LLM; latência agregada muito baixa.
- **Desvantagens Críticas:** **Estrangulamento de Recall.** Como o baseline teve 2 FNs (REV-033 e REV-044), esses casos nunca chegariam ao LLM, fixando o teto de recall em 81.82%.
- **Risco de FP:** Baixo.
- **Risco de FN:** Alto.
- **Explicabilidade:** Mista.

### Estratégia B: LLM como Classificador Primário → Guardrails Determinísticos Negativos
- **Fluxo:** O LLM avalia os editais. Uma camada de regras determinísticas pós-processamento aplica regras negativas de veto para contextos sabidamente inválidos (ex.: vetar compra isolada de carnes/hortifrúti sem prestação de serviço, vetar mobiliário escolar padronizado, vetar termômetros avulsos).
- **Vantagens:** Preserva o Recall de 100% do LLM e elimina cirurgicamente a maioria dos 12 FPs observados (eliminando potencialmente até 8 dos 12 FPs).
- **Desvantagens:** Custo e tempo de inferência sobre 100% dos dados.
- **Risco de FP:** Muito baixo.
- **Risco de FN:** Baixo (desde que as regras negativas sejam ultra-específicas).
- **Explicabilidade:** Altíssima (justificativa do LLM + regra determinística de exclusão).

### Estratégia C: Política de Decisão / Ensemble Ponderado
- **Fluxo:** Ambas as camadas operam. Uma tabela de decisão explícita cruza `baseline_score`, `baseline_categories`, `llm_relevance` e `llm_confidence`:
  - Concordância positiva forte (`score >= 80` e `LLM ALTA/MEDIA`): Aprovação imediata (Audit Gold).
  - Concordância negativa forte (`score == 0` e `LLM IRRELEVANTE`): Descarte imediato.
  - Divergência:
    - Se `LLM == BAIXA` e `baseline == ALIMENTACAO_COLETIVA` sem equipamento: aplicar regra de negócio comercial.
    - Se `LLM == IRRELEVANTE` e `baseline > 80` (ex.: climatização/exaustão genérica): prevalece o filtro de desambiguação do LLM (conforme comprovado em REV-002 e REV-004).
- **Vantagens:** Máxima robustez analítica, adaptabilidade e auditoria granular.
- **Desvantagens:** Maior complexidade de calibração e governança.
- **Risco de FP:** Baixo a Moderado.
- **Risco de FN:** Próximo de zero.
- **Explicabilidade:** Excelente.

---

## 6. Governança Metodológica: Preservação do Test Set e Proposta de DEV SET

### 6.1 Integridade Estrita do Test Set
- O corpus atual de 76 registros (`reports/evaluation_corpus_v0.1.0.csv`) e as anotações (`reports/human_annotations_v0.1.0.csv`) constituem o **TEST SET CANÔNICO** do projeto Kitchen Intel.
- **Nenhuma regra determinística (`rules_v0.1.1`) e nenhum prompt (`classifier_v0.1.0.txt`) foi ou será alterado com base direta nestes 76 registros**, prevenindo contaminação estatística (data snooping / data leakage) e sobreajuste (overfitting).

### 6.2 Proposta de Construção do DEV SET (`development_corpus_v0.1.0`)
Para realizar futuro ajuste fino de prompts (ex.: Prompt v0.2.0 com explicitação de "gêneros alimentícios in natura vs serviço de refeição"), calibração de thresholds e regras de veto, propõe-se o seguinte protocolo:
1. **Nova Coleta:** Extrair uma nova janela temporal do PNCP (ex.: registros subsequentes de 2026-09-12 a 2026-09-15) com volume aproximado de 100 a 150 novos editais.
2. **Estratificação Controlada:** Garantir amostragem que inclua casos limítrofes conhecidos (merenda, mobiliário escolar, manutenção civil predial, equipamentos pesados de cocção/refrigeração).
3. **Revisão Humana Isolada:** Aplicar o mesmo protocolo de Blind Review com William para geração de `human_annotations_dev_v0.1.0.csv`.
4. **Finalidade Exclusiva:** Utilizar o DEV SET para iterar prompts, testar thresholds de score e validar regras de guardrail antes de qualquer nova submissão ao Test Set.
5. **Critério:** Nenhuma coleta ou implementação será realizada no presente momento.

---

## 7. Conclusão da Análise Técnica

O benchmark do Gate 5 comprovou empiricamente que o LLM (`openai/gpt-oss-20b`) supera o baseline determinístico em precisão (+10.33 pp), acurácia (+6.58 pp), F1 (+13.28 pp) e atinge **100% de recall** no test set, corrigindo inclusive lacunas léxicas do dicionário de regras. 

A análise técnica pós-benchmark está concluída, os dados estão documentados e os artefatos permanecem estritamente congelados. O projeto permanece no Gate 5 sem avançar para o Gate 6.
