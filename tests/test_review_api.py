"""Testes automatizados da API de revisão humana e imutabilidade do corpus (Gate 4.6)."""

from __future__ import annotations

import csv
import hashlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.api.app import create_app
from src.api.review_repository import ReviewRepository, VALID_CATEGORIES


@pytest.fixture
def real_client() -> TestClient:
    app = create_app()
    return TestClient(app)


@pytest.fixture
def temp_review_setup(tmp_path: Path):
    corpus_file = tmp_path / "test_corpus.csv"
    annotations_file = tmp_path / "test_annotations.csv"

    # Criar corpus sintético com 2 itens
    corpus_headers = [
        "review_id",
        "evaluation_corpus_version",
        "source",
        "source_record_id",
        "orgao_nome",
        "unidade_nome",
        "municipio",
        "uf",
        "objeto_original",
        "valor_total_estimado",
        "data_publicacao",
        "baseline_relevance",
        "baseline_categories",
        "baseline_score",
        "baseline_confidence",
    ]
    corpus_rows = [
        {
            "review_id": "REV-0001",
            "evaluation_corpus_version": "0.1.0",
            "source": "PNCP",
            "source_record_id": "11111111000100-1-000001/2026",
            "orgao_nome": "Hospital Regional",
            "unidade_nome": "Nutrição",
            "municipio": "São Paulo",
            "uf": "SP",
            "objeto_original": "Aquisição de fogão industrial e coifa inox",
            "valor_total_estimado": "150000.00",
            "data_publicacao": "2026-09-10T10:00:00",
            "baseline_relevance": "ALTA",
            "baseline_categories": "COZINHA, COCCAO, INOX, EXAUSTAO",
            "baseline_score": "85",
            "baseline_confidence": "80",
        },
        {
            "review_id": "REV-0002",
            "evaluation_corpus_version": "0.1.0",
            "source": "PNCP",
            "source_record_id": "22222222000100-1-000002/2026",
            "orgao_nome": "Prefeitura Municipal",
            "unidade_nome": "Educação",
            "municipio": "Campinas",
            "uf": "SP",
            "objeto_original": "Manutenção de carteiras escolares de madeira",
            "valor_total_estimado": "25000.00",
            "data_publicacao": "2026-09-10T11:00:00",
            "baseline_relevance": "IRRELEVANTE",
            "baseline_categories": "",
            "baseline_score": "0",
            "baseline_confidence": "50",
        },
    ]
    with corpus_file.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=corpus_headers)
        writer.writeheader()
        writer.writerows(corpus_rows)

    # Criar arquivo de anotações vazio
    ann_headers = [
        "review_id",
        "source_record_id",
        "human_relevant",
        "human_relevance",
        "human_categories",
        "human_confidence",
        "human_notes",
        "reviewed_at",
    ]
    ann_rows = [
        {
            "review_id": "REV-0001",
            "source_record_id": "11111111000100-1-000001/2026",
            "human_relevant": "",
            "human_relevance": "",
            "human_categories": "",
            "human_confidence": "",
            "human_notes": "",
            "reviewed_at": "",
        },
        {
            "review_id": "REV-0002",
            "source_record_id": "22222222000100-1-000002/2026",
            "human_relevant": "",
            "human_relevance": "",
            "human_categories": "",
            "human_confidence": "",
            "human_notes": "",
            "reviewed_at": "",
        },
    ]
    with annotations_file.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=ann_headers)
        writer.writeheader()
        writer.writerows(ann_rows)

    app = create_app(corpus_path=corpus_file, annotations_path=annotations_file)
    client = TestClient(app)
    return client, corpus_file, annotations_file


def test_get_review_summary_real_dataset(real_client: TestClient) -> None:
    resp = real_client.get("/review")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 76
    assert data["reviewed"] == 76
    assert data["pending"] == 0
    assert data["progress_percent"] == 100.0
    assert len(data["items"]) == 76
    first = data["items"][0]
    assert first["review_id"] == "REV-001"
    assert first["is_reviewed"] is True
    assert first["reviewed_at"] is not None


