# Fontes candidatas e auditoria do Gate 1

Status verificados no Gate 1. Somente PNCP foi integrado; nenhuma outra fonte foi coletada.

## PNCP — CONFIRMADO E IMPLEMENTADO

- **Portal e Dados Abertos oficiais:** <https://www.gov.br/pncp/pt-br/> e <https://www.gov.br/pncp/pt-br/acesso-a-informacao/dados-abertos>.
- **Documentação técnica oficial:** <https://pncp.gov.br/api/consulta/swagger-ui/index.html?configUrl=/pncp-api/v3/api-docs/swagger-config>. O manual oficial de consultas também registra a rota escolhida: <https://www.gov.br/pncp/pt-br/central-de-conteudo/manuais/versoes-anteriores/ManualPNCPAPIConsultasVerso1.0.pdf>.
- **Endpoint escolhido e confirmado em execução real:** `GET https://pncp.gov.br/api/consulta/v1/contratacoes/publicacao`.
- **Finalidade:** consultar contratações por data de publicação. A resposta é JSON e o acesso é público, sem login.
- **Parâmetros usados:** `dataInicial`, `dataFinal`, `codigoModalidadeContratacao`, `pagina` e `tamanhoPagina`. O manual identifica os quatro primeiros como obrigatórios para esta rota; `tamanhoPagina` foi aceito e validado na execução real.
- **Formato de datas:** `AAAAMMDD`.
- **Paginação:** começa em `pagina=1`; a resposta contém registros em `data` e pode informar `totalPaginas`. O coletor também para em página sem registros e sempre respeita `--max-pages`.
- **Limite conhecido verificado:** a API respondeu HTTP 400 quando `tamanhoPagina=2`, informando mínimo de 10. O código rejeita valores abaixo de 10. Não foi assumido limite máximo sem confirmação oficial.
- **Erros:** timeout/erro de conexão e HTTP 429, 500, 502, 503 e 504 recebem no máximo três tentativas; outros status HTTP encerram a execução com erro visível. A política é do projeto, não uma promessa da API.

## Centro Paula Souza — CONFIRMADO COMO FONTE CANDIDATA; NÃO IMPLEMENTADO

O portal oficial Dados Abertos SP publica o conjunto [Licitações do Centro Paula Souza](https://dadosabertos.sp.gov.br/dataset/licitacoes-do-centro-paula-souza), com recurso estruturado referido como MySQL e origem em `https://dados.cps.sp.gov.br/licitacoes/`. A página declara cobertura de licitações de 2017 a 2024, última atualização exibida em 17/04/2025 e **nenhuma licença fornecida**.

Não há, nesta auditoria, uma documentação de API oficial clara e atual para esse recurso que permita uma integração segura e reprodutível. Portanto, o CPS não foi integrado e nenhum endpoint interno de frontend ou scraping foi usado. Em gate futuro, a integração deverá validar licença, atualização, documentação de acesso e se PNCP/Transparência SP oferece cobertura mais adequada.

| Fonte | Tipo | Cobertura | Acesso | Formato | Frequência esperada | Valor comercial | Riscos | Status de integração |
|---|---|---|---|---|---|---|---|---|
| PNCP | API pública oficial de consultas | contratações publicadas no PNCP | público, sem login | JSON | sob consulta; validar monitoramento posterior | alto: contratações e avisos correlatos | cobertura declarada pelos entes, disponibilidade e mudanças de API | CONFIRMADO / IMPLEMENTADO |
| Centro Paula Souza — licitações | conjunto oficial Dados Abertos SP | licitações CPS declaradas de 2017 a 2024 | recurso estruturado; documentação/licença a validar | MySQL indicado pelo portal | histórico; atualidade a validar | alto para ICP prioritário | licença ausente, recorte histórico, API clara não confirmada | CONFIRMADO / NÃO IMPLEMENTADO |
| Fundação CASA — dados públicos | portal institucional | Fundação CASA, quando disponível | dado público institucional; validar | a validar | a validar | alto para ICP prioritário | disponibilidade e detalhamento a validar | NÃO IMPLEMENTADO |
| Compras.gov.br | portal público de compras | órgãos aderentes/aplicáveis | dado público; validar aplicabilidade | a validar | a validar | alto: complementa oportunidades públicas | cobertura e regras de acesso a validar | NÃO IMPLEMENTADO |
| Receita Federal / Dados Abertos CNPJ | dados abertos cadastrais | organizações com CNPJ | dado aberto; validar versão/acesso | a validar | a validar | médio: enriquecimento organizacional | atualização, vínculos e uso correto de dados | NÃO IMPLEMENTADO |
| CNES | base pública de estabelecimentos de saúde | saúde | dado público; validar | a validar | a validar | médio: qualificação de ICP | defasagem e interpretação cadastral | NÃO IMPLEMENTADO |
| INEP | dados educacionais | educação | dado público; validar | a validar | a validar | médio: qualificação de ICP | defasagem e granularidade | NÃO IMPLEMENTADO |
| e-MEC | cadastro educacional | educação superior | acesso público; validar | a validar | a validar | médio: qualificação de ICP | cobertura e atualização | NÃO IMPLEMENTADO |
| Cadastur | cadastro turístico | turismo | acesso público; validar | a validar | a validar | futuro: hotéis/resorts | cobertura e atualização | NÃO IMPLEMENTADO |
| dados.gov.br | catálogo de dados públicos | nacional e setorial | dados abertos; validar conjunto a conjunto | a validar | a validar | variável | qualidade e licenças por conjunto | NÃO IMPLEMENTADO |
| Portais estaduais e municipais | portais públicos | local/regional | varia por ente; validar | a validar | a validar | alto para cobertura local | heterogeneidade, layout e acesso | NÃO IMPLEMENTADO |
| Diários oficiais | publicação oficial | nacional, estadual e municipal | acesso público; validar | a validar | a validar | complementar: sinais e atos | ruído, volume e mudanças de layout | NÃO IMPLEMENTADO |
