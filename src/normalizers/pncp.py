"""Normalização determinística de snapshots Bronze PNCP para JSON Lines Silver."""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from src.models.pncp import PncpSilverRecord, SILVER_SCHEMA_VERSION


LOGGER = logging.getLogger(__name__)


class PncpNormalizationError(ValueError):
    """Registro ou envelope Bronze não atende às regras Silver."""


@dataclass(frozen=True)
class RejectedRecord:
    source_file: str
    reason: str
    raw_record: Any | None
    rejected_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_file": self.source_file,
            "reason": self.reason,
            "raw_record": self.raw_record,
            "rejected_at": self.rejected_at,
        }


@dataclass(frozen=True)
class NormalizationResult:
    raw_record_count: int
    valid_record_count: int
    rejected_count: int
    duplicate_count: int
    source_files: tuple[str, ...]
    silver_file: Path
    manifest_file: Path
    rejected_file: Path | None


def normalize_pncp_record(
    raw: dict[str, Any],
    *,
    source_file: str,
    captured_at: str,
    normalized_at: str,
) -> PncpSilverRecord:
    """Valida e normaliza um registro, sem modificar o objeto Bronze recebido."""
    states: dict[str, str] = {}
    orgao = _optional_object(raw, "orgaoEntidade", states)
    unidade = _optional_object(raw, "unidadeOrgao", states)
    source_record_id = _required_text(raw, "numeroControlePNCP", states)

    return PncpSilverRecord(
        source="PNCP",
        source_record_id=source_record_id,
        source_url=_optional_text(raw, "linkSistemaOrigem", states),
        source_file=source_file,
        source_files=(source_file,),
        orgao_cnpj=_optional_text(orgao, "cnpj", states, "orgaoEntidade.cnpj"),
        orgao_nome=_optional_text(orgao, "razaoSocial", states, "orgaoEntidade.razaoSocial"),
        unidade_codigo=_optional_text(unidade, "codigoUnidade", states, "unidadeOrgao.codigoUnidade"),
        unidade_nome=_optional_text(unidade, "nomeUnidade", states, "unidadeOrgao.nomeUnidade"),
        objeto_compra=_optional_text(raw, "objetoCompra", states),
        modalidade_codigo=_optional_integer(raw, "modalidadeId", states),
        modalidade_nome=_optional_text(raw, "modalidadeNome", states),
        numero_compra=_optional_text(raw, "numeroCompra", states),
        ano_compra=_optional_integer(raw, "anoCompra", states),
        processo=_optional_text(raw, "processo", states),
        data_publicacao=_optional_datetime(raw, "dataPublicacaoPncp", states),
        data_abertura_proposta=_optional_datetime(raw, "dataAberturaProposta", states),
        data_encerramento_proposta=_optional_datetime(raw, "dataEncerramentoProposta", states),
        valor_total_estimado=_optional_number(raw, "valorTotalEstimado", states),
        situacao=_optional_text(raw, "situacaoCompraNome", states),
        municipio=_optional_text(unidade, "municipioNome", states, "unidadeOrgao.municipioNome"),
        uf=_optional_text(unidade, "ufSigla", states, "unidadeOrgao.ufSigla"),
        captured_at=_normalize_timestamp(captured_at, "metadata.captured_at"),
        normalized_at=_normalize_timestamp(normalized_at, "normalized_at"),
        schema_version=SILVER_SCHEMA_VERSION,
        source_field_states=states,
    )


