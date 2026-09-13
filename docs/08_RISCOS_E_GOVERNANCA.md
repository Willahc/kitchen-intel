# Riscos e governança

## Riscos iniciais

| Risco | Controle inicial |
|---|---|
| falsa oportunidade | evidência, fonte e revisão humana |
| edital encerrado classificado como ativo | validar datas e status na fonte |
| duplicidade | normalização e deduplicação versionadas |
| organização errada | preservar identificadores e evidência |
| CNPJ incorreto | não inferir; validar fonte cadastral |
| alucinação de LLM | grounding, saída estruturada e validação |
| score não explicável | regras determinísticas e versionadas |
| dado desatualizado | registrar captura e atualização |
| quebra de API | monitoramento, retries e alternativa documentada quando implementados |
| mudança de layout | priorizar interfaces oficiais e preservar Bronze |
| custo excessivo de LLM | métricas, limites e avaliação antes de escalar |
| coleta desnecessária de PII | minimização e revisão de campos |
| uso de dado não permitido | validar termos, licença e finalidade |
| viés de segmentação | revisar cobertura e critérios |
| dependência excessiva de IA | humano no loop e baseline determinístico |

## Princípios

- Fonte primeiro.
- Evidência antes da recomendação.
- Humano no loop.
- Versionamento.
- Explicabilidade.
- Minimização de PII.
- Logs.
- Auditabilidade.
