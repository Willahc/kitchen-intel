# Guia de Revisão Humana e Ground Truth — Gate 4.6

Este documento é o manual oficial de curadoria para **William** (e revisores especialistas de negócio) para a anotação manual de Ground Truth (padrão-ouro) no projeto **KITCHEN INTEL**.

---

## 1. Objetivo e Governança do Ground Truth

A anotação humana estabelece o **padrão-ouro independente** contra o qual todas as inteligências do projeto serão medidas:
- Baseline determinístico de regras (Gate 3/4);
- Modelos LLM e extração estruturada (Gates futuros);
- Abordagens híbridas e calibração de scores.

### Arquitetura de Separação de Dados
Para garantir integridade científica e evitar corrupção acidental:
1. **Corpus de Avaliação (`reports/evaluation_corpus_v0.1.0.csv`):**
   - Contém os 76 registros reais do PNCP selecionados (estratificados por casos nucleares, ambíguos, negativos difíceis e controles).
   - É **estritamente IMUTÁVEL** (hash SHA-256 congelado: `6a2961b6e1849616d163775287f24703afc3d435a871dc9569d38eecf12918f8`).
2. **Anotações Humanas (`reports/human_annotations_v0.1.0.csv`):**
   - Armazena exclusivamente as anotações geradas por William.
   - Vinculado ao corpus através das chaves `(review_id, source_record_id)`.
   - Pode ser atualizado pela interface web (`PUT /review/{review_id}`) ou via exportação/importação de CSV.

---

## 2. A Pergunta Fundamental de Avaliação

Ao analisar o objeto e os dados da contratação, **NÃO** pergunte:
> *"A minha empresa ganharia esta licitação?"* ou *"Eu tenho estoque deste produto hoje?"*

A pergunta canônica obrigatória é:
> **"Este objeto representa uma compra, obra, manutenção ou demanda comercial que pertence legitimamente ao ecossistema de cozinha profissional, institucional, refeitório ou alimentação coletiva?"**

- Se a resposta for **SIM**, marque `human_relevant = TRUE`.
- Se a resposta for **NÃO**, marque `human_relevant = FALSE`.

---

## 3. Protocolo Blind Review (Eliminação do Viés de Ancoragem)

Para garantir uma anotação imparcial:
- **Viés de Ancoragem (Anchoring Bias):** Quando um revisor vê previamente a nota (score) ou a classificação sugerida pelo sistema, sua tendência psicológica é concordar com a máquina, inflando artificialmente as métricas de concordância.
- **Blind Review (Revisão Cega):** Na interface web, o **Modo Blind Review** vem ativado por padrão. Ele oculta a nota de oportunidade, termos casados e a relevância estimada pelo baseline enquanto o registro não tiver sido avaliado por William.
- Caso o revisor deseje checar a predição da máquina após formar sua opinião, ele pode desativar a blind review ou clicar em "Revelar predição do sistema".

---

## 4. Campos de Anotação Humana

As anotações contêm 5 variáveis essenciais:

| Campo | Tipo / Valores | Descrição e Critério |
|---|---|---|
| `human_relevant` | Booleano (`TRUE` / `FALSE`) | Classificação binária primária de pertinência ao domínio. |
| `human_relevance` | Enum: `ALTA`, `MEDIA`, `BAIXA`, `IRRELEVANTE` | Grau de relevância da oportunidade (ver seção 5). |
| `human_categories` | Multilabel: lista com até 9 categorias | Categorias do setor de cozinha presentes no edital (ver seção 6). |
| `human_confidence` | Inteiro: `1` a `5` | Grau de certeza da interpretação humana (`1` = dúbio/vago; `5` = certeza absoluta). |
| `human_notes` | Texto livre (máx 1000 caracteres) | Justificativa ou observações do revisor, útil para desambiguações e falsos positivos. |

---

## 5. Critérios para `human_relevance`

