"""Coletor paginado da API pública de consultas do PNCP."""

from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

from src.config import COLLECTOR_VERSION, PNCP_PUBLICATIONS_ENDPOINT, PncpCollectionConfig


LOGGER = logging.getLogger(__name__)
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


class PncpCollectorError(RuntimeError):
    """Erro base de coleta, sempre acompanhado de contexto no log."""


class PncpHttpError(PncpCollectorError):
    """Resposta HTTP que não pôde ser recuperada."""


class PncpResponseError(PncpCollectorError):
    """Resposta que não contém JSON válido."""


@dataclass(frozen=True)
class CollectionResult:
    """Resumo de uma execução, sem normalizar registros da fonte."""

    pages_collected: int
    records_collected: int
    files: tuple[Path, ...]


class PncpCollector:
    """Consulta e persiste snapshots Bronze da rota oficial do PNCP."""

    def __init__(
        self,
        config: PncpCollectionConfig,
        session: requests.Session | None = None,
        sleep: Any = time.sleep,
    ) -> None:
        self.config = config
        self.session = session or requests.Session()
        self.sleep = sleep
        self.run_id = uuid.uuid4().hex[:12]
        self._captured_at = datetime.now(timezone.utc)

    def collect(self) -> CollectionResult:
        """Coleta até max_pages ou até a API indicar que não há mais páginas."""
        files: list[Path] = []
        records_collected = 0
        start = self.config.start_page
        end = start + self.config.max_pages
        for page in range(start, end):
            payload, status = self._request_page(page)
            records = _extract_records(payload)
            file_path = self._save_bronze(payload, status, page)
            files.append(file_path)
            records_collected += len(records)
            LOGGER.info("Página=%s status=%s registros=%s arquivo=%s", page, status, len(records), file_path)

            total_pages = _extract_total_pages(payload)
            if total_pages is not None and page >= total_pages:
                LOGGER.info("Fim da paginação informado pela fonte: total_paginas=%s", total_pages)
                break
            if not records:
                LOGGER.info("Fim da paginação: página sem registros")
                break
            if page < self.config.max_pages:
                self.sleep(1.0)

        LOGGER.info("Coleta concluída paginas=%s registros=%s", len(files), records_collected)
        return CollectionResult(len(files), records_collected, tuple(files))

    def _request_page(self, page: int) -> tuple[Any, int]:
        params = self._params_for_page(page)
        for attempt in range(1, self.config.max_attempts + 1):
            try:
                response = self.session.get(
                    PNCP_PUBLICATIONS_ENDPOINT,
                    params=params,
                    timeout=self.config.timeout_seconds,
                    headers={"Accept": "application/json"},
                )
            except (requests.Timeout, requests.ConnectionError) as error:
                if attempt == self.config.max_attempts:
                    raise PncpCollectorError(
                        f"Falha de conexão após {attempt} tentativas na página {page}"
                    ) from error
                self._retry_wait(attempt, page, f"{type(error).__name__}")
                continue

            LOGGER.info("Resposta HTTP pagina=%s status=%s", page, response.status_code)
            if response.status_code in RETRYABLE_STATUS_CODES:
                if attempt == self.config.max_attempts:
                    raise PncpHttpError(
                        f"HTTP {response.status_code} após {attempt} tentativas na página {page}"
                    )
                self._retry_wait(attempt, page, f"HTTP {response.status_code}")
                continue
            if not response.ok:
                # A mensagem curta da fonte ajuda a diagnosticar parâmetros inválidos;
                # nenhum payload de contratação é salvo ou registrado em caso de erro.
                detail = response.text[:500].replace("\n", " ")
                raise PncpHttpError(
                    f"HTTP não recuperável {response.status_code} na página {page}: {detail}"
                )
            try:
                return response.json(), response.status_code
            except ValueError as error:
                raise PncpResponseError(f"JSON inválido na página {page}") from error
        raise AssertionError("O loop de tentativas deveria sempre retornar ou lançar erro")

    def _params_for_page(self, page: int) -> dict[str, str | int]:
        return {
            "dataInicial": self.config.start_date,
            "dataFinal": self.config.end_date,
            "codigoModalidadeContratacao": self.config.modality_code,
            "pagina": page,
            "tamanhoPagina": self.config.page_size,
        }

    def _retry_wait(self, attempt: int, page: int, reason: str) -> None:
        delay = float(2 ** (attempt - 1))
        LOGGER.warning(
            "Retry pagina=%s tentativa=%s/%s motivo=%s espera_segundos=%s",
            page,
            attempt + 1,
            self.config.max_attempts,
            reason,
            delay,
        )
        self.sleep(delay)

    def _save_bronze(self, payload: Any, http_status: int, page: int) -> Path:
        captured_at = self._captured_at.astimezone(timezone.utc)
        day_directory = self.config.output_dir / captured_at.strftime("%Y/%m/%d")
        day_directory.mkdir(parents=True, exist_ok=True)
        timestamp = captured_at.strftime("%Y%m%dT%H%M%S%fZ")
        path = day_directory / f"pncp_{timestamp}_{self.run_id}_page_{page}.json"
        document = {
            "metadata": {
                "source": "PNCP",
                "captured_at": captured_at.isoformat(),
                "endpoint": PNCP_PUBLICATIONS_ENDPOINT,
                "params": self._params_for_page(page),
                "http_status": http_status,
                "collector_version": COLLECTOR_VERSION,
                "run_id": self.run_id,
            },
            "payload": payload,
        }
        try:
            with path.open("x", encoding="utf-8") as bronze_file:
                json.dump(document, bronze_file, ensure_ascii=False, indent=2)
                bronze_file.write("\n")
        except FileExistsError as error:
            raise PncpCollectorError(f"Conflito de nome Bronze: {path}") from error
        return path


def _extract_records(payload: Any) -> list[Any]:
    """Lê somente o envelope de paginação, sem modificar o payload salvo."""
    if not isinstance(payload, dict):
        return []
    for key in ("data", "content", "items"):
        value = payload.get(key)
        if isinstance(value, list):
            return value
    return []


def _extract_total_pages(payload: Any) -> int | None:
    if not isinstance(payload, dict):
        return None
    for key in ("totalPaginas", "totalPages"):
        value = payload.get(key)
        if isinstance(value, int) and value >= 0:
            return value
    return None
