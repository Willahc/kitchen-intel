"""Modelo Silver mínimo para contratações retornadas pelo PNCP."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


SILVER_SCHEMA_VERSION = "0.1.0"


@dataclass(frozen=True)
class PncpSilverRecord:
    """Representação canônica e rastreável de uma contratação PNCP."""

    source: str
    source_record_id: str
    source_url: str | None
    source_file: str
    source_files: tuple[str, ...]
    orgao_cnpj: str | None
    orgao_nome: str | None
    unidade_codigo: str | None
    unidade_nome: str | None
    objeto_compra: str | None
    modalidade_codigo: int | None
    modalidade_nome: str | None
    numero_compra: str | None
    ano_compra: int | None
    processo: str | None
    data_publicacao: str | None
    data_abertura_proposta: str | None
    data_encerramento_proposta: str | None
    valor_total_estimado: float | None
    situacao: str | None
    municipio: str | None
    uf: str | None
    captured_at: str
    normalized_at: str
    schema_version: str
    source_field_states: dict[str, str]

    def to_dict(self) -> dict[str, Any]:
        """Converte o registro em tipos serializáveis para JSON Lines."""
        result = asdict(self)
        result["source_files"] = list(self.source_files)
        return result
