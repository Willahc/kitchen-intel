# Diário de aprendizado de engenharia

## Gate 1 — conceitos aplicados

| Conceito | Definição simples | Como apareceu aqui | Erro comum | Como explicar em entrevista |
|---|---|---|---|---|
| API | interface para programas trocarem dados | o script consulta a API pública oficial do PNCP | tratar página web como API ou inventar rota | “Consumi uma API pública oficial para coletar dados estruturados.” |
| HTTP | protocolo de pedido e resposta na web | cada `GET` recebe status e JSON do PNCP | ignorar status HTTP | “Controlei a resposta HTTP antes de gravar dados.” |
| JSON | texto estruturado para dados | a resposta do PNCP é salva como `payload` | alterar campos antes de preservar a origem | “Guardei o JSON retornado sem transformação semântica na Bronze.” |
| endpoint | rota que oferece uma operação | usamos `/v1/contratacoes/publicacao` | confundir endpoint com o portal inteiro | “Escolhi uma rota documentada para contratações por publicação.” |
| parâmetros de query | valores na URL que refinam a consulta | datas, modalidade, página e tamanho da página | usar formato de data ou tamanho inválido | “Passei parâmetros explícitos e registrei-os junto ao snapshot.” |
| status code | número que descreve o resultado HTTP | 200 grava Bronze; 400 encerra; 429/5xx podem repetir | salvar uma resposta de erro como dado | “Usei status para separar sucesso, falha definitiva e falha transitória.” |
| paginação | entrega de lista em partes | começa na página 1 e respeita `--max-pages` | baixar tudo ou criar loop infinito | “O coletor para por limite, total informado ou página vazia.” |
| timeout | tempo máximo de espera por tentativa | cada request usa 20 segundos por padrão | request sem limite pode travar o pipeline | “Todo acesso externo tem timeout explícito.” |
| retry | nova tentativa limitada após falha transitória | até 3 tentativas para timeout/conexão, 429 e 5xx selecionados | repetir 400 ou repetir indefinidamente | “Uso retry seletivo e limitado, para não mascarar erro nem sobrecarregar a fonte.” |
| backoff | espera crescente entre tentativas | espera 1 s, depois 2 s, depois 4 s quando aplicável | retentar imediatamente e gerar mais pressão | “Apliquei backoff exponencial simples para respeitar uma fonte instável.” |
| idempotência | reexecutar com resultado seguro e rastreável | cada execução usa timestamp UTC, `run_id`, página e abertura exclusiva do arquivo | sobrescrever snapshot ou misturar páginas | “Reexecuções preservam novos snapshots sem sobrescrever uma captura anterior.” |
| pipeline | sequência de etapas repetível | CLI → HTTP → validação → Bronze → logs | misturar coleta, classificação e análise em uma função | “Separei CLI, HTTP e persistência para manter o primeiro pipeline explicável.” |
| Bronze | camada de evidência crua próxima da fonte | arquivo contém metadata própria e `payload` original | normalizar ou classificar já na entrada | “Bronze é a prova de origem: preserva o retorno e o contexto de captura.” |

## Próximos conceitos (sem aprofundamento neste gate)

Schema (Gate 2); score determinístico (Gate 3); RAG, embedding e vector database (Gate 6); tool calling e LangGraph (Gate 7); LLM gateway e observabilidade (Gate 8); batch e Spark (Gate 9); streaming e Kafka (Gate 10); CI/CD e rollback (Gate 11); Terraform (Gate 12).

## Gate 2 — conceitos aplicados

