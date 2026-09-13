from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from src.opportunity.benchmark import evaluate_golden_cases
from src.opportunity.engine import build_gold, build_opportunity, load_rules


RULES_PATH = Path("config/opportunity_rules.json")


def silver_record() -> dict[str, object]:
    return {"source": "PNCP", "source_record_id": "123-1-000001/2026", "source_files": ["data/bronze/a.json"], "orgao_nome": "Órgão", "orgao_cnpj": "123", "unidade_nome": "Unidade", "municipio": "São Paulo", "uf": "SP", "objeto_compra": "Reforma de refeitório escolar", "data_publicacao": "2026-09-10T10:00:00", "data_abertura_proposta": "2026-09-11T10:00:00", "data_encerramento_proposta": "2026-09-20T10:00:00", "valor_total_estimado": 100000.0}


def test_opportunity_id_is_deterministic_and_has_lineage() -> None:
    rules = load_rules(RULES_PATH)
    first = build_opportunity(silver_record(), "data/silver/a.jsonl", date(2026, 9, 12), "2026-09-12T12:00:00+00:00", rules)
    second = build_opportunity(silver_record(), "data/silver/a.jsonl", date(2026, 9, 12), "2026-09-12T13:00:00+00:00", rules)
    assert first.opportunity_id == second.opportunity_id
    assert first.source_bronze_files == ("data/bronze/a.json",)
    assert "INFRASTRUCTURE_MATCH" in first.reason_codes


def test_gold_jsonl_and_manifest(tmp_path: Path) -> None:
    silver_dir = tmp_path / "silver"
    silver_dir.mkdir()
    (silver_dir / "input.jsonl").write_text(json.dumps(silver_record()) + "\n", encoding="utf-8")
    result = build_gold(silver_dir, tmp_path / "gold", tmp_path, RULES_PATH, date(2026, 9, 12))
    manifest = json.loads(result.manifest_file.read_text(encoding="utf-8"))
    assert result.gold_file.read_text(encoding="utf-8").count("\n") == 1
    assert manifest["input_record_count"] == 1
    assert manifest["high_relevance_count"] == 1


def test_golden_cases_have_metrics() -> None:
    report = evaluate_golden_cases(Path("tests/fixtures/golden_opportunity_cases.json"), RULES_PATH, date(2026, 9, 12))
    assert report["case_count"] == 10
    assert report["accuracy_relevance"] == 1.0
    assert report["precision_relevant"] == 1.0
    assert report["recall_relevant"] == 1.0
    assert report["category_exact_accuracy"] == 1.0
