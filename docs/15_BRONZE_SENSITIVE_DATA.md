# Dados sensíveis no Bronze

## Auditoria de padrões — 2026-09-13

Dois alertas de padrão de segredo foram inspecionados sem expor os respectivos
valores e sem modificar os artefatos Bronze canônicos.

| Artefato | Campo JSON | Classificação | Fundamentação |
| --- | --- | --- | --- |
| `data/bronze/pncp/2026/09/12/pncp_20260912T140758646831Z_e40b64d62286_page_3.json` | `payload.data.10.linkProcessoEletronico` | `FALSE_POSITIVE` | Campo de URL pública para processo eletrônico, com 247 caracteres; o padrão textual coincidiu incidentalmente. |
| `data/bronze/pncp/2026/09/12/pncp_20260912T140914037792Z_a8f67a52b6b8_page_3.json` | `payload.data.1.linkProcessoEletronico` | `FALSE_POSITIVE` | Campo de URL pública para processo eletrônico, com 247 caracteres; o padrão textual coincidiu incidentalmente. |

Não foram identificadas credenciais nesses dois campos. O Bronze canônico é
imutável: uma futura necessidade de compartilhamento deverá usar um export
sanitizado separado, nunca redação destrutiva do dado de origem.
