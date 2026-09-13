from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from src.normalizers.pncp import PncpNormalizationError, normalize_bronze_directory, normalize_pncp_record


def raw_record(**overrides: Any) -> dict[str, Any]:
    record: dict[str, Any] = {
        "numeroControlePNCP": "12345678000199-1-000001/2026",
        "orgaoEntidade": {"cnpj": "12345678000199", "razaoSocial": " ORGAO TESTE "},
        "unidadeOrgao": {"codigoUnidade": "001", "nomeUnidade": " Unidade Teste ", "municipioNome": "São Paulo", "ufSigla": "SP"},
        "objetoCompra": " Objeto sem reescrita ",
        "modalidadeId": 6,
        "modalidadeNome": "Pregão - Eletrônico",
        "numeroCompra": " 001/2026 ",
        "anoCompra": 2026,
        "processo": "PROC-1",
        "dataPublicacaoPncp": "2026-09-11T10:00:00",
        "dataAberturaProposta": "2026-09-12T10:00:00",
        "dataEncerramentoProposta": "2026-09-13T10:00:00",
        "valorTotalEstimado": 1234.5,
        "situacaoCompraNome": "Divulgada no PNCP",
        "linkSistemaOrigem": None,
    }
    record.update(overrides)
    return record


def write_bronze(path: Path, records: list[Any], captured_at: str = "2026-09-12T12:00:00+00:00") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"metadata": {"source": "PNCP", "captured_at": captured_at}, "payload": {"data": records}}), encoding="utf-8")
    return path


def test_valid_record_normalizes_types_and_lineage() -> None:
    record = normalize_pncp_record(raw_record(), source_file="data/bronze/pncp/a.json", captured_at="2026-09-12T12:00:00+00:00", normalized_at="2026-09-12T13:00:00+00:00")
    assert record.source_record_id == "12345678000199-1-000001/2026"
    assert record.orgao_nome == "ORGAO TESTE"
    assert record.unidade_codigo == "001"
    assert record.valor_total_estimado == 1234.5
    assert record.source_file == "data/bronze/pncp/a.json"
    assert record.captured_at.endswith("+00:00")


def test_optional_absent_is_recorded_without_invention() -> None:
    raw = raw_record()
    del raw["linkSistemaOrigem"]
    record = normalize_pncp_record(raw, source_file="a.json", captured_at="2026-09-12T12:00:00+00:00", normalized_at="2026-09-12T13:00:00+00:00")
    assert record.source_url is None
    assert record.source_field_states["linkSistemaOrigem"] == "absent"


def test_null_is_distinguished_from_absence() -> None:
    record = normalize_pncp_record(raw_record(linkSistemaOrigem=None), source_file="a.json", captured_at="2026-09-12T12:00:00+00:00", normalized_at="2026-09-12T13:00:00+00:00")
    assert record.source_field_states["linkSistemaOrigem"] == "null"


def test_valid_date_is_iso_normalized() -> None:
    record = normalize_pncp_record(raw_record(), source_file="a.json", captured_at="2026-09-12T12:00:00+00:00", normalized_at="2026-09-12T13:00:00+00:00")
    assert record.data_publicacao == "2026-09-11T10:00:00"


def test_invalid_date_is_rejected() -> None:
    with pytest.raises(PncpNormalizationError, match="dataPublicacaoPncp"):
        normalize_pncp_record(raw_record(dataPublicacaoPncp="not-a-date"), source_file="a.json", captured_at="2026-09-12T12:00:00+00:00", normalized_at="2026-09-12T13:00:00+00:00")


def test_numeric_value_is_preserved_as_number() -> None:
    record = normalize_pncp_record(raw_record(valorTotalEstimado=10), source_file="a.json", captured_at="2026-09-12T12:00:00+00:00", normalized_at="2026-09-12T13:00:00+00:00")
    assert record.valor_total_estimado == 10.0