| Conceito | Definição simples | Como usamos aqui | Erro comum | Como explicar em entrevista |
|---|---|---|---|---|
| Schema | contrato dos campos, tipos e regras de um dado | `PncpSilverRecord` define o mínimo canônico PNCP | copiar todos os campos sem propósito ou inventar campos | “Derivei o schema de um payload real e versionei-o.” |
| Normalização | tornar forma e tipos consistentes sem mudar o sentido | textos recebem apenas `strip`; datas são validadas; números viram número | resumir ou reinterpretar `objetoCompra` | “Normalizei estrutura, não conteúdo comercial.” |
| Validação | verificar se o dado respeita regras antes de ser aceito | ID oficial e datas inválidas causam rejeição auditável | descartar erro silenciosamente | “Dados inválidos vão para uma trilha de rejeição com motivo.” |
| Null | valor explicitamente ausente | `null` é preservado como ausência, sem virar zero | confundir `null` com dado negativo | “O normalizador não cria fatos a partir da falta de dado.” |
| Chave natural | identificador que já existe no sistema de origem | `numeroControlePNCP` é a chave natural | usar posição da página como identidade | “Preferi o identificador oficial da fonte.” |
| Chave composta | identidade formada por mais de um campo | não foi necessária neste payload | montar chave frágil sem documentar componentes | “Só usaria composição se a fonte não oferecesse ID estável.” |
| Identificador determinístico | mesma entrada gera a mesma identidade | o mesmo `numeroControlePNCP` mantém o mesmo `source_record_id` | gerar UUID novo para cada reprocessamento | “A identidade vem da fonte, não da execução.” |
| Deduplicação | consolidar ocorrências da mesma entidade | agrupa pelo ID e mantém a captura mais recente | apagar linhagem de capturas antigas | “Mantenho uma entidade e todas as evidências de captura.” |
| Lineage | caminho do dado desde sua origem | `source_file`, `source_files`, `captured_at` e versão de schema | guardar caminho absoluto local | “Consigo rastrear uma linha Silver até seu JSON Bronze.” |
| JSON Lines | arquivo com um JSON por linha | cada contratação Silver é uma linha; manifest fica separado | misturar metadados com registros | “JSONL é simples, legível e permite processamento por linha.” |
| Rebuild/reprocessamento | recriar uma camada derivada a partir da anterior | Silver é gerado só de Bronze, sem alteração do original | editar Bronze para corrigir Silver | “Posso apagar e reconstruir Silver sem perder a evidência original.” |

## Gate 3 — conceitos aplicados

| Conceito | Definição simples | Como usamos | Erro comum | Como explicar em entrevista |
|---|---|---|---|---|
| Regra determinística | mesma entrada e versão produzem a mesma decisão | JSON versionado, matching lexical e `--as-of` explícito | esconder regra em código disperso | “Construí um baseline reproduzível antes de IA.” |
| Baseline | referência mensurável para comparação futura | Golden Cases e métricas do motor 0.1.1 | comparar LLM sem referência | “Qualquer LLM futuro será comparado ao baseline.” |
| Classificação | atribuir categoria/relevância | termos produzem categorias e ALTA/MEDIA/BAIXA/IRRELEVANTE | confundir categoria com prioridade | “Classificação diz o que o texto parece indicar.” |
| Falso positivo | marcar como relevante algo que não é | `exaustor automotivo` seria exemplo sem exclusão | afrouxar regras para gerar oportunidades | “Contextos negativos reduzem falsos positivos.” |
| Falso negativo | deixar de marcar algo realmente relevante | variante lexical ainda não coberta | assumir que ausência de match prova irrelevância do mundo | “Golden Cases tornam lacunas de vocabulário visíveis.” |
| Precision | fração dos relevantes previstos que realmente são relevantes | calculada nos Golden Cases | medir só acurácia com classes desequilibradas | “Precision mede qualidade dos alertas.” |
| Recall | fração dos relevantes esperados que foram encontrados | calculado nos Golden Cases | ignorar oportunidades perdidas | “Recall mede cobertura dos sinais esperados.” |
| Feature | sinal mensurável usado numa regra | termos, data, valor e fonte PNCP | usar feature sem origem | “Cada feature vem do Silver ou da configuração.” |
| Score | número para ordenar atratividade | componentes e pontos aparecem em `score_breakdown` | criar pontuação mágica | “Cada ponto tem regra e evidência.” |
| Confidence | segurança da interpretação | mede qualidade lexical, não venda | somar confidence ao score comercial | “Separar confiança evita priorizar pela certeza errada.” |
| Reason code | motivo estruturado e estável | `EXHAUST_MATCH`, `NEGATIVE_CONTEXT`, `ACTIVE_PROCUREMENT` | explicação livre impossível de agregar | “Reason codes são auditáveis e fáceis de comparar.” |
| Golden case | caso sintético com resultado esperado | 10 textos representativos em fixture versionada | testar apenas exemplos reais favoráveis | “É um benchmark pequeno e controlado para regressão.” |