def normalize_bronze_directory(
    input_dir: Path,
    output_dir: Path,
    project_root: Path,
    limit: int | None = None,
) -> NormalizationResult:
    """Reconstrói um snapshot Silver a partir de todos os arquivos Bronze JSON."""
    if limit is not None and limit <= 0:
        raise ValueError("limit deve ser positivo")
    bronze_files = sorted(input_dir.rglob("*.json"))
    if not bronze_files:
        raise PncpNormalizationError(f"Nenhum arquivo JSON encontrado em {input_dir}")

    normalized_at = _utc_now()
    candidates: list[PncpSilverRecord] = []
    rejected: list[RejectedRecord] = []
    raw_count = 0
    source_files: list[str] = []

    for bronze_file in bronze_files:
        relative_file = _relative_path(bronze_file, project_root)
        source_files.append(relative_file)
        try:
            document = json.loads(bronze_file.read_text(encoding="utf-8"))
            metadata, records = _validate_bronze_document(document)
            captured_at = metadata["captured_at"]
        except (OSError, json.JSONDecodeError, PncpNormalizationError) as error:
            LOGGER.warning("Bronze malformado arquivo=%s erro=%s", relative_file, error)
            rejected.append(_rejection(relative_file, f"bronze_malformado: {error}", None, normalized_at))
            continue

        for raw in records:
            if limit is not None and raw_count >= limit:
                break
            raw_count += 1
            if not isinstance(raw, dict):
                rejected.append(_rejection(relative_file, "registro não é um objeto JSON", raw, normalized_at))
                continue
            try:
                candidates.append(
                    normalize_pncp_record(
                        raw,
                        source_file=relative_file,
                        captured_at=captured_at,
                        normalized_at=normalized_at,
                    )
                )
            except PncpNormalizationError as error:
                LOGGER.warning("Registro rejeitado arquivo=%s erro=%s", relative_file, error)
                rejected.append(_rejection(relative_file, str(error), raw, normalized_at))
        if limit is not None and raw_count >= limit:
            break

    records, duplicate_count = _deduplicate(candidates)
    return _write_outputs(
        records=records,
        rejected=rejected,
        raw_count=raw_count,
        duplicate_count=duplicate_count,
        source_files=tuple(source_files),
        output_dir=output_dir,
        generated_at=normalized_at,
    )


def _validate_bronze_document(document: Any) -> tuple[dict[str, Any], list[Any]]:
    if not isinstance(document, dict):
        raise PncpNormalizationError("documento Bronze não é objeto JSON")
    metadata = document.get("metadata")
    payload = document.get("payload")
    if not isinstance(metadata, dict):
        raise PncpNormalizationError("metadata ausente ou inválido")
    if metadata.get("source") != "PNCP":
        raise PncpNormalizationError("metadata.source deve ser PNCP")
    if not isinstance(metadata.get("captured_at"), str):
        raise PncpNormalizationError("metadata.captured_at ausente ou inválido")
    _normalize_timestamp(metadata["captured_at"], "metadata.captured_at")
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        raise PncpNormalizationError("payload.data ausente ou não é lista")
    return metadata, payload["data"]


def _deduplicate(records: Iterable[PncpSilverRecord]) -> tuple[list[PncpSilverRecord], int]:
    groups: dict[str, list[PncpSilverRecord]] = {}
    for record in records:
        groups.setdefault(record.source_record_id, []).append(record)
    deduplicated: list[PncpSilverRecord] = []
    duplicate_count = 0
    for source_record_id, group in groups.items():
        ordered = sorted(group, key=lambda item: (item.captured_at, item.source_file), reverse=True)
        selected = ordered[0]
        duplicate_count += len(ordered) - 1
        if len(ordered) > 1 and any(_business_view(item) != _business_view(selected) for item in ordered[1:]):
            LOGGER.warning("Conflito entre capturas para source_record_id=%s; mantida captura mais recente", source_record_id)
        all_files = tuple(sorted({item.source_file for item in ordered}))
        deduplicated.append(
            PncpSilverRecord(**{**selected.to_dict(), "source_files": all_files})
        )
    return sorted(deduplicated, key=lambda item: item.source_record_id), duplicate_count


def _business_view(record: PncpSilverRecord) -> dict[str, Any]:
    values = record.to_dict()
    for lineage_key in ("source_file", "source_files", "captured_at", "normalized_at"):
        values.pop(lineage_key)
    return values