def test_get_review_detail_and_not_found(real_client: TestClient) -> None:
    resp = real_client.get("/review/REV-001")
    assert resp.status_code == 200
    detail = resp.json()
    assert detail["review_id"] == "REV-001"
    assert "objeto_original" in detail
    assert "baseline" in detail
    assert "human" in detail
    assert detail["human"]["is_reviewed"] is True

    resp404 = real_client.get("/review/REV-9999")
    assert resp404.status_code == 404


def test_get_review_export_csv(real_client: TestClient) -> None:
    resp = real_client.get("/review/export")
    assert resp.status_code == 200
    assert "text/csv" in resp.headers.get("content-type", "")
    lines = resp.text.strip().split("\r\n") if "\r\n" in resp.text else resp.text.strip().split("\n")
    assert lines[0].startswith("review_id,source_record_id")
    # 1 header + 76 registros
    assert len(lines) == 77


def test_save_annotation_and_corpus_immutability(temp_review_setup) -> None:
    client, corpus_file, annotations_file = temp_review_setup

    corpus_sha_before = hashlib.sha256(corpus_file.read_bytes()).hexdigest()

    payload = {
        "human_relevant": True,
        "human_relevance": "ALTA",
        "human_categories": ["COZINHA", "COCCAO", "INOX"],
        "human_confidence": 5,
        "human_notes": "Equipamento pesado de cocção central para cozinha hospitalar.",
    }
    resp = client.put("/review/REV-0001", json=payload)
    assert resp.status_code == 200
    updated = resp.json()
    assert updated["human"]["is_reviewed"] is True
    assert updated["human"]["human_relevant"] is True
    assert updated["human"]["human_relevance"] == "ALTA"
    assert set(updated["human"]["human_categories"]) == {"COZINHA", "COCCAO", "INOX"}
    assert updated["human"]["human_confidence"] == 5
    assert updated["human"]["human_notes"] == "Equipamento pesado de cocção central para cozinha hospitalar."
    assert updated["human"]["reviewed_at"] is not None

    # CRÍTICO: Verificar que o corpus de avaliação permaneceu 100% IMUTÁVEL
    corpus_sha_after = hashlib.sha256(corpus_file.read_bytes()).hexdigest()
    assert corpus_sha_before == corpus_sha_after, "O corpus de avaliação JAMAIS pode ser alterado por uma anotação!"

    # Verificar que a alteração foi persistida no arquivo de anotações
    with annotations_file.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        saved_rows = list(reader)
        row1 = next(r for r in saved_rows if r["review_id"] == "REV-0001")
        assert row1["human_relevant"] == "TRUE"
        assert row1["human_relevance"] == "ALTA"
        assert "COZINHA" in row1["human_categories"]
        assert row1["human_confidence"] == "5"


def test_validation_errors(temp_review_setup) -> None:
    client, _, _ = temp_review_setup

    # Categoria inválida -> 422
    bad_cat = {
        "human_relevant": True,
        "human_relevance": "ALTA",
        "human_categories": ["COZINHA", "CATEGORIA_INEXISTENTE"],
        "human_confidence": 5,
    }
    resp = client.put("/review/REV-0001", json=bad_cat)
    assert resp.status_code == 422
    assert "Categorias inválidas" in resp.text

    # Relevância inválida -> 422
    bad_rel = {
        "human_relevant": True,
        "human_relevance": "SUPER_ALTA",
        "human_categories": ["COZINHA"],
        "human_confidence": 5,
    }
    resp2 = client.put("/review/REV-0001", json=bad_rel)
    assert resp2.status_code == 422

    # Confiança fora do intervalo (1..5) -> 422
    bad_conf = {
        "human_relevant": True,
        "human_relevance": "ALTA",
        "human_categories": ["COZINHA"],
        "human_confidence": 10,
    }
    resp3 = client.put("/review/REV-0001", json=bad_conf)
    assert resp3.status_code == 422

    # review_id inexistente -> 404
    resp4 = client.put("/review/REV-9999", json={
        "human_relevant": False,
        "human_relevance": "IRRELEVANTE",
        "human_categories": [],
        "human_confidence": 5,
    })
    assert resp4.status_code == 404