## Gate 4 — conceitos aplicados

| Conceito | Definição simples | Como usamos aqui | Erro comum | Como explicar em entrevista |
|---|---|---|---|---|
| Backend | parte que fornece dados e aplica contratos ao cliente | FastAPI lê Gold JSONL e responde endpoints GET | colocar regras comerciais duplicadas no frontend | “Criei um backend somente leitura para disponibilizar um dataset Gold rastreável.” |
| Frontend | interface executada no navegador | SPA React/Vite mostra indicadores, filtros, tabela e detalhe | tratar a tela como fonte da verdade | “O frontend apenas apresenta as respostas da API; não recalcula score.” |
| API provider | aplicação que oferece uma API para outros programas | FastAPI fornece `/stats` e `/opportunities` ao browser | confundir provider com quem consome a API | “O PNCP é provider para nossa coleta; nossa FastAPI é provider para o dashboard.” |
| REST | convenção HTTP orientada a recursos | oportunidades são consultadas por rotas previsíveis | assumir que REST exige banco ou CRUD completo | “Usei recursos e verbos HTTP simples para uma consulta de leitura.” |
| GET | pedido HTTP para obter uma representação | todos os endpoints do Gate 4 usam GET | fazer GET alterar ou disparar reprocessamento | “GET consulta Gold e não modifica nenhuma camada de dados.” |
| Path parameter | parte variável no caminho da rota | `/opportunities/{opportunity_id}` identifica uma oportunidade | colocar filtros opcionais no path | “Usei path parameter para a identidade do recurso.” |
| Query parameter | opção após `?` que refina a consulta | `uf`, `category`, `min_score`, `page` e `page_size` | aceitar valores sem validação | “Usei query parameters validados para filtrar e paginar.” |
| HTTP 200 | resposta de sucesso | lista, estatísticas e detalhe existente retornam 200 | interpretar 200 como garantia de dado relevante | “200 indica que a consulta foi atendida, não que há um lead.” |
| HTTP 404 | recurso solicitado não foi encontrado | ID inexistente em detalhe/evidence retorna 404 | retornar 200 com objeto inventado | “404 deixa a ausência explícita ao cliente da API.” |
| Schema de resposta | contrato da forma devolvida por uma API | Pydantic serializa lista, detalhe, stats e evidências | usar schema HTTP para duplicar regras do motor | “Separei contrato HTTP do modelo Gold e das regras de negócio.” |
| Serialização | converter estruturas internas em JSON para transporte | respostas FastAPI saem como JSON compatível com browser | expor objetos internos ou caminhos absolutos | “A API serializa somente os campos previstos no contrato.” |
| CORS | regra do navegador sobre origem que pode chamar uma API | API permite apenas `localhost:5173` e `127.0.0.1:5173` no desenvolvimento | liberar `*` sem necessidade | “Configurei CORS com as origens locais explícitas do frontend.” |
| Paginação de API | dividir uma lista em partes consultáveis | `page` e `page_size` limitam a tabela | devolver todos os registros para sempre | “A API pagina desde o MVP para controlar resposta e interface.” |
| SPA | aplicação web de uma página que atualiza a interface | React/Vite troca filtros e abre detalhe sem nova página do servidor | mover fonte de verdade para estado visual | “A SPA consome uma API e renderiza dados, mantendo a regra no backend.” |
| Client/server | cliente pede; servidor processa e responde | browser é cliente; FastAPI é servidor; Gold é fonte de leitura | misturar responsabilidades ou expor arquivo direto ao browser | “Separei consumo visual da entrega e validação de dados.” |
| Environment variable | valor configurável fora do código | `VITE_API_BASE_URL` define a base da API no frontend | espalhar `localhost` por diversos arquivos | “A URL do backend é configurável por ambiente sem segredo.” |