def test_official_identifier_is_deterministic() -> None:
    first = normalize_pncp_record(raw_record(), source_file="a.json", captured_at="2026-09-12T12:00:00+00:00", normalized_at="2026-09-12T13:00:00+00:00")
    second = normalize_pncp_record(raw_record(), source_file="b.json", captured_at="2026-09-13T12:00:00+00:00", normalized_at="2026-09-13T13:00:00+00:00")
    assert first.source_record_id == second.source_record_id


def test_duplicate_keeps_newest_capture_and_preserves_all_lineage(tmp_path: Path) -> None:
    bronze = tmp_path / "bronze"
    output = tmp_path / "silver"
    write_bronze(bronze / "older.json", [raw_record()], "2026-09-12T12:00:00+00:00")
    write_bronze(bronze / "newer.json", [raw_record()], "2026-09-13T12:00:00+00:00")
    result = normalize_bronze_directory(bronze, output, tmp_path)
    row = json.loads(result.silver_file.read_text(encoding="utf-8"))
    assert result.duplicate_count == 1
    assert row["source_file"] == "bronze/newer.json"
    assert row["source_files"] == ["bronze/newer.json", "bronze/older.json"]


def test_conflict_between_captures_warns_and_keeps_newest(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    bronze = tmp_path / "bronze"
    output = tmp_path / "silver"
    write_bronze(bronze / "older.json", [raw_record(objetoCompra="original")], "2026-09-12T12:00:00+00:00")
    write_bronze(bronze / "newer.json", [raw_record(objetoCompra="alterado")], "2026-09-13T12:00:00+00:00")
    result = normalize_bronze_directory(bronze, output, tmp_path)
    row = json.loads(result.silver_file.read_text(encoding="utf-8"))
    assert row["objeto_compra"] == "alterado"
    assert "Conflito entre capturas" in caplog.text


def test_malformed_bronze_is_rejected(tmp_path: Path) -> None:
    bronze = tmp_path / "bronze" / "bad.json"
    bronze.parent.mkdir(parents=True)
    bronze.write_text("{invalid", encoding="utf-8")
    result = normalize_bronze_directory(bronze.parent, tmp_path / "silver", tmp_path)
    assert result.rejected_count == 1
    assert result.rejected_file is not None


def test_payload_without_data_is_rejected(tmp_path: Path) -> None:
    bronze = tmp_path / "bronze" / "empty.json"
    bronze.parent.mkdir(parents=True)
    bronze.write_text(json.dumps({"metadata": {"source": "PNCP", "captured_at": "2026-09-12T12:00:00+00:00"}, "payload": {}}), encoding="utf-8")
    result = normalize_bronze_directory(bronze.parent, tmp_path / "silver", tmp_path)
    assert result.rejected_count == 1


def test_invalid_record_is_written_to_rejected_jsonl(tmp_path: Path) -> None:
    bronze = write_bronze(tmp_path / "bronze" / "invalid.json", [raw_record(numeroControlePNCP="")])
    result = normalize_bronze_directory(bronze.parent, tmp_path / "silver", tmp_path)
    assert result.rejected_count == 1
    rejected = json.loads(result.rejected_file.read_text(encoding="utf-8"))  # type: ignore[union-attr]
    assert rejected["raw_record"]["numeroControlePNCP"] == ""


def test_jsonl_and_manifest_are_generated(tmp_path: Path) -> None:
    bronze = write_bronze(tmp_path / "bronze" / "one.json", [raw_record()])
    result = normalize_bronze_directory(bronze.parent, tmp_path / "silver", tmp_path)
    assert len(result.silver_file.read_text(encoding="utf-8").splitlines()) == 1
    manifest = json.loads(result.manifest_file.read_text(encoding="utf-8"))
    assert manifest["schema_version"] == "0.1.0"
    assert manifest["record_count"] == 1
    assert manifest["invalid_count"] == 0


def test_limit_restricts_records_without_touching_bronze(tmp_path: Path) -> None:
    bronze = write_bronze(tmp_path / "bronze" / "two.json", [raw_record(), raw_record(numeroControlePNCP="12345678000199-1-000002/2026")])
    result = normalize_bronze_directory(bronze.parent, tmp_path / "silver", tmp_path, limit=1)
    assert result.raw_record_count == 1
    assert result.valid_record_count == 1