def _write_outputs(
    *,
    records: list[PncpSilverRecord],
    rejected: list[RejectedRecord],
    raw_count: int,
    duplicate_count: int,
    source_files: tuple[str, ...],
    output_dir: Path,
    generated_at: str,
) -> NormalizationResult:
    output_dir.mkdir(parents=True, exist_ok=True)
    suffix = f"{datetime.fromisoformat(generated_at).strftime('%Y%m%dT%H%M%S%fZ')}_{uuid.uuid4().hex[:12]}"
    silver_file = output_dir / f"pncp_silver_{suffix}.jsonl"
    manifest_file = output_dir / f"pncp_silver_{suffix}.manifest.json"
    _write_jsonl_exclusive(silver_file, (record.to_dict() for record in records))

    rejected_file: Path | None = None
    if rejected:
        rejected_dir = output_dir / "rejected"
        rejected_dir.mkdir(parents=True, exist_ok=True)
        rejected_file = rejected_dir / f"pncp_rejected_{suffix}.jsonl"
        _write_jsonl_exclusive(rejected_file, (item.to_dict() for item in rejected))

    manifest = {
        "schema_version": SILVER_SCHEMA_VERSION,
        "generated_at": generated_at,
        "source_files": list(source_files),
        "raw_record_count": raw_count,
        "record_count": len(records),
        "invalid_count": len(rejected),
        "duplicate_count": duplicate_count,
        "rejected_file": _relative_output(rejected_file, output_dir) if rejected_file else None,
    }
    _write_json_exclusive(manifest_file, manifest)
    return NormalizationResult(
        raw_record_count=raw_count,
        valid_record_count=len(records),
        rejected_count=len(rejected),
        duplicate_count=duplicate_count,
        source_files=source_files,
        silver_file=silver_file,
        manifest_file=manifest_file,
        rejected_file=rejected_file,
    )


def _write_jsonl_exclusive(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    with path.open("x", encoding="utf-8") as output:
        for row in rows:
            output.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")))
            output.write("\n")


def _write_json_exclusive(path: Path, document: dict[str, Any]) -> None:
    with path.open("x", encoding="utf-8") as output:
        json.dump(document, output, ensure_ascii=False, indent=2)
        output.write("\n")


def _optional_object(raw: dict[str, Any], key: str, states: dict[str, str]) -> dict[str, Any]:
    value = raw.get(key, _MISSING)
    state = _absence_state(value)
    if state:
        states[key] = state
        return {}
    if not isinstance(value, dict):
        raise PncpNormalizationError(f"{key} deve ser objeto quando informado")
    return value


def _required_text(raw: dict[str, Any], key: str, states: dict[str, str]) -> str:
    value = _optional_text(raw, key, states)
    if value is None:
        raise PncpNormalizationError(f"{key} é obrigatório e está {states.get(key, 'ausente')}")
    return value


def _optional_text(raw: dict[str, Any], key: str, states: dict[str, str], state_key: str | None = None) -> str | None:
    value = raw.get(key, _MISSING)
    state = _absence_state(value)
    identifier = state_key or key
    if state:
        states[identifier] = state
        return None
    if not isinstance(value, str):
        raise PncpNormalizationError(f"{identifier} deve ser texto quando informado")
    stripped = value.strip()
    if not stripped:
        states[identifier] = "empty"
        return None
    return stripped


def _optional_integer(raw: dict[str, Any], key: str, states: dict[str, str]) -> int | None:
    value = raw.get(key, _MISSING)
    state = _absence_state(value)
    if state:
        states[key] = state
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise PncpNormalizationError(f"{key} deve ser inteiro quando informado")
    return value


def _optional_number(raw: dict[str, Any], key: str, states: dict[str, str]) -> float | None:
    value = raw.get(key, _MISSING)
    state = _absence_state(value)
    if state:
        states[key] = state
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PncpNormalizationError(f"{key} deve ser numérico quando informado")
    return float(value)


def _optional_datetime(raw: dict[str, Any], key: str, states: dict[str, str]) -> str | None:
    value = _optional_text(raw, key, states)
    if value is None:
        return None
    return _normalize_timestamp(value, key)


def _normalize_timestamp(value: str, field_name: str) -> str:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).isoformat()
    except ValueError as error:
        raise PncpNormalizationError(f"{field_name} não contém data ISO 8601 válida") from error


def _relative_path(path: Path, project_root: Path) -> str:
    try:
        return path.resolve().relative_to(project_root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _relative_output(path: Path, output_dir: Path) -> str:
    return path.relative_to(output_dir).as_posix()


def _rejection(source_file: str, reason: str, raw_record: Any | None, rejected_at: str) -> RejectedRecord:
    return RejectedRecord(source_file, reason, raw_record, rejected_at)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


_MISSING = object()


def _absence_state(value: Any) -> str | None:
    if value is _MISSING:
        return "absent"
    if value is None:
        return "null"
    if isinstance(value, str) and not value.strip():
        return "empty"
    return None
