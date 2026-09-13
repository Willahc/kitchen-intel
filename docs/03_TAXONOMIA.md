# Taxonomia inicial e regras implementadas no Gate 3

Taxonomia lexical provisória para futura classificação e pesquisa. Termos poderão receber sinônimos, regras de contexto e versões nos gates posteriores.

| Categoria | Termos iniciais |
|---|---|
| COZINHA | cozinha industrial; cozinha institucional; cozinha profissional; cozinha escolar; cozinha hospitalar |
| REFEITORIO | refeitório; restaurante universitário; restaurante institucional; praça de alimentação institucional |
| INOX | mesa inox; bancada inox; pia inox; estante inox; prateleira inox; carro inox |
| COCCAO | forno combinado; forno industrial; fogão industrial; fritadeira industrial; chapa; caldeirão |
| REFRIGERACAO | freezer industrial; refrigerador industrial; câmara fria; balcão refrigerado |
| EXAUSTAO | coifa; exaustor; sistema de exaustão; ventilação de cozinha; dutos |
| LAVAGEM | lava-louças industrial; máquina de lavar louça; área de lavagem |
| INFRAESTRUTURA | reforma de cozinha; construção de cozinha; adequação de cozinha; reforma de refeitório; instalação de cozinha; manutenção de cozinha |
| ALIMENTACAO_COLETIVA | merenda escolar; alimentação hospitalar; alimentação coletiva; UAN; unidade de alimentação e nutrição |

## Classificação de relevância futura

- **ALTA:** evidência direta e contextual de demanda aderente.
- **MEDIA:** indício aderente, porém incompleto ou indireto.
- **BAIXA:** correspondência fraca ou pouco específica.
- **IRRELEVANTE:** sem aderência comercial documentada.

Essa classificação não deve ser aplicada como fato sem evidência e regra versionada.

## Baseline determinístico (`rules_version: 0.1.1`)

O texto original nunca é alterado. Para matching, o motor aplica apenas minúsculas, remoção de acentos, pontuação e espaços redundantes. Os termos canônicos acima foram preservados em `config/opportunity_rules.json`.

Foram adicionadas variantes lexicais mínimas porque os golden cases exigem grafias que os termos originais não cobriam: `cozinha` (termo genérico), `aço inox` e `mesa em aço inox`. Elas não são inferência semântica: são expressões literais e permanecem auditáveis em `matched_terms`.

`reforma`, `construção`, `adequação`, `instalação` e `manutenção` só atribuem `INFRAESTRUTURA` quando já existe outra categoria positiva no mesmo texto. Isso evita transformar uma obra genérica em oportunidade de cozinha.

### Contextos negativos versionados

`cozinha residencial`, `inox odontológico`, `consultório odontológico` e `exaustor automotivo` bloqueiam a atribuição comercial de categorias no baseline. O termo positivo ainda aparece em `matched_terms`, e a exclusão aparece em `negative_matches` e `NEGATIVE_CONTEXT`.

### Relevância efetiva

- **ALTA:** termo direto de cozinha institucional/industrial/profissional/escolar/hospitalar; `INFRAESTRUTURA` junto de outra categoria; ou `COZINHA` e `REFEITORIO` juntos.
- **MEDIA:** equipamento de inox, cocção, refrigeração, exaustão ou lavagem; ou cozinha/refeitório isolado.
- **BAIXA:** somente alimentação coletiva; por exemplo, `merenda escolar` é sinal indireto, não prova de compra de equipamento.
- **IRRELEVANTE:** nenhum termo, ou contexto negativo explícito.