## Gate 4.5 — conceitos aplicados

| Conceito | Definição simples | Como usamos aqui | Erro comum | Como explicar em entrevista |
|---|---|---|---|---|
| Ground Truth | a verdade factual de referência para avaliação | anotação humana independente de William na planilha `gate4_5_human_review.csv` | tratar a saída do modelo/regra como se fosse a verdade | “Ground truth é o gabarito externo e independente com o qual medimos a qualidade real do sistema.” |
| Human Review | validação manual qualificada de dados | revisão por especialista de negócio sobre pertencimento ao domínio | inventar notas ou preencher automaticamente campos humanos | “O revisor humano audita uma amostra representativa sem viés de automação prévia.” |
| True Positive (TP) | o sistema previu relevante e de fato é relevante | se William confirmar um registro como TRUE e o baseline também o classificou como relevante, teremos um TP | contar qualquer predição positiva sem checagem de ground truth | “Acerto positivo do sistema: sinal de negócio real identificado corretamente.” |
| False Positive (FP) | o sistema previu relevante, mas na verdade não é | exaustor veicular marcado por engano como relevante por ter a palavra 'exaustor' | ignorar alertas falsos que cansam o time comercial | “Alarme falso: gasta tempo comercial com algo fora de escopo.” |
| True Negative (TN) | o sistema previu irrelevante e de fato não é relevante | se William confirmar um registro como FALSE e o baseline também o classificou como irrelevante, teremos um TN | esquecer que descartar o lixo corretamente é mérito do filtro | “Rejeição correta de ruído: protege o time de dezenas de milhares de compras irrelevantes.” |
| False Negative (FN) | o sistema previu irrelevante, mas na verdade era uma oportunidade | edital com 'área de cocção' que o léxico não conhecia e marcou como irrelevante | assumir que se o sistema não pegou, não existia no mundo | “Oportunidade perdida: o pior erro de negócio em prospecção ativa.” |
| Precision | taxa de assertividade dos positivos ($TP / (TP + FP)$) | mede qual fração das oportunidades alertadas realmente interessam | buscar 100% de precision ao custo de ignorar o mercado | “Precision mede a confiabilidade do sinal comercial gerado.” |
| Recall | taxa de cobertura do mercado ($TP / (TP + FN)$) | mede qual fração das oportunidades reais existentes foram encontradas | inflar recall aceitando qualquer palavra e inundando de lixo | “Recall mede o quanto o radar consegue cobrir sem deixar passar boas oportunidades.” |
| F1 Score | média harmônica balanceada entre Precision e Recall | métrica agregada para comparar baseline determinístico contra futuro LLM | usar média aritmética simples entre precision e recall | “F1 é a média harmônica que pune desbalanceamentos graves entre precisão e cobertura.” |
| Matriz de Confusão | tabela $2 \times 2$ relacionando previsão e ground truth | cruza predições de baseline contra anotação humana para exibir TP, FP, TN, FN | avaliar apenas acurácia global com classes desbalanceadas | “Apresenta a decomposição dos erros e acertos em vez de uma porcentagem genérica ilusória.” |
| Data Leakage | vazamento de dados de teste no design do modelo | separar estritamente o corpus de avaliação das regras e prompts | criar regras ou prompts olhando diretamente para as respostas do teste | “Congelamos o benchmark com hash para garantir que modelos futuros não sejam ajustados sobre o teste.” |
| Frozen Benchmark | dataset de teste imutável com hash criptográfico | `reports/gate4_5_human_review.csv` com hash SHA-256 fixo (`v0.1.0`) | alterar os exemplos de teste conforme for conveniente | “Garante reprodutibilidade científica na comparação entre regras e inteligência artificial.” |

### Por que a média harmônica (F1 Score)?

Se usássemos a média aritmética simples entre Precision e Recall:
$$\text{Média Aritmética} = \frac{\text{Precision} + \text{Recall}}{2}$$

