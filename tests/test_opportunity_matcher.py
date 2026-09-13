from __future__ import annotations

from pathlib import Path

from src.opportunity.classifier import classify_text
from src.opportunity.engine import load_rules
from src.opportunity.matcher import normalize_for_matching


RULES = load_rules(Path("config/opportunity_rules.json"))


def test_normalization_removes_accents_case_and_punctuation() -> None:
    assert normalize_for_matching("Construção de Cozinha e Refeitório!") == "construcao de cozinha e refeitorio"


def test_multiple_categories_and_infrastructure_action() -> None:
    result = classify_text("Construção de cozinha e refeitório", RULES)
    assert result["relevance"] == "ALTA"
    assert set(result["categories"]) == {"COZINHA", "REFEITORIO", "INFRAESTRUTURA"}


def test_negative_context_blocks_commercial_categories() -> None:
    result = classify_text("Exaustor automotivo", RULES)
    assert result["relevance"] == "IRRELEVANTE"
    assert result["categories"] == ()
    assert result["negative_matches"][0]["term"] == "exaustor automotivo"


def test_no_match_is_irrelevant_and_explained() -> None:
    result = classify_text("Compra de computadores", RULES)
    assert result["relevance"] == "IRRELEVANTE"
    assert "NO_DOMAIN_MATCH" in result["reason_codes"]