- **ALTA:** Contratações nucleares para cozinhas profissionais e refeitórios institucionais:
  - Compra de fornos combinados, caldeirões industriais, coifas e sistemas pesados de exaustão;
  - Construção, reforma completa ou adequação predial de cozinhas e refeitórios;
  - Câmaras frigoríficas industriais de grande porte para armazenamento alimentar.
- **MEDIA:** Maquinário ou mobiliário específico de suporte:
  - Bancadas, mesas lisas, cubas e estantes em aço inoxidável para manipulação de alimentos;
  - Refrigeradores comerciais verticais e freezers industriais;
  - Máquinas lava-louças comerciais, fatiadores de frios e descascadores de legumes industriais;
  - Manutenção preventiva e corretiva de equipamentos de cocção/refrigeração alimentar.
- **BAIXA:** Sinais indiretos de demanda ou editais de alimentação:
  - Terceirização de alimentação coletiva ou fornecimento de merenda escolar (não compra maquinário no edital, mas sinaliza cozinha ativa e demanda operacional);
  - Aquisição de pequenos utensílios e insumos de apoio sem compra de maquinário pesado.
- **IRRELEVANTE:** Contratações sem relação com cozinha profissional, alimentação institucional ou refeitório:
  - Itens administrativos, mobília escolar de madeira, obras gerais sem menção a alimentação, TI, peças de trator, material de escritório, etc.

---

## 6. Lista Canônica de Categorias (`human_categories`)

Selecione todas as categorias aplicáveis (multilabel):
- `COZINHA`: ambientes e equipamentos gerais de cozinha institucional/industrial;
- `REFEITORIO`: mobiliário e infraestrutura de salão de refeições/restaurante coletivo;
- `INOX`: mobiliário em aço inox (bancadas, mesas, cubas, pias, estantes);
- `COCCAO`: fornos industriais, combinados, fogões, fritadeiras, chapas, caldeirões;
- `REFRIGERACAO`: freezers industriais, refrigeradores comerciais, câmaras frias;
- `EXAUSTAO`: coifas, exaustores, dutos de exaustão, lavadores de gases;
- `LAVAGEM`: lava-louças industriais de capô, esteira ou gaveta;
- `INFRAESTRUTURA`: obras civis, adequações elétricas/hidráulicas em cozinhas;
- `ALIMENTACAO_COLETIVA`: serviços de alimentação, nutrição e merenda institucional.

---

## 7. Como Utilizar a Interface de Revisão (Web UI)

1. Inicie a API e a interface web (`npm run dev` na pasta `frontend`).
2. Acesse `http://localhost:5173` e clique na aba **"Revisão Humana & Ground Truth (Corpus v0.1.0)"**.
3. O painel superior apresentará o progresso: `0/76 (0.0%)` registros revisados.
4. Para cada registro:
   - Leia o **Objeto Oficial** e os metadados do órgão/unidade;
   - Preencha os campos `human_relevant`, `human_relevance`, `human_categories`, `human_confidence` e `human_notes`;
   - Clique em **"Salvar Avaliação de William"** (com "Avançar para o próximo pendente" marcado).
5. Seus dados serão gravados imediatamente via endpoint `PUT /review/{review_id}` em `reports/human_annotations_v0.1.0.csv`.
6. Ao final, você pode clicar em **"Exportar Anotações (CSV)"** para baixar a planilha completa assinada.

---

## 8. Execução do Script de Avaliação

O script formal de avaliação `scripts/evaluate_baseline_human.py` exige 100% de cobertura das anotações humanas:
```bash
# Execução padrão (bloqueia se houver pendências):
python scripts/evaluate_baseline_human.py

# Inspeção intermediária/preliminar durante o processo de revisão:
python scripts/evaluate_baseline_human.py --allow-partial
```

O script reportará métricas oficiais:
- Matriz de confusão (TP, FP, TN, FN);
- Acurácia, Precisão, Recall e F1-score binários;
- Acurácia de concordância de relevância ordinal/multiclasse;
- Métricas multicategoria multilabel (Exact match, Precision, Recall, F1).
