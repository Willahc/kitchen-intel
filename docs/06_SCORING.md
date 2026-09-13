# Scoring

## Hipótese original

Mede a atratividade comercial da oportunidade, não a certeza de que ela existe ou está ativa.

| Componente | Máximo |
|---|---:|
| Fit de segmento | 15 |
| Fit de produto | 15 |
| Sinal recente de compra | 25 |
| Expansão, reforma ou nova unidade | 15 |
| Ticket/valor estimado | 10 |
| Relacionamento/histórico com segmento | 10 |
| Geografia | 5 |
| Recência | 5 |
| **Total** | **100** |

Os pesos acima continuam como hipótese mais ampla. O Gate 3 implementa abaixo somente componentes suportados pelo Silver atual.

## Implementação Gate 3 (`scoring_version: 0.1.1`)

### Opportunity Score

| Componente | Máximo | Regra atual |
|---|---:|---|
| Fit de produto | 35 | ALTA 35; MEDIA 22; BAIXA 8; IRRELEVANTE 0, conforme classificação lexical |
| Sinal de compra | 25 | 25 para registro de fonte `PNCP` |
| Recência | 15 | publicação até 7 dias: 15; até 30: 10; até 90: 5; acima: 0 |
| Ticket | 15 | ≥500 mil: 15; ≥100 mil: 10; ≥25 mil: 5; abaixo: 2 |
| Fit de segmento | 10 | `not_available`: Gate 3 não infere segmento de órgão/unidade |

O total soma apenas componentes disponíveis. Um registro `IRRELEVANTE` recebe Score final 0 pela regra `IRRELEVANT_DOMAIN_GATE`, mesmo que possua sinal público de compra, pois não deve ser priorizado comercialmente. O breakdown continua mostrando os componentes calculados. Datas/valores ausentes ficam `not_available`, não zero por padrão.

### Confidence Score (0–100)

Mede a confiança da interpretação lexical, não a atratividade. Parte de 20 e adiciona: termo direto forte (+40), múltiplas categorias (+25) ou categoria única (+20), ID e objeto (+10), valor (+5) e datas (+5). Contexto negativo reconhecido adiciona +30 à confiança de exclusão, mas conflito positivo/negativo reduz 20. O resultado é limitado a 0–100.

Não é somado ao Opportunity Score e não deve substituí-lo.

## Regras de governança

Os pesos exigem calibração com dados e validação comercial. Cada regra futura deve ser determinística, explicável, versionada e documentada. LLMs podem apoiar classificação estruturada ou justificativa somente em gates futuros; não alteram scores determinísticos diretamente.
