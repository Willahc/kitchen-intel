"""Leitura Silver e geração Gold rastreável pelo motor determinístico."""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from src.models.opportunity import OpportunityRecord
from src.opportunity.classifier import classify_text
from src.opportunity.scoring import score_confidence, score_opportunity, temporal_status


LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class GoldBuildResult:
    gold_file: Path
    manifest_file: Path
    input_record_count: int
    relevant_count: int
    irrelevant_count: int


def load_rules(path: Path) -> dict[str, Any]:
    document = json.loads(path.read_text(encoding="utf-8"))
    required = {"rules_version", "categories", "negative_terms", "score_weights", "confidence"}
    missing = required - set(document)
    if missing:
        raise ValueError(f"Configuração de regras incompleta: {sorted(missing)}")
    return document


def build_opportunity(record: dict[str, Any], source_silver_file: str, as_of: date, generated_at: str, rules: dict[str, Any]) -> OpportunityRecord:
    """Transforma uma linha Silver em Gold sem modificar o registro de origem."""
    classification = classify_text(record.get("objeto_compra"), rules)
    status, temporal_reasons = temporal_status(record, as_of)
    opportunity_score, breakdown, score_reasons = score_opportunity(record, classification, as_of, rules)
    confidence_score, confidence_reasons = score_confidence(record, classification, rules)
    source = _required_string(record, "source")
    source_record_id = _required_string(record, "source_record_id")
    rules_version = rules["rules_version"]
    identifier = hashlib.sha256(f"{source}|{source_record_id}|{rules_version}".encode("utf-8")).hexdigest()[:24]
    reasons = sorted(set(classification["reason_codes"] + tuple(temporal_reasons + score_reasons + confidence_reasons)))
    return OpportunityRecord(
        opportunity_id=identifier,
        source=source,
        source_record_id=source_record_id,
        orgao_nome=_optional_string(record, "orgao_nome"),
        orgao_cnpj=_optional_string(record, "orgao_cnpj"),
        unidade_nome=_optional_string(record, "unidade_nome"),
        municipio=_optional_string(record, "municipio"),
        uf=_optional_string(record, "uf"),
        objeto_original=_optional_string(record, "objeto_compra"),
        categories=classification["categories"],
        matched_terms=classification["matched_terms"],
        negative_matches=classification["negative_matches"],
        relevance=classification["relevance"],
        temporal_status=status,
        data_publicacao=_optional_string(record, "data_publicacao"),
        data_abertura_proposta=_optional_string(record, "data_abertura_proposta"),
        data_encerramento_proposta=_optional_string(record, "data_encerramento_proposta"),
        valor_total_estimado=_optional_number(record, "valor_total_estimado"),
        opportunity_score=opportunity_score,
        confidence_score=confidence_score,
        score_breakdown=breakdown,
        reason_codes=tuple(reasons),
        source_silver_file=source_silver_file,
        source_bronze_files=tuple(record.get("source_files", [])),
        rules_version=rules_version,
        generated_at=generated_at,
    )


