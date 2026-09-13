"""Modelo Gold explicável para o baseline determinístico."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class OpportunityRecord:
    opportunity_id: str
    source: str
    source_record_id: str
    orgao_nome: str | None
    orgao_cnpj: str | None
    unidade_nome: str | None
    municipio: str | None
    uf: str | None
    objeto_original: str | None
    categories: tuple[str, ...]
    matched_terms: tuple[dict[str, str], ...]
    negative_matches: tuple[dict[str, str], ...]
    relevance: str
    temporal_status: str
    data_publicacao: str | None
    data_abertura_proposta: str | None
    data_encerramento_proposta: str | None
    valor_total_estimado: float | None
    opportunity_score: int
    confidence_score: int
    score_breakdown: dict[str, dict[str, Any]]
    reason_codes: tuple[str, ...]
    source_silver_file: str
    source_bronze_files: tuple[str, ...]
    rules_version: str
    generated_at: str

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        for field in ("categories", "matched_terms", "negative_matches", "reason_codes", "source_bronze_files"):
            result[field] = list(result[field])
        return result
