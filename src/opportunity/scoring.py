"""Scores explicáveis e separados para o baseline do Gate 3."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any


def temporal_status(record: dict[str, Any], as_of: date) -> tuple[str, list[str]]:
    """Calcula situação temporal apenas com datas Silver disponíveis."""
    opening = _date_part(record.get("data_abertura_proposta"))
    closing = _date_part(record.get("data_encerramento_proposta"))
    if opening and as_of < opening:
        return "FUTURA", ["FUTURE_PROCUREMENT"]
    if closing and as_of > closing:
        return "ENCERRADA", ["CLOSED_PROCUREMENT"]
    if opening or closing:
        return "ATIVA", ["ACTIVE_PROCUREMENT"]
    return "INDETERMINADA", ["TEMPORAL_STATUS_UNAVAILABLE"]


def score_opportunity(
    record: dict[str, Any], classification: dict[str, Any], as_of: date, rules: dict[str, Any]
) -> tuple[int, dict[str, dict[str, Any]], list[str]]:
    """Calcula apenas componentes suportados por Silver e regras atuais."""
    reasons: list[str] = []
    relevance = classification["relevance"]
    product_points = rules["score_weights"]["fit_product"][relevance]
    breakdown: dict[str, dict[str, Any]] = {
        "fit_product": _component(product_points, 35, "available", list(classification["categories"])),
        "fit_segment": _component(None, 10, "not_available", ["segmento institucional não inferido no Gate 3"]),
    }
    if classification["categories"]:
        reasons.append("PRODUCT_FIT_EVALUATED")

    if record.get("source") == "PNCP":
        purchase_points = rules["score_weights"]["purchase_signal"]
        breakdown["purchase_signal"] = _component(purchase_points, 25, "available", ["source=PNCP"])
        reasons.append("PUBLIC_PROCUREMENT_SIGNAL")
    else:
        breakdown["purchase_signal"] = _component(None, 25, "not_available", ["fonte não suportada"])

    publication = _date_part(record.get("data_publicacao"))
    if publication:
        age_days = max((as_of - publication).days, 0)
        points = _band_points(age_days, rules["score_weights"]["recency_bands_days"])
        breakdown["recency"] = _component(points, 15, "available", [f"idade_dias={age_days}"])
        if points == 15:
            reasons.append("RECENT_PUBLICATION")
    else:
        breakdown["recency"] = _component(None, 15, "not_available", ["data_publicacao ausente"])

    value = record.get("valor_total_estimado")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        points = _ticket_points(float(value), rules["score_weights"]["ticket_bands"])
        breakdown["ticket"] = _component(points, 15, "available", [f"valor_total_estimado={value}"])
        if points == 15:
            reasons.append("HIGH_ESTIMATED_VALUE")
    else:
        breakdown["ticket"] = _component(None, 15, "not_available", ["valor_total_estimado ausente"])

    raw_total = sum(int(component["points"]) for component in breakdown.values() if component["points"] is not None)
    if relevance == "IRRELEVANTE":
        breakdown["domain_eligibility"] = _component(0, 0, "available", ["relevance=IRRELEVANTE bloqueia priorização comercial"])
        reasons.append("IRRELEVANT_DOMAIN_GATE")
        return 0, breakdown, reasons
    breakdown["domain_eligibility"] = _component(None, 0, "not_applicable", ["registro relevante para o domínio"])
    total = raw_total
    return total, breakdown, reasons


def score_confidence(record: dict[str, Any], classification: dict[str, Any], rules: dict[str, Any]) -> tuple[int, list[str]]:
    """Mede confiança da interpretação lexical, não atratividade comercial."""
    config = rules["confidence"]
    points = config["base"]
    reasons = ["CONFIDENCE_BASELINE"]
    terms = {item["term"] for item in classification["matched_terms"]}
    if terms & set(rules["strong_direct_terms"]):
        points += config["direct_strong_match"]
        reasons.append("EXACT_STRONG_MATCH")
    elif len(classification["categories"]) >= 2:
        points += config["multiple_categories"]
        reasons.append("MULTIPLE_CATEGORY_MATCH")
    elif classification["categories"]:
        points += config["single_strong_category"]
        reasons.append("SINGLE_CATEGORY_MATCH")
    if record.get("source_record_id") and record.get("objeto_compra"):
        points += config["required_identity_and_object"]
        reasons.append("REQUIRED_FIELDS_PRESENT")
    if record.get("valor_total_estimado") is not None:
        points += config["value_present"]
        reasons.append("VALUE_PRESENT")
    if record.get("data_publicacao") and record.get("data_encerramento_proposta"):
        points += config["dates_present"]
        reasons.append("DATES_PRESENT")
    if classification["negative_matches"]:
        points += config["negative_context"]
        reasons.append("NEGATIVE_CONTEXT_RECOGNIZED")
        if classification["matched_terms"]:
            points -= config["positive_negative_conflict_penalty"]
            reasons.append("POSITIVE_NEGATIVE_CONFLICT")
    return max(0, min(100, points)), reasons


def _component(points: int | None, maximum: int, status: str, evidence: list[str]) -> dict[str, Any]:
    return {"points": points, "maximum": maximum, "status": status, "evidence": evidence}


def _date_part(value: Any) -> date | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def _band_points(value: int, bands: list[list[int]]) -> int:
    for limit, points in bands:
        if value <= limit:
            return points
    return 0


def _ticket_points(value: float, bands: list[list[int]]) -> int:
    for threshold, points in bands:
        if value >= threshold:
            return points
    return 0