Um classificador ingênuo que retornasse **todas** as 1.760 licitações como relevantes teria **Recall = 100%**, mas **Precision = 1,36%** (24 / 1760). A média aritmética seria de $(100 + 1,36) / 2 = 50,68\%$, sugerindo um sistema razoável quando na realidade ele é inútil.

A média harmônica dá peso muito maior ao menor valor:
$$F_1 = 2 \times \frac{\text{Precision} \times \text{Recall}}{\text{Precision} + \text{Recall}}$$

No exemplo acima:
$$F_1 = 2 \times \frac{0,0136 \times 1,00}{0,0136 + 1,00} = \frac{0,0272}{1,0136} \approx 2,68\%$$

O $F_1$ cai para próximo de zero, penalizando severamente o modelo que tenta "trapacear" aumentando apenas um dos lados.

- **Precision alta + Recall baixo:** O sistema quase nunca erra quando aponta uma oportunidade, mas é míope: perde 80% do mercado real.
- **Recall alto + Precision baixa:** O sistema acha quase tudo o que existe, mas gera tanto alarme falso que a equipe comercial perde a confiança e para de usar a ferramenta.

---

## Gate 4.6 — conceitos aplicados

| Conceito | Definição simples | Como usamos aqui | Erro comum | Como explicar em entrevista |
|---|---|---|---|---|
| Ground Truth | gabarito factual e auditável de referência | conjunto de anotações humanas independentes de William | tomar a predição da máquina ou do baseline como verdade | “Ground truth é o padrão-ouro independente com o qual medimos formalmente a precisão e cobertura do sistema.” |
| Annotation (Anotação) | atribuição de valor ou rótulo semântico a um dado por um especialista | William preenchendo pertinência (`human_relevant`), relevância, categorias e confiança | usar IA para pré-preencher anotação humana sem explicitar que foi gerada por máquina | “Anotação é o ato de qualificar o dado bruto com julgamento de domínio humano especializado.” |
| Annotator (Anotador) | especialista humano responsável por rotular os dados | William atuando como curador de negócio do domínio de cozinhas profissionais | atribuir a anotação a alguém sem conhecimento de domínio | “O anotador deve ser especialista de negócio para evitar ruído e inconsistência no benchmark.” |
| Label (Rótulo) | classe ou categoria atribuída a uma instância | `human_relevance` (ALTA/MEDIA/BAIXA/IRRELEVANTE) e as 9 categorias canônicas | usar vocabulário livre sem dicionário restrito e padronizado | “Definimos um esquema fechado e validado de rótulos para garantir consistência estatística.” |
| Benchmark | conjunto estruturado e imutável de testes para avaliar modelos competitivamente | corpus real de 76 registros do PNCP (`reports/evaluation_corpus_v0.1.0.csv`) | alterar os exemplos de teste quando o modelo erra | “Benchmark é o exame vestibular padronizado contra o qual baseline e futuros LLMs competem em condições idênticas.” |
| Blind Review (Revisão Cega) | avaliação realizada sem conhecimento prévio da resposta do sistema | interface oculta as notas e predições do baseline até que William salve sua decisão | exibir a nota do sistema antes de o humano julgar | “Revisão cega garante independência metodológica e anula a influência da máquina sobre o especialista.” |
| Anchoring Bias (Viés de Ancoragem) | viés cognitivo onde a primeira informação apresentada distorce decisões posteriores | revisor tender a concordar com a nota alta sugerida pelo sistema em vez de ler o edital com senso crítico | mostrar predições como 'sugestão' antes da anotação | “Ocultar o baseline determinístico durante a curadoria elimina o viés de ancoragem no anotador.” |
| Inter-annotator Agreement | grau de consenso estatístico entre diferentes revisores humanos | métricas como Cohen’s Kappa e percentual de concordância cruzada em expansões futuras | assumir que um único humano é infalível e livre de ambiguidade | “Mede a robustez do protocolo de anotação quando múltiplos especialistas avaliam a mesma amostra.” |
| Imutabilidade do Corpus | garantia de que a base de teste jamais seja alterada por gravações | `reports/evaluation_corpus_v0.1.0.csv` tem hash fixo; anotações vão para arquivo separado `reports/human_annotations_v0.1.0.csv` | sobrescrever o dataset de teste com as respostas no mesmo arquivo | “Isolamos fisicamente os dados de teste das anotações humanas para assegurar auditoria e rastreabilidade.” |

