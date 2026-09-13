"""Classificação determinística de categorias e relevância."""

from __future__ import annotations

from typing import Any

from src.opportunity.matcher import find_category_matches, find_infrastructure_actions, find_negative_matches


CATEGORY_REASON_CODES = {
    "COZINHA": "DIRECT_KITCHEN_MATCH",
    "REFEITORIO": "REFEITORY_MATCH",
    "INOX": "INOX_MATCH",
    "COCCAO": "COOKING_EQUIPMENT_MATCH",
    "REFRIGERACAO": "REFRIGERATION_MATCH",
    "EXAUSTAO": "EXHAUST_MATCH",
    "LAVAGEM": "WASHING_MATCH",
    "INFRAESTRUTURA": "INFRASTRUCTURE_MATCH",
    "ALIMENTACAO_COLETIVA": "COLLECTIVE_FEEDING_MATCH"
}


def classify_text(text: str | None, rules: dict[str, Any]) -> dict[str, Any]:
    """Classifica texto por regras explícitas e retorna suas evidências."""
    matches = find_category_matches(text, rules)
    negatives = find_negative_matches(text, rules)
    categories = {match["category"] for match in matches}
    actions = find_infrastructure_actions(text, rules)
    if actions and categories - {"INFRAESTRUTURA"} and not negatives:
        categories.add("INFRAESTRUTURA")
        matches.extend({"term": action, "category": "INFRAESTRUTURA"} for action in actions)

    # O termo positivo continua auditável em matched_terms, mas contexto negativo
    # explícito impede atribuição comercial de categoria neste baseline.
    if negatives:
        categories = set()

    ordered_categories = tuple(sorted(categories))
    relevance = _relevance(ordered_categories, matches, negatives, rules)
    reason_codes = {CATEGORY_REASON_CODES[category] for category in ordered_categories}
    reason_codes.update(match["reason_code"] for match in negatives)
    if relevance == "BAIXA":
        reason_codes.add("INDIRECT_DOMAIN_MATCH")
    if not matches:
        reason_codes.add("NO_DOMAIN_MATCH")
    return {
        "categories": ordered_categories,
        "matched_terms": tuple(matches),
        "negative_matches": tuple(negatives),
        "relevance": relevance,
        "reason_codes": tuple(sorted(reason_codes)),
    }


def _relevance(categories: tuple[str, ...], matches: list[dict[str, str]], negatives: list[dict[str, str]], rules: dict[str, Any]) -> str:
    if negatives:
        return "IRRELEVANTE"
    direct_terms = set(rules["strong_direct_terms"])
    if any(match["term"] in direct_terms for match in matches):
        return "ALTA"
    category_set = set(categories)
    if "INFRAESTRUTURA" in category_set and len(category_set) >= 2:
        return "ALTA"
    if {"COZINHA", "REFEITORIO"}.issubset(category_set):
        return "ALTA"
    if category_set & {"INOX", "COCCAO", "REFRIGERACAO", "EXAUSTAO", "LAVAGEM"}:
        return "MEDIA"
    if category_set == {"COZINHA"} or category_set == {"REFEITORIO"}:
        return "MEDIA"
    if category_set:
        return "BAIXA"
    return "IRRELEVANTE"
