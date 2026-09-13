"""Matching lexical explicável, sem alteração do texto original."""

from __future__ import annotations

import re
import unicodedata
from typing import Any


def normalize_for_matching(text: str | None) -> str:
    """Remove acentos, caixa e pontuação apenas para comparação lexical."""
    if not text:
        return ""
    decomposed = unicodedata.normalize("NFD", text.lower())
    without_accents = "".join(char for char in decomposed if unicodedata.category(char) != "Mn")
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", without_accents)).strip()


def find_category_matches(text: str | None, rules: dict[str, Any]) -> list[dict[str, str]]:
    normalized_text = normalize_for_matching(text)
    matches: list[dict[str, str]] = []
    for category, terms in rules["categories"].items():
        for term in terms:
            if _contains(normalized_text, normalize_for_matching(term)):
                matches.append({"term": term, "category": category})
    return matches


def find_negative_matches(text: str | None, rules: dict[str, Any]) -> list[dict[str, str]]:
    normalized_text = normalize_for_matching(text)
    matches: list[dict[str, str]] = []
    for rule in rules["negative_terms"]:
        if _contains(normalized_text, normalize_for_matching(rule["term"])):
            matches.append({"term": rule["term"], "reason_code": rule["reason_code"]})
    return matches


def find_infrastructure_actions(text: str | None, rules: dict[str, Any]) -> list[str]:
    normalized_text = normalize_for_matching(text)
    return [term for term in rules["infrastructure_action_terms"] if _contains(normalized_text, normalize_for_matching(term))]


def _contains(text: str, term: str) -> bool:
    return bool(term) and bool(re.search(rf"(?<!\w){re.escape(term)}(?!\w)", text))
