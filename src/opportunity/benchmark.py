"""Benchmark pequeno e determinístico para o baseline do Gate 3."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from src.opportunity.classifier import classify_text
from src.opportunity.engine import load_rules
from src.opportunity.scoring import score_confidence, score_opportunity, temporal_status


def evaluate_golden_cases(cases_path: Path, rules_path: Path, as_of: date) -> dict[str, Any]:
    rules = load_rules(rules_path)
    cases = json.loads(cases_path.read_text(encoding="utf-8"))
    details: list[dict[str, Any]] = []
    correct_relevance = correct_categories = true_positive = false_positive = false_negative = 0
    for case in cases:
        classification = classify_text(case["text"], rules)
        predicted_relevant = classification["relevance"] != "IRRELEVANTE"
        expected_relevant = case["expected_relevance"] != "IRRELEVANTE"
        if classification["relevance"] == case["expected_relevance"]:
            correct_relevance += 1
        if list(classification["categories"]) == sorted(case["expected_categories"]):
            correct_categories += 1
        if predicted_relevant and expected_relevant:
            true_positive += 1
        elif predicted_relevant and not expected_relevant:
            false_positive += 1
        elif not predicted_relevant and expected_relevant:
            false_negative += 1
        synthetic = {"source": "PNCP", "source_record_id": case["name"], "objeto_compra": case["text"], "data_publicacao": as_of.isoformat(), "data_encerramento_proposta": as_of.isoformat(), "valor_total_estimado": 0}
        status, _ = temporal_status(synthetic, as_of)
        opportunity_score, _, _ = score_opportunity(synthetic, classification, as_of, rules)
        confidence_score, _ = score_confidence(synthetic, classification, rules)
        details.append({"name": case["name"], "expected_relevance": case["expected_relevance"], "predicted_relevance": classification["relevance"], "expected_categories": case["expected_categories"], "predicted_categories": list(classification["categories"]), "temporal_status": status, "opportunity_score": opportunity_score, "confidence_score": confidence_score})
    count = len(cases)
    precision = true_positive / (true_positive + false_positive) if true_positive + false_positive else 0.0
    recall = true_positive / (true_positive + false_negative) if true_positive + false_negative else 0.0
    return {"rules_version": rules["rules_version"], "case_count": count, "accuracy_relevance": round(correct_relevance / count, 4), "precision_relevant": round(precision, 4), "recall_relevant": round(recall, 4), "category_exact_accuracy": round(correct_categories / count, 4), "confusion": {"true_positive": true_positive, "false_positive": false_positive, "false_negative": false_negative}, "cases": details}


def write_benchmark_report(report: dict[str, Any], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