### Arquitetura de Software e Dependências de Engenharia

Para preservar a rastreabilidade e simplicidade do sistema, o projeto utiliza dependências mínimas e estritas em `requirements.txt`:
- `requests>=2.31,<3`: chamadas HTTP resilientes à API pública do PNCP.
- `pytest>=8,<10`: framework de testes unitários e de integração com asserções estritas.
- `fastapi>=0.115,<1`: framework web declarativo assíncrono com validação via Pydantic.
- `uvicorn>=0.30,<1`: servidor ASGI leve para servir a API de leitura e revisão.
- `httpx>=0.27,<1`: cliente HTTP utilizado pelo `TestClient` para execução dos testes automatizados.

No frontend:
- React 19 + TypeScript + Vite, construindo uma SPA rápida com abas para consulta do Radar de Oportunidades e Curadoria Humana com suporte a Blind Review.
- Comunicação via API REST (`GET /review`, `GET /review/{review_id}`, `PUT /review/{review_id}`, `GET /review/export`).

---

## Gate 5 — conceitos aplicados

| Conceito | Definição simples | Como usamos aqui | Erro comum | Como explicar em entrevista |
|---|---|---|---|---|
| LLM Inference | processo computacional em que o modelo pré-treinado gera uma resposta para uma entrada | chamada HTTP enviando os dados da licitação para obter a classificação B2B | achar que inferência treina ou altera os pesos do modelo | “Inferência é o consumo do modelo em tempo de execução: passamos o contexto e recebemos a predição estruturada.” |
| System Prompt | instrução mestre que define persona, regras de domínio, limites e formato de saída | `prompts/classifier_v0.1.0.txt` fixando as 9 categorias e regras de desambiguação | misturar dados voláteis do registro dentro do system prompt | “O system prompt é a constituição do modelo: estabelece comportamento, taxonomia e restrições imutáveis.” |
| User Prompt | mensagem dinâmica contendo os dados específicos da instância a ser avaliada | JSON contendo apenas os 7 campos públicos da contratação a ser classificada | incluir predições anteriores ou rótulos humanos no prompt de entrada | “O user prompt contém estritamente o caso a ser julgado, garantindo que o modelo decida caso a caso de forma limpa.” |
| Structured Output | garantia de que a saída do LLM obedece a um esquema formal estrito (JSON) | validação Pydantic com campos `relevant`, `relevance`, `categories`, `confidence`, `reason` | confiar em texto livre do LLM e tentar extrair com regex frágil | “Structured output transforma o texto probabilístico do LLM em objetos tipados e validáveis pelo sistema.” |
| Temperature | hiperparâmetro que calibra a aleatoriedade da amostragem das palavras | `temperature = 0.0` para maximizar determinismo e reprodutibilidade da classificação | usar temperature alta em tarefas de classificação e auditoria | “Em classificação de negócio, queremos repetibilidade: a mesma entrada deve gerar sempre a mesma decisão (temp=0).” |
| Token | unidade atômica de texto (pedaço de palavra ou caractere) processada pelo LLM | medição de `input_tokens` e `output_tokens` para precificação e auditoria de contexto | achar que 1 token equivale exatamente a 1 palavra ou 1 caractere | “Tokens são as fatias léxicas do vocabulário do modelo; em português, palavras complexas geram mais tokens.” |
| Context Window | quantidade máxima de tokens que o modelo pode processar de uma só vez | entrada concisa (~300 tokens) em modelo com janela de 128k tokens | lotar a janela com dados irrelevantes e encarecer o processamento | “Context window é o limite de memória imediata do modelo durante uma chamada de inferência.” |
| Latency | tempo decorrido entre o envio da requisição e o retorno completo da resposta | medição em milissegundos via `time.perf_counter()`, registrando percentis p50 e p95 | avaliar apenas acurácia e esquecer que uma API lenta quebra a experiência | “Latência mede a viabilidade operacional do modelo em esteiras de dados e interfaces em tempo real.” |
| Cost per Inference | custo monetário exato debitado pelo provedor para processar um registro | cálculo baseado nas tabelas oficiais ($0,15/1M in, $0,60/1M out no gpt-4o-mini) | não contabilizar custos e descobrir a conta no fim do mês | “O custo por inferência determina a viabilidade econômica do produto em escala de milhares de licitações.” |
| Cache de Inferência | armazenamento local de saídas indexado pelo hash dos parâmetros de entrada | chave SHA-256 de `input_hash + provider + model + prompt_version` em `llm_cache_v0.1.0.json` | pagar repetidamente pela mesma consulta ou gerar inconsistências | “Cache evita retrabalho: se o mesmo edital for processado com a mesma regra, devolvemos a predição a custo zero.” |
| Determinism | propriedade em que as mesmas entradas produzem rigorosamente a mesma saída | temperature zero e medição de agreement rate em teste de consistência | assumir que LLMs são determinísticos sem rodar testes empíricos | “Determinismo garante que o cliente comercial receba sempre a mesma análise para o mesmo edital.” |
| Evaluation | medição científica e objetiva da performance do modelo contra o padrão-ouro | cruzamento estatístico das predições do LLM contra os 76 registros de William | avaliar modelo olhando manualmente para 2 ou 3 exemplos soltos | “Avaliação é a prova dos nove: mede com números concretos se a IA realmente superou as regras determinísticas.” |
| Test Set | conjunto de dados intocado reservado exclusivamente para a avaliação final | os 76 registros de `reports/evaluation_corpus_v0.1.0.csv` | ajustar prompt repetidamente em cima dos erros do próprio teste | “Test set é o exame vestibular congelado: o modelo só é avaliado nele uma vez para evitar falsa impressão de sucesso.” |
| Development Set | conjunto de dados intermediário usado para testar e refinar prompts e hipóteses | dataset que será criado em gates futuros para engenharia de prompt | usar o test set como dev set e sofrer vazamento metodológico | “Dev set é o simulado de estudo: onde podemos errar, testar novos prompts e medir antes da prova real.” |
| Prompt Overfitting | ajuste excessivo do prompt para acertar casos específicos do teste, perdendo generalização | proibir inclusão de exemplos específicos dos 76 casos dentro de `classifier_v0.1.0.txt` | adicionar regras ad-hoc no prompt para cada caso que o modelo errou | “Prompt overfitting é 'decorar o gabarito da prova': parece perfeito no teste, mas quebra quando chega um dado novo.” |
| Incremental Batching | divisão do volume de inferência em lotes controlados com retomada idempotente | `--max-new-calls N` processando apenas o que falta sem reiniciar o que já está em cache | forçar execução monolítica de tudo de uma vez e perder trabalho ao cair a rede ou cota | “Lotes incrementais permitem avaliar grandes bases de forma segura e resiliente a limites de fornecedores de API.” |
| Rate Limit & Quota | restrição imposta por provedores sobre requisições por minuto (RPM) ou dia (RPD) | detecção de `GenerateRequestsPerDay` e interrupção limpa com `DailyQuotaExhaustedError` | insistir em loops de retry infinitos quando a cota diária já foi esgotada | “Diferenciamos 'rate limit momentâneo' (espera com backoff) de 'cota diária esgotada' (saída limpa até o próximo ciclo).” |
| Benchmark Model Integrity | garantia metodológica de que todas as instâncias de um teste são avaliadas pelo mesmo modelo | proibir a mistura de modelos diferentes (ex.: 20 A + 20 B + 36 C) para tentar burlar cotas | tratar predições de múltiplos modelos como se fossem o mesmo benchmark | “Para que a comparação científica seja justa, cada número do relatório deve vir estritamente do mesmo modelo.” |



