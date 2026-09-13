# API e Dashboard MVP — Gate 4

## Objetivo e limite

O Gate 4 torna o Gold consultável por uma pessoa de negócio. É uma interface local, somente leitura e baseada exclusivamente em dados reais já produzidos pelo pipeline. Ela não cria oportunidades, não altera scores, não grava em Bronze/Silver/Gold e não usa IA.

Princípios e limites operacionais estabelecidos neste Gate:
- **API somente leitura:** expõe apenas endpoints `GET`; métodos de mutação (POST, PUT, DELETE) não existem nem são permitidos.
- **Sem banco de dados (sem PostgreSQL):** os dados são lidos diretamente do arquivo JSONL do snapshot Gold mais recente.
- **Sem IA / LLM:** nenhuma classificação, busca semântica ou geração de texto é feita por modelo de linguagem.
- **0 oportunidades relevantes na amostra atual é resultado legítimo:** reflete fielmente as regras determinísticas `0.1.1` sobre dados reais coletados do PNCP, nos quais nenhuma contratação pertencia ao domínio de cozinha/alimentação institucional. O frontend e o backend tratam esse cenário de forma transparente, sem fabricação de dados.

## Arquitetura

```text
Browser
  ↓ SPA React/Vite
HTTP GET
  ↓ FastAPI
Gold JSONL (snapshot mais recente, somente leitura)
```

O frontend usa `VITE_API_BASE_URL`; o exemplo local é fornecido em `frontend/.env.example`. A API permite CORS somente para `http://localhost:5173` e `http://127.0.0.1:5173` durante o desenvolvimento. Não há `*` porque o MVP conhece explicitamente suas origens locais.

## Por que ainda não há banco

Fato: a amostra do Gate 4 é pequena e o Gold é um JSON Lines reconstruível a partir de Silver. Um banco adicionaria migrações, operação e uma segunda fonte de estado sem necessidade demonstrada. A API carrega o snapshot Gold mais recente por meio de um repositório de leitura simples. PostgreSQL será reavaliado somente quando volume, consultas ou operação justificarem essa complexidade.

## Endpoints

| Rota | Resposta | Finalidade |
|---|---|---|
| `GET /health` | estado simples da aplicação | verificar disponibilidade local |
| `GET /stats` | contagens, médias e categorias | alimentar os indicadores do dashboard |
| `GET /opportunities` | lista paginada de Gold | pesquisa, filtros e tabela |
| `GET /opportunities/{opportunity_id}` | detalhe integral permitido pelo contrato | abrir uma oportunidade |
| `GET /opportunities/{opportunity_id}/evidence` | termos, motivos, score e lineage | explicar a classificação |

`GET /opportunities` aceita `q`, `uf`, `municipio`, `category`, `relevance`, `temporal_status`, `min_score`, `min_confidence`, `page` e `page_size`. A busca `q` é literal, sem case sensitivity, sobre `objeto_original`, `orgao_nome` e `unidade_nome`; não há busca semântica. A ordenação padrão é `opportunity_score` decrescente, depois `confidence_score` decrescente e finalmente ID para desempate reproduzível.

## Explicabilidade apresentada

O painel de detalhe monta a seção “Por que esta oportunidade foi classificada assim?” diretamente de `reason_codes`, `matched_terms`, `negative_matches`, `score_breakdown` e lineage Gold. Não há explicação gerada por IA. Quando `source_url` não existe no registro Gold, a tela informa que o link de origem não está disponível; ela nunca fabrica uma URL.

## Contratos e segurança

Pydantic é usado porque FastAPI o integra naturalmente para validar parâmetros e serializar contratos HTTP. Ele não replica o Opportunity Engine. Os endpoints aceitam apenas filtros tipados e não recebem caminhos de arquivo, comandos ou operações de escrita. O lineage é exposto com caminhos relativos, não absolutos.

## Execução local

```powershell
python -m pip install -r requirements.txt
python -m uvicorn src.api.app:app --host 127.0.0.1 --port 8000
```

Em outro terminal:

```powershell
Set-Location frontend
npm install
npm run dev
```

O build de produção do frontend é verificado com `npm run build`; este gate não realiza deploy.
