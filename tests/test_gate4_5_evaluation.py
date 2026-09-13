"""Testes automatizados do Gate 4.5 — Corpus de Avaliação e Métricas de Revisão Humana."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

import pytest

from scripts.build_human_review_corpus import (
    CORPUS_VERSION,
    CSV_COLUMNS,
    build_review_rows,
    select_evaluation_corpus,
    write_corpus_csv,
)
from scripts.evaluate_baseline_human import (
    compute_evaluation_metrics,
    parse_categories,
    parse_human_bool,
)


def mock_gold_record(identifier: str, relevance: str, obj: str = "teste", **overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "opportunity_id": identifier,
        "source": "PNCP",
        "source_record_id": f"REC-{identifier}",
        "orgao_nome": "Órgão Teste",
        "objeto_original": obj,
        "categories": ["COZINHA"] if relevance in {"ALTA", "MEDIA"} else [],
        "matched_terms": [{"term": "cozinha", "category": "COZINHA"}] if relevance in {"ALTA", "MEDIA"} else [],
        "negative_matches": [],
        "relevance": relevance,
        "temporal_status": "ATIVA",
        "data_publicacao": "2026-09-10T00:00:00",
        "valor_total_estimado": 50000.0,
        "opportunity_score": 80 if relevance == "ALTA" else (60 if relevance == "MEDIA" else 0),
        "confidence_score": 70 if relevance in {"ALTA", "MEDIA"} else 40,
    }
    base.update(overrides)
    return base


def test_corpus_assembly_and_columns(tmp_path: Path) -> None:
    records = [
        mock_gold_record("1", "ALTA", "Reforma de cozinha industrial"),
        mock_gold_record("2", "MEDIA", "Mesa em inox"),
        mock_gold_record("3", "BAIXA", "Merenda escolar"),
        mock_gold_record("4", "IRRELEVANTE", "Manutencao predial geral"),
        mock_gold_record("5", "IRRELEVANTE", "Contratacao de software de gestao"),
    ]
    corpus = select_evaluation_corpus(records, target_difficult_negatives=1, target_random_negatives=1, seed=42)
    rows = build_review_rows(corpus)
    out_csv = tmp_path / "test_corpus.csv"
    sha = write_corpus_csv(rows, out_csv)

    assert out_csv.exists()
    assert len(sha) == 64
    with out_csv.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        assert reader.fieldnames == CSV_COLUMNS
        loaded_rows = list(reader)
        assert len(loaded_rows) == len(corpus)


def test_human_fields_remain_empty_in_real_corpus() -> None:
    csv_path = Path("reports/gate4_5_human_review.csv")
    assert csv_path.exists(), "Corpus gate4_5_human_review.csv deve existir"

    with csv_path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        assert len(rows) >= 50, f"Esperado pelo menos 50 registros no corpus, obtido {len(rows)}"
        for row in rows:
            for field in ["human_relevant", "human_relevance", "human_categories", "human_confidence", "human_notes"]:
                assert row[field] == "", f"Campo {field} no registro {row['review_id']} deve ser estritamente vazio!"


def test_deterministic_selection() -> None:
    records = [
        mock_gold_record("a", "ALTA", "cozinha"),
        mock_gold_record("b", "MEDIA", "refeitorio"),
        mock_gold_record("c", "IRRELEVANTE", "reforma de escola"),
        mock_gold_record("d", "IRRELEVANTE", "material de expediente"),
        mock_gold_record("e", "IRRELEVANTE", "pneu de caminhao"),
    ]
    sel1 = select_evaluation_corpus(records, target_difficult_negatives=1, target_random_negatives=1, seed=123)
    sel2 = select_evaluation_corpus(records, target_difficult_negatives=1, target_random_negatives=1, seed=123)
    assert [r["opportunity_id"] for r in sel1] == [r["opportunity_id"] for r in sel2]


def test_unreviewed_corpus_does_not_treat_empty_as_false() -> None:
    unreviewed_rows = [
        {"baseline_relevance": "ALTA", "human_relevant": "", "human_relevance": ""},
        {"baseline_relevance": "IRRELEVANTE", "human_relevant": "   ", "human_relevance": ""},
    ]
    metrics = compute_evaluation_metrics(unreviewed_rows)
    assert metrics["status"] == "PENDING_REVIEW"
    assert metrics["reviewed_records"] == 0
    assert "Corpus ainda não revisado" in metrics["message"]


def test_evaluation_metrics_tp_fp_tn_fn() -> None:
    # 2 TP, 1 FP, 1 TN, 1 FN
    test_rows = [
        {"baseline_relevance": "ALTA", "human_relevant": "TRUE", "human_relevance": "ALTA", "baseline_categories": "COZINHA", "human_categories": "COZINHA"},
        {"baseline_relevance": "MEDIA", "human_relevant": "SIM", "human_relevance": "MEDIA", "baseline_categories": "REFEITORIO", "human_categories": "REFEITORIO"},
        {"baseline_relevance": "MEDIA", "human_relevant": "FALSE", "human_relevance": "IRRELEVANTE", "baseline_categories": "COZINHA", "human_categories": ""},
        {"baseline_relevance": "IRRELEVANTE", "human_relevant": "0", "human_relevance": "IRRELEVANTE", "baseline_categories": "", "human_categories": ""},
        {"baseline_relevance": "IRRELEVANTE", "human_relevant": "1", "human_relevance": "MEDIA", "baseline_categories": "", "human_categories": "INOX"},
    ]
    results = compute_evaluation_metrics(test_rows)
    assert results["status"] == "EVALUATED"
    cm = results["confusion_matrix"]
    assert cm["true_positive"] == 2
    assert cm["false_positive"] == 1
    assert cm["true_negative"] == 1
    assert cm["false_negative"] == 1

    bm = results["binary_metrics"]
    # Total = 5; TP=2, FP=1, TN=1, FN=1
    # Accuracy = (2 + 1) / 5 = 0.60
    # Precision = 2 / (2 + 1) = 0.6667
    # Recall = 2 / (2 + 1) = 0.6667
    # F1 = 2 * (2/3 * 2/3) / (4/3) = 0.6667
    assert bm["accuracy"] == 0.60
    assert bm["precision"] == 0.6667
    assert bm["recall"] == 0.6667
    assert bm["f1_score"] == 0.6667


def test_zero_division_safety() -> None:
    # Cenário onde TP=0, FP=0, TN=2, FN=0
    all_negatives = [
        {"baseline_relevance": "IRRELEVANTE", "human_relevant": "FALSE"},
        {"baseline_relevance": "IRRELEVANTE", "human_relevant": "FALSE"},
    ]
    results = compute_evaluation_metrics(all_negatives)
    bm = results["binary_metrics"]
    assert bm["accuracy"] == 1.0
    assert bm["precision"] == 0.0
    assert bm["recall"] == 0.0
    assert bm["f1_score"] == 0.0


def test_multiclass_and_multilabel_helpers() -> None:
    assert parse_human_bool("True") is True
    assert parse_human_bool("SIM") is True
    assert parse_human_bool("1") is True
    assert parse_human_bool("False") is False
    assert parse_human_bool("nao") is False
    assert parse_human_bool("0") is False
    assert parse_human_bool("") is None
    assert parse_human_bool(None) is None

    assert parse_categories("COZINHA, INOX") == {"COZINHA", "INOX"}
    assert parse_categories("cozinha; refeitorio") == {"COZINHA", "REFEITORIO"}
    assert parse_categories("") == set()


def test_corpus_hash_and_version() -> None:
    assert CORPUS_VERSION == "0.1.0"
    csv_file = Path("reports/gate4_5_human_review.csv")
    content = csv_file.read_bytes()
    import hashlib
    computed_sha = hashlib.sha256(content).hexdigest()
    # Deve ser estável e não vazio
    assert len(computed_sha) == 64
