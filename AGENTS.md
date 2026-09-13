# Regras para agentes

Antes de alterar o projeto, todo agente deve ler `README.md` e os documentos em `docs/` relevantes à mudança.

- Nunca assumir requisitos não documentados nem inventar dados.
- Distinguir explicitamente **fato**, **inferência** e **hipótese**.
- Não transformar ausência de dado em dado negativo.
- Preservar fonte, URL e evidência de qualquer oportunidade; toda oportunidade deve ser rastreável até a fonte.
- Priorizar fontes governamentais e institucionais e evitar scraping quando houver API ou dado aberto oficial.
- Não armazenar dados pessoais desnecessários nem coletar dados sensíveis.
- Nenhuma recomendação comercial pode ser produzida sem evidências.
- Não permitir que um LLM altere scores determinísticos diretamente sem regra documentada.
- Separar score de oportunidade de score de confiança.
- Qualquer IA futura deve produzir saída estruturada e validável.
- Toda alteração de arquitetura deve atualizar `docs/04_ARQUITETURA.md`.
- Todo novo campo de dados deve atualizar `docs/05_MODELO_DE_DADOS.md`.
- Toda nova regra de score deve atualizar `docs/06_SCORING.md`.
- Todo gate deve ter critérios objetivos de PASS/FAIL.
- Nenhuma tecnologia deve ser adicionada apenas porque aparece em uma vaga de emprego; cada adoção exige justificativa arquitetural clara.
- Usar IA como acelerador, mantendo validação humana, legibilidade, testes e entendimento humano.