def build_gold(silver_dir: Path, output_dir: Path, project_root: Path, rules_path: Path, as_of: date) -> GoldBuildResult:
    rules = load_rules(rules_path)
    silver_files = sorted(path for path in silver_dir.glob("*.jsonl") if path.is_file())
    if not silver_files:
        raise ValueError(f"Nenhum JSONL Silver encontrado em {silver_dir}")
    generated_at = datetime.now(timezone.utc).isoformat()
    opportunities: list[OpportunityRecord] = []
    input_files: list[str] = []
    for silver_file in silver_files:
        relative_silver = _relative_path(silver_file, project_root)
        input_files.append(relative_silver)
        for line_number, line in enumerate(silver_file.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            try:
                opportunities.append(build_opportunity(json.loads(line), relative_silver, as_of, generated_at, rules))
            except (json.JSONDecodeError, ValueError, TypeError) as error:
                raise ValueError(f"Silver inválido em {relative_silver}:{line_number}: {error}") from error
    unique = _deduplicate_opportunities(opportunities)
    output_dir.mkdir(parents=True, exist_ok=True)
    suffix = f"{datetime.fromisoformat(generated_at).strftime('%Y%m%dT%H%M%S%fZ')}_{uuid.uuid4().hex[:12]}"
    gold_file = output_dir / f"opportunities_{suffix}.jsonl"
    manifest_file = output_dir / f"opportunities_{suffix}.manifest.json"
    _write_jsonl(gold_file, (item.to_dict() for item in unique))
    manifest = _manifest(unique, input_files, generated_at, rules["rules_version"], len(opportunities))
    _write_json(manifest_file, manifest)
    return GoldBuildResult(gold_file, manifest_file, len(opportunities), manifest["relevant_count"], manifest["irrelevant_count"])


def _deduplicate_opportunities(records: list[OpportunityRecord]) -> list[OpportunityRecord]:
    unique: dict[str, OpportunityRecord] = {}
    for record in records:
        previous = unique.get(record.opportunity_id)
        if previous and previous.source_silver_file != record.source_silver_file:
            LOGGER.warning("Duplicata Gold opportunity_id=%s; mantido arquivo Silver lexicograficamente posterior", record.opportunity_id)
        if previous is None or record.source_silver_file >= previous.source_silver_file:
            unique[record.opportunity_id] = record
    return sorted(unique.values(), key=lambda item: item.opportunity_id)


def _manifest(records: list[OpportunityRecord], source_files: list[str], generated_at: str, rules_version: str, input_record_count: int) -> dict[str, Any]:
    relevance_counts = {level: sum(item.relevance == level for item in records) for level in ("ALTA", "MEDIA", "BAIXA", "IRRELEVANTE")}
    temporal_counts = {level: sum(item.temporal_status == level for item in records) for level in ("ATIVA", "FUTURA", "ENCERRADA", "INDETERMINADA")}
    category_counts: dict[str, int] = {}
    for record in records:
        for category in record.categories:
            category_counts[category] = category_counts.get(category, 0) + 1
    return {
        "rules_version": rules_version,
        "generated_at": generated_at,
        "source_silver_files": source_files,
        "input_record_count": input_record_count,
        "relevant_count": sum(value for key, value in relevance_counts.items() if key != "IRRELEVANTE"),
        "irrelevant_count": relevance_counts["IRRELEVANTE"],
        "active_count": temporal_counts["ATIVA"],
        "future_count": temporal_counts["FUTURA"],
        "closed_count": temporal_counts["ENCERRADA"],
        "indeterminate_count": temporal_counts["INDETERMINADA"],
        "high_relevance_count": relevance_counts["ALTA"],
        "medium_relevance_count": relevance_counts["MEDIA"],
        "low_relevance_count": relevance_counts["BAIXA"],
        "average_opportunity_score": _average([item.opportunity_score for item in records]),
        "average_confidence_score": _average([item.confidence_score for item in records]),
        "category_counts": category_counts
    }


def _average(values: list[int]) -> float | None:
    return round(sum(values) / len(values), 2) if values else None


def _write_jsonl(path: Path, rows: Any) -> None:
    with path.open("x", encoding="utf-8") as output:
        for row in rows:
            output.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")))
            output.write("\n")


def _write_json(path: Path, document: dict[str, Any]) -> None:
    with path.open("x", encoding="utf-8") as output:
        json.dump(document, output, ensure_ascii=False, indent=2)
        output.write("\n")


def _relative_path(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _required_string(record: dict[str, Any], key: str) -> str:
    value = record.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{key} é obrigatório no Silver")
    return value


def _optional_string(record: dict[str, Any], key: str) -> str | None:
    value = record.get(key)
    return value if isinstance(value, str) else None


def _optional_number(record: dict[str, Any], key: str) -> float | None:
    value = record.get(key)
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None
