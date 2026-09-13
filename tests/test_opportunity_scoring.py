from __future__ import annotations

from datetime import date
from pathlib import Path

from src.opportunity.classifier import classify_text
from src.opportunity.engine import load_rules
from src.opportunity.scoring import score_confidence, score_opportunity, temporal_status


RULES = load_rules(Path("config/opportunity_rules.json"))


def record(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {"source": "PNCP", "source_record_id": "id", "objeto_compra": "cozinha industrial", "data_publicacao": "2026-09-10T10:00:00", "data_abertura_proposta": "2026-09-11T10:00:00", "data_encerramento_proposta": "2026-09-20T10:00:00", "valor_total_estimado": 600000.0}
    base.update(overrides)
    return base


def test_temporal_status_active_future_and_closed() -> None:
    assert temporal_status(record(), date(2026, 9, 12))[0] == "ATIVA"
    assert temporal_status(record(data_abertura_proposta="2026-09-20T10:00:00"), date(2026, 9, 12))[0] == "FUTURA"
    assert temporal_status(record(data_encerramento_proposta="2026-09-01T10:00:00"), date(2026, 9, 12))[0] == "ENCERRADA"


def test_score_is_explicit_and_fit_segment_is_not_available() -> None:
    classification = classify_text("cozinha industrial", RULES)
    score, breakdown, reasons = score_opportunity(record(), classification, date(2026, 9, 12), RULES)
    assert score == 90
    assert breakdown["fit_segment"]["status"] == "not_available"
    assert breakdown["ticket"]["points"] == 15
    assert "RECENT_PUBLICATION" in reasons


def test_confidence_is_not_opportunity_score() -> None:
    classification = classify_text("cozinha industrial", RULES)
    confidence, reasons = score_confidence(record(), classification, RULES)
    assert confidence == 80
    assert "EXACT_STRONG_MATCH" in reasons


def test_irrelevant_domain_is_not_prioritized_despite_public_procurement() -> None:
    classification = classify_text("Compra de computadores", RULES)
    score, breakdown, reasons = score_opportunity(record(objeto_compra="Compra de computadores"), classification, date(2026, 9, 12), RULES)
    assert score == 0
    assert breakdown["purchase_signal"]["points"] == 25
    assert "IRRELEVANT_DOMAIN_GATE" in reasons
