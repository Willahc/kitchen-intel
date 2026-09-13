from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import requests

from src.collectors.pncp import PncpCollector, PncpCollectorError, PncpHttpError, PncpResponseError
from src.config import PNCP_PUBLICATIONS_ENDPOINT, PncpCollectionConfig


class FakeResponse:
    def __init__(self, status_code: int, payload: Any = None, json_error: bool = False) -> None:
        self.status_code = status_code
        self.payload = payload
        self.json_error = json_error

    @property
    def ok(self) -> bool:
        return 200 <= self.status_code < 400

    @property
    def text(self) -> str:
        return "fake response"

    def json(self) -> Any:
        if self.json_error:
            raise ValueError("invalid json")
        return self.payload


class FakeSession:
    def __init__(self, outcomes: list[Any]) -> None:
        self.outcomes = iter(outcomes)
        self.calls: list[dict[str, Any]] = []

    def get(self, url: str, **kwargs: Any) -> FakeResponse:
        self.calls.append({"url": url, **kwargs})
        outcome = next(self.outcomes)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


def config(tmp_path: Path, **overrides: Any) -> PncpCollectionConfig:
    values = {
        "start_date": "20260910",
        "end_date": "20260910",
        "modality_code": 6,
        "page_size": 10,
        "max_pages": 2,
        "output_dir": tmp_path,
    }
    values.update(overrides)
    return PncpCollectionConfig(**values)


def test_success_preserves_payload_and_writes_correct_metadata(tmp_path: Path) -> None:
    payload = {"data": [{"objetoCompra": "cozinha"}], "totalPaginas": 1}
    session = FakeSession([FakeResponse(200, payload)])
    result = PncpCollector(config(tmp_path), session=session, sleep=lambda _: None).collect()

    assert result.pages_collected == 1
    assert result.records_collected == 1
    saved = json.loads(result.files[0].read_text(encoding="utf-8"))
    assert saved["payload"] == payload
    assert saved["metadata"]["source"] == "PNCP"
    assert saved["metadata"]["http_status"] == 200
    assert saved["metadata"]["endpoint"] == PNCP_PUBLICATIONS_ENDPOINT
    assert saved["metadata"]["params"]["pagina"] == 1
    assert session.calls[0]["timeout"] == 20.0


def test_invalid_json_raises_error(tmp_path: Path) -> None:
    collector = PncpCollector(config(tmp_path), session=FakeSession([FakeResponse(200, json_error=True)]), sleep=lambda _: None)
    with pytest.raises(PncpResponseError):
        collector.collect()


def test_timeout_retries_then_succeeds(tmp_path: Path) -> None:
    session = FakeSession([requests.Timeout(), FakeResponse(200, {"data": [], "totalPaginas": 1})])
    waits: list[float] = []
    result = PncpCollector(config(tmp_path), session=session, sleep=waits.append).collect()
    assert result.pages_collected == 1
    assert len(session.calls) == 2
    assert waits == [1.0]


def test_non_retryable_http_error_does_not_retry(tmp_path: Path) -> None:
    session = FakeSession([FakeResponse(400, {})])
    with pytest.raises(PncpHttpError, match="não recuperável 400"):
        PncpCollector(config(tmp_path), session=session, sleep=lambda _: None).collect()
    assert len(session.calls) == 1


@pytest.mark.parametrize("status", [429, 500])
def test_retryable_http_errors_retry_with_limit(tmp_path: Path, status: int) -> None:
    session = FakeSession([FakeResponse(status, {}), FakeResponse(200, {"data": [], "totalPaginas": 1})])
    result = PncpCollector(config(tmp_path), session=session, sleep=lambda _: None).collect()
    assert result.pages_collected == 1
    assert len(session.calls) == 2


def test_pagination_stops_at_source_total_pages(tmp_path: Path) -> None:
    session = FakeSession([
        FakeResponse(200, {"data": [{"id": 1}], "totalPaginas": 2}),
        FakeResponse(200, {"data": [{"id": 2}], "totalPaginas": 2}),
    ])
    result = PncpCollector(config(tmp_path, max_pages=5), session=session, sleep=lambda _: None).collect()
    assert result.pages_collected == 2
    assert result.records_collected == 2
    assert [call["params"]["pagina"] for call in session.calls] == [1, 2]


def test_bronze_names_do_not_collide_between_runs(tmp_path: Path) -> None:
    first = PncpCollector(config(tmp_path), session=FakeSession([FakeResponse(200, {"data": [], "totalPaginas": 1})]), sleep=lambda _: None).collect()
    second = PncpCollector(config(tmp_path), session=FakeSession([FakeResponse(200, {"data": [], "totalPaginas": 1})]), sleep=lambda _: None).collect()
    assert first.files[0] != second.files[0]
    assert first.files[0].exists() and second.files[0].exists()


def test_connection_error_fails_after_configured_limit(tmp_path: Path) -> None:
    session = FakeSession([requests.ConnectionError(), requests.ConnectionError(), requests.ConnectionError()])
    with pytest.raises(PncpCollectorError, match="após 3 tentativas"):
        PncpCollector(config(tmp_path), session=session, sleep=lambda _: None).collect()
    assert len(session.calls) == 3


def test_page_size_below_pncp_minimum_is_rejected() -> None:
    with pytest.raises(ValueError, match="pelo menos 10"):
        PncpCollectionConfig(
            start_date="20260910",
            end_date="20260910",
            modality_code=6,
            page_size=9,
        )
