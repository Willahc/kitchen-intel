# Plano de Amostragem Direcionada e Corpus de Avaliação — Gate 4.5

## 1. Objetivo

Construir um conjunto de dados **real**, rastreável e auditável, proveniente da API pública oficial do PNCP, com o propósito de viabilizar a futura avaliação comparativa entre:
1. O baseline determinístico (`rules_version 0.1.1`);
2. Modelos de linguagem (LLM) no Gate 5;
3. Abordagens híbridas (regras + IA) nos gates subsequentes.

O Gate 4 encerrou com uma amostra legítima de 20 registros reais, porém com 0 oportunidades relevantes para o domínio de cozinhas industriais e institucionais. Para que uma avaliação de IA seja cientificamente sólida e metodologicamente válida, é necessário dispor de um corpus de avaliação contendo uma diversidade representativa de fenômenos classificatórios reais.

---

## 2. Princípios e Regras Inegociáveis

- **Dados 100% Reais:** nenhuma oportunidade, órgão, objeto ou contratação pode ser fabricada ou simulada. Todos os registros provêm da API oficial do PNCP.
- **Bronze Imutável e Não Filtrado:** como o endpoint oficial do PNCP não oferece busca textual na rota de contratações, não é permitido filtrar dados antes do armazenamento em Bronze. Todo payload oficial recebido é integralmente persistido.
- **Linhagem Completa:** todo registro segue o fluxo estrito:
  $$\text{PNCP} \longrightarrow \text{Bronze} \longrightarrow \text{Silver} \longrightarrow \text{Opportunity Engine 0.1.1 (Gold)} \longrightarrow \text{Corpus de Avaliação}$$
- **Baseline Congelado:** as regras determinísticas `0.1.1` e os Golden Cases do Gate 3 permanecem estritamente congelados. Não é permitido afrouxar regras para induzir relevância artificial.
- **Revisão Humana Isenta:** os campos `human_*` no dataset de revisão humana são criados estritamente vazios. Nenhuma classificação humana pode ser inventada pelo agente ou preenchida por inferência.

---

## 3. Tipologia de Casos Alvo

O corpus de avaliação busca intencionalmente cobrir 5 categorias fundamentais de exemplos reais:

1. **Positivos Fortes:** contratações explícitas de equipamentos pesados, sistemas de exaustão, câmaras frias ou cozinhas completas (ex.: forno combinado industrial, caldeirão a vapor, coifa com exaustor para cozinha).
2. **Positivos Indiretos:** contratações de alimentação coletiva, merenda escolar ou gestão de UAN que representem sinais comerciais claros de infraestrutura alimentar institucional.
3. **Casos Ambíguos:** itens em aço inoxidável ou reformas prediais gerais que demandam análise humana do contexto da aplicação (ex.: bancada inox para preparo de alimentos vs. bancada inox para necrotério/laboratório).
4. **Negativos Difíceis:** objetos que contêm termos comumente associados ao domínio, mas em contextos expressamente negativos ou excludentes (ex.: exaustor automotivo, mobiliário de escritório, instrumental odontológico em aço inox).
5. **Negativos Óbvios:** contratações de serviços administrativos, TI, obras civis gerais ou materiais de escritório que representam a distribuição natural do setor público e devem ser descartadas com rapidez e alta confiança.

---

## 4. Domínios e Vocabulário de Interesse

| Domínio | Conceito Comercial | Termos Lexicais Canônicos |
|---|---|---|
| **COZINHA** | Ambientes de preparo institucional | cozinha industrial, cozinha institucional, cozinha escolar, cozinha hospitalar |
| **REFEITORIO** | Locais de consumo coletivo | refeitório, restaurante universitário |
| **INOX** | Mobiliário e superfícies sanitárias | mesa inox, bancada inox, pia inox, estante inox, cuba inox, prateleira inox |
| **COCCAO** | Preparo térmico profissional | forno industrial, forno combinado, fogão industrial, fritadeira industrial, caldeirão |
| **REFRIGERACAO** | Conservação térmica de alimentos | freezer industrial, refrigerador industrial, câmara fria, balcão frigorífico |
| **EXAUSTAO** | Tratamento de ar e gordura | coifa industrial, exaustor de cozinha, sistema de exaustão, duto de gordura |
| **LAVAGEM** | Higienização pesada de utensílios | lava-louças industrial |
| **INFRAESTRUTURA** | Obras civis dedicadas a alimentos | reforma de cozinha, construção de cozinha, adequação de refeitório |
| **ALIMENTACAO** | Operação e fornecimento coletivo | alimentação coletiva, merenda escolar, unidade de alimentação e nutrição, UAN |

---

## 5. Estratégia de Coleta e Amostragem Progressiva

Para assegurar estabilidade operacional e respeito aos limites da API pública do PNCP, a coleta segue um plano em fases:

- **Etapa A (Modalidades Centrais):** Modalidade 6 (`Pregão - Eletrônico`), a mais frequente para aquisições de bens e equipamentos institucionais, e Modalidade 8 (`Dispensa de Licitação`), comum em manutenções e peças sob demanda.
- **Etapa B (Expansão Temporal Controlada):** Variação de datas diárias recentes para diluir carga sobre a API do PNCP e evitar requisições volumosas que gerem timeout na fonte governamental.
- **Etapa C (Modalidades Complementares):** Inclusão da Modalidade 1 (`Concorrência - Eletrônica`) para identificação de reformas prediais e grandes adequações de infraestrutura, caso as modalidades anteriores não atinjam o teto mínimo.

### Metas e Condições de Parada (*Stop Conditions*)

A expansão de coleta será encerrada quando qualquer um dos seguintes critérios for atingido:
1. Obtenção de **pelo menos 30 candidatos relevantes** classificados pelo baseline determinístico 0.1.1; OU
2. Avaliação de até **2.000 registros brutos** do PNCP; OU
3. Limitação técnica comprovada e documentada na disponibilidade da API do PNCP.

---

## 6. Composição do Dataset de Revisão Humana

A partir da base Gold gerada, será extraído o arquivo `reports/gate4_5_human_review.csv` contendo entre 50 e 100 registros com a seguinte distribuição planejada:
- Todos os registros classificados como `ALTA` pelo baseline;
- Amostra substancial de registros `MEDIA`;
- Amostra de registros `BAIXA` (sinais indiretos / alimentação coletiva);
- Casos com termos ambíguos ou disparos de exclusão de contexto;
- Amostra aleatória controlada de registros `IRRELEVANTE`.

### Versionamento e Integridade

O dataset resultante será identificado como:
$$\text{evaluation\_corpus\_version} = 0.1.0$$
Após a geração do arquivo CSV, seu hash criptográfico SHA-256 será calculado e congelado. Nenhuma modificação nos registros ou nos campos de baseline poderá ser realizada posteriormente, garantindo que a revisão humana e as futuras avaliações de modelos de IA operem sobre uma base estável e livre de vazamento de dados (*data leakage*).
