from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from src.api.app import create_app


def record(identifier: str, **overrides: object) -> dict[str, object]:
    base: dict[str, object] = {"opportunity_id": identifier, "source": "PNCP", "source_record_id": identifier, "orgao_nome": "Escola Estadual", "orgao_cnpj": "123", "unidade_nome": "Unidade Centro", "municipio": "São Paulo", "uf": "SP", "objeto_original": "Reforma de refeitório escolar", "categories": ["REFEITORIO", "INFRAESTRUTURA"], "matched_terms": [{"term": "refeitório", "category": "REFEITORIO"}], "negative_matches": [], "relevance": "ALTA", "temporal_status": "ATIVA", "data_publicacao": "2026-09-10T00:00:00", "data_abertura_proposta": "2026-09-11T00:00:00", "data_encerramento_proposta": "2026-09-20T00:00:00", "valor_total_estimado": 100000.0, "opportunity_score": 60, "confidence_score": 80, "score_breakdown": {"fit_product": {"points": 35}}, "reason_codes": ["REFEITORY_MATCH"], "source_silver_file": "data/silver/input.jsonl", "source_bronze_files": ["data/bronze/input.json"], "rules_version": "0.1.1", "generated_at": "2026-09-12T00:00:00+00:00"}
    base.update(overrides)
    return base


def client(tmp_path: Path) -> TestClient:
    (tmp_path / "opportunities_test.jsonl").write_text("\n".join(json.dumps(item) for item in [record("a"), record("b", orgao_nome="Hospital Municipal", municipio="Campinas", uf="SP", categories=["REFRIGERACAO"], relevance="MEDIA", temporal_status="FUTURA", opportunity_score=40, confidence_score=65)]) + "\n", encoding="utf-8")
    return TestClient(create_app(tmp_path))


def test_health_and_stats(tmp_path: Path) -> None:
    api = client(tmp_path)
    assert api.get("/health").json() == {"status": "ok"}
    response = api.get("/stats")
    assert response.status_code == 200
    assert response.json()["total_gold"] == 2
    assert response.json()["high"] == 1


def test_opportunities_filters_pagination_search_and_ordering(tmp_path: Path) -> None:
    api = client(tmp_path)
    assert api.get("/opportunities", params={"page_size": 1}).json()["items"][0]["opportunity_id"] == "a"
    assert api.get("/opportunities", params={"q": "hospital"}).json()["total"] == 1
    assert api.get("/opportunities", params={"uf": "sp", "municipio": "camp", "category": "REFRIGERACAO", "relevance": "MEDIA", "temporal_status": "FUTURA", "min_score": 40, "min_confidence": 65}).json()["items"][0]["opportunity_id"] == "b"


def test_detail_evidence_and_not_found(tmp_path: Path) -> None:
    api = client(tmp_path)
    assert api.get("/opportunities/a").status_code == 200
    evidence = api.get("/opportunities/a/evidence")
    assert evidence.status_code == 200
    assert evidence.json()["lineage"]["source_bronze_files"] == ["data/bronze/input.json"]
    assert api.get("/opportunities/missing").status_code == 404
