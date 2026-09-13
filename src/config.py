"""Configurações explícitas e seguras para a coleta PNCP."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


PNCP_PUBLICATIONS_ENDPOINT = "https://pncp.gov.br/api/consulta/v1/contratacoes/publicacao"
COLLECTOR_VERSION = "0.1.0"


@dataclass(frozen=True)
class PncpCollectionConfig:
    """Parâmetros de uma execução reproduzível do coletor."""

    start_date: str
    end_date: str
    modality_code: int
    page_size: int = 10
    max_pages: int = 1
    start_page: int = 1
    timeout_seconds: float = 20.0
    max_attempts: int = 3
    output_dir: Path = Path("data/bronze/pncp")

    def __post_init__(self) -> None:
        if len(self.start_date) != 8 or not self.start_date.isdigit():
            raise ValueError("start_date deve usar o formato AAAAMMDD")
        if len(self.end_date) != 8 or not self.end_date.isdigit():
            raise ValueError("end_date deve usar o formato AAAAMMDD")
        if self.modality_code <= 0:
            raise ValueError("modality_code deve ser positivo")
        if self.page_size < 10:
            raise ValueError("page_size deve ser pelo menos 10, conforme validação atual do PNCP")
        if self.max_pages <= 0:
            raise ValueError("max_pages deve ser positivo")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds deve ser positivo")
        if self.max_attempts <= 0:
            raise ValueError("max_attempts deve ser positivo")
