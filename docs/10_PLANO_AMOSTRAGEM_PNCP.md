# Plano de amostragem PNCP — Gate 4

## Objetivo

Ampliar controladamente a amostra real para validar consulta, filtros e dashboard. Não há filtragem de domínio durante a coleta: cada resposta oficial completa é preservada em Bronze.

## Fonte e rota

Fonte: API pública oficial de consultas do PNCP. Rota: `GET /api/consulta/v1/contratacoes/publicacao`. A documentação oficial indica que `codigoModalidadeContratacao` é parâmetro obrigatório e aponta as tabelas de domínio de modalidades no portal PNCP.

## Plano aprovado para esta execução

| Consulta | Modalidade | Período | Páginas máximas | Tamanho de página | Máximo teórico |
|---|---:|---|---:|---:|---:|
| A | 6 | 2026-09-08 a 2026-09-09 | 2 | 10 | 20 |
| B | 8 | 2026-09-08 a 2026-09-09 | 2 | 10 | 20 |

O código 6 já foi observado no payload real como `Pregão - Eletrônico`. O código 8 é uma modalidade usada como exemplo no manual oficial de consultas; seu nome não é assumido neste plano e será obtido somente da resposta oficial, caso haja registros.

O intervalo de dois dias é recente em relação à execução de 2026-09-12 e o teto de 40 registros evita tentativa de baixar o PNCP integralmente. Caso uma consulta não tenha registros ou falhe, o fato será registrado; não haverá ampliação automática de período ou páginas.

## Rastreabilidade e reprocessamento

Cada página será salva como novo snapshot Bronze pelo coletor existente, com endpoint, parâmetros, HTTP status, timestamp UTC e versão do coletor. Depois, os pipelines existentes reconstruirão Silver e Gold; nenhuma rota paralela ou filtro pré-Bronze será criado.

## Resultado da execução em 2026-09-12

- Consulta A (modalidade 6): não gerou snapshot novo. A página 1 sofreu `ReadTimeout` e esgotou o limite de três tentativas.
- Consulta B (modalidade 8): a página 1 respondeu HTTP 200 e gerou um Bronze com 10 registros. O payload confirmou `modalidadeNome: Dispensa`.
- A página 2 da consulta B sofreu timeout e esgotou o mesmo limite de três tentativas.

Portanto, a expansão efetiva foi de **1 arquivo Bronze e 10 registros**, abaixo do teto planejado de 40. Não houve extensão automática de datas, páginas ou novas modalidades.

## Limites

- Sem scraping, credenciais ou endpoints internos.
- Sem classificação durante coleta.
- Sem alteração das regras `0.1.1` para induzir oportunidades.
- A amostra serve para teste do MVP; não representa o mercado inteiro.
