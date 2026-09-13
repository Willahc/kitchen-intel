"""Testes automatizados para o Development Set e Blind Review (Gate 5D).

Valida:
1. Schema do corpus DEV (reports/development_corpus_v0.1.0.csv)
2. Unicidade de source_record_id no DEV
3. Unicidade e formato dos IDs (DEV-001 a DEV-120)
4. Zero overlap absoluto com o Test Set (evaluation_corpus_v0.1.0.csv)
5. Schema do arquivo de anotações (reports/development_annotations_v0.1.0.csv)
6. Endpoints de Blind Review na API (/review/dev, /review/dev/{id}, /review/dev/export)
7. Ausência total de predições de modelo / scores no payload de detalhe do DEV (blind review)
8. Integridade do hash SHA-256 e metadados de congelamento (manifest)
9. Janela temporal estritamente posterior ao Test Set (> 2026-09-11T08:30:06)
"""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.api.app import create_app

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEV_CORPUS_PATH = PROJECT_ROOT / "reports" / "development_corpus_v0.1.0.csv"
DEV_ANNOTATIONS_PATH = PROJECT_ROOT / "reports" / "development_annotations_v0.1.0.csv"
DEV_MANIFEST_PATH = PROJECT_ROOT / "reports" / "development_corpus_v0.1.0.manifest.json"
TEST_CORPUS_PATH = PROJECT_ROOT / "reports" / "evaluation_corpus_v0.1.0.csv"


def test_dev_corpus_schema():
    """Valida existência, contagem e colunas obrigatórias do corpus DEV."""
    assert DEV_CORPUS_PATH.exists(), f"Arquivo DEV não encontrado: {DEV_CORPUS_PATH}"

    with DEV_CORPUS_PATH.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        expected_fields = [
            "review_id",
            "source_record_id",
            "objeto_original",
            "orgao_nome",
            "unidade_nome",
            "municipio",
            "uf",
            "valor_total_estimado",
            "data_publicacao",
            "baseline_relevance",
            "baseline_categories",
            "baseline_score",
            "baseline_confidence",
            "matched_terms",
            "negative_matches",
        ]
        assert reader.fieldnames == expected_fields
        rows = list(reader)

    assert len(rows) == 120, f"Esperado 120 registros, obteve {len(rows)}"
    for r in rows:
        assert r["review_id"].startswith("DEV-")
        assert len(r["source_record_id"]) > 5
        assert len(r["objeto_original"]) > 5
        assert r["baseline_relevance"] in ("ALTA", "MEDIA", "BAIXA", "IRRELEVANTE")


def test_dev_unique_source_record_id():
    """Garante que não há nenhum source_record_id duplicado dentro do DEV."""
    with DEV_CORPUS_PATH.open("r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    sids = [r["source_record_id"] for r in rows]
    assert len(sids) == len(set(sids)), "Existem source_record_id duplicados no DEV"


def test_dev_unique_dev_ids():
    """Garante sequência contínua de DEV-001 a DEV-120 sem duplicatas ou lacunas."""
    with DEV_CORPUS_PATH.open("r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    dev_ids = [r["review_id"] for r in rows]
    expected_ids = [f"DEV-{i:03d}" for i in range(1, 121)]
    assert dev_ids == expected_ids


def test_zero_overlap_with_test_set():
    """Garante ZERO overlap entre o DEV set e o Test set imutável."""
    assert TEST_CORPUS_PATH.exists()

    with DEV_CORPUS_PATH.open("r", encoding="utf-8") as f:
        dev_ids = {r["source_record_id"] for r in csv.DictReader(f)}

    with TEST_CORPUS_PATH.open("r", encoding="utf-8") as f:
        test_ids = {r["source_record_id"] for r in csv.DictReader(f)}

    intersection = dev_ids & test_ids
    assert len(intersection) == 0, f"Overlap detectado entre DEV e TEST: {intersection}"


def test_dev_annotations_schema():
    """Valida o schema do arquivo de anotações do DEV e verifica se campos humanos estão vazios."""
    assert DEV_ANNOTATIONS_PATH.exists()

    with DEV_ANNOTATIONS_PATH.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        expected_fields = [
            "review_id",
            "source_record_id",
            "human_relevant",
            "human_relevance",
            "human_categories",
            "human_confidence",
            "human_notes",
            "reviewed_at",
        ]
        assert reader.fieldnames == expected_fields
        rows = list(reader)

    assert len(rows) == 120
    for r in rows:
        assert r["review_id"].startswith("DEV-")
        assert len(r["source_record_id"]) > 5
        # Campos humanos devem iniciar vazios
        assert r["human_relevant"] == ""
        assert r["human_relevance"] == ""
        assert r["reviewed_at"] == ""


def test_dev_blind_review_endpoint(tmp_path: Path):
    """Testa os endpoints /review/dev na API FastAPI em modo blind."""
    # Cria cópia temporária de annotations para não alterar os arquivos canônicos durante o teste
    temp_ann = tmp_path / "test_dev_annotations.csv"
    temp_ann.write_text(DEV_ANNOTATIONS_PATH.read_text(encoding="utf-8"), encoding="utf-8")

    app = create_app(dev_corpus_path=DEV_CORPUS_PATH, dev_annotations_path=temp_ann)
    client = TestClient(app)

    # 1. Summary
    res = client.get("/review/dev")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 120
    assert data["reviewed"] == 0
    assert data["pending"] == 120

    # 2. Export
    exp_res = client.get("/review/dev/export")
    assert exp_res.status_code == 200
    assert "DEV-001" in exp_res.text

    # 3. Detail
    det_res = client.get("/review/dev/DEV-001")
    assert det_res.status_code == 200
    det = det_res.json()
    assert det["review_id"] == "DEV-001"
    assert det["human"]["is_reviewed"] is False

    # 4. Save annotation
    payload = {
        "human_relevant": True,
        "human_relevance": "MEDIA",
        "human_categories": ["COZINHA"],
        "human_confidence": 4,
        "human_notes": "Anotação de teste",
    }
    put_res = client.put("/review/dev/DEV-001", json=payload)
    assert put_res.status_code == 200
    updated = put_res.json()
    assert updated["human"]["human_relevant"] is True
    assert updated["human"]["human_relevance"] == "MEDIA"
    assert updated["human"]["human_confidence"] == 4
    assert updated["human"]["is_reviewed"] is True

    # Verifica persistência no CSV temporário
    assert "DEV-001" in temp_ann.read_text(encoding="utf-8")


def test_dev_blind_review_hides_sampling_bucket():
    """Garante que a API não expõe o sampling bucket nem termos internos de amostragem."""
    app = create_app(dev_corpus_path=DEV_CORPUS_PATH, dev_annotations_path=DEV_ANNOTATIONS_PATH)
    client = TestClient(app)

    res = client.get("/review/dev/DEV-001")
    assert res.status_code == 200
    detail = res.json()

    assert "bucket" not in detail
    assert "sampling_bucket" not in detail
    assert "bucket_type" not in detail
    for k in detail.keys():
        assert "bucket" not in k.lower(), f"Chave com 'bucket' encontrada: {k}"


def test_dev_blind_review_hides_baseline_and_llm():
    """Garante ausência absoluta de predições do baseline e de LLM no detalhe DEV."""
    app = create_app(dev_corpus_path=DEV_CORPUS_PATH, dev_annotations_path=DEV_ANNOTATIONS_PATH)
    client = TestClient(app)

    res = client.get("/review/dev/DEV-001")
    assert res.status_code == 200
    detail = res.json()

    # Baseline deve ser estritamente None
    assert detail.get("baseline") is None, "Predições de modelo vazaram no endpoint blind review!"
    # Não deve haver campos soltos de LLM ou scores no nível raiz
    assert "llm_prediction" not in detail
    assert "opportunity_score" not in detail
    assert "confidence_score" not in detail
    assert "matched_terms" not in detail
    assert "negative_matches" not in detail


def test_semantic_validation_valid_combinations(tmp_path: Path):
    """Garante que combinações semânticas válidas de anotação são aceitas com 200 OK."""
    temp_ann = tmp_path / "test_valid_ann.csv"
    temp_ann.write_text(DEV_ANNOTATIONS_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    app = create_app(dev_corpus_path=DEV_CORPUS_PATH, dev_annotations_path=temp_ann)
    client = TestClient(app)

    valid_cases = [
        {"human_relevant": True, "human_relevance": "ALTA", "human_categories": ["COZINHA"], "human_confidence": 5},
        {"human_relevant": True, "human_relevance": "MEDIA", "human_categories": ["REFEITORIO", "INOX"], "human_confidence": 4},
        {"human_relevant": True, "human_relevance": "BAIXA", "human_categories": ["ALIMENTACAO_COLETIVA"], "human_confidence": 3},
        {"human_relevant": False, "human_relevance": "IRRELEVANTE", "human_categories": [], "human_confidence": 5},
    ]

    for idx, case in enumerate(valid_cases, start=1):
        rid = f"DEV-{idx:03d}"
        res = client.put(f"/review/dev/{rid}", json=case)
        assert res.status_code == 200, f"Falha para caso válido {case}: {res.text}"
        data = res.json()
        assert data["human"]["human_relevant"] == case["human_relevant"]
        assert data["human"]["human_relevance"] == case["human_relevance"]
        assert set(data["human"]["human_categories"]) == set(case["human_categories"])


def test_semantic_validation_invalid_rejected(tmp_path: Path):
    """Garante que combinações inconsistentes são rejeitadas com 422 Unprocessable Entity."""
    temp_ann = tmp_path / "test_invalid_ann.csv"
    temp_ann.write_text(DEV_ANNOTATIONS_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    app = create_app(dev_corpus_path=DEV_CORPUS_PATH, dev_annotations_path=temp_ann)
    client = TestClient(app)

    # 1. relevant=False mas relevance != IRRELEVANTE
    for rel in ("ALTA", "MEDIA", "BAIXA"):
        res = client.put("/review/dev/DEV-001", json={
            "human_relevant": False,
            "human_relevance": rel,
            "human_categories": [],
            "human_confidence": 5,
        })
        assert res.status_code == 422
        assert "IRRELEVANTE" in res.text

    # 2. relevant=False mas categories não vazio
    res = client.put("/review/dev/DEV-001", json={
        "human_relevant": False,
        "human_relevance": "IRRELEVANTE",
        "human_categories": ["COZINHA"],
        "human_confidence": 5,
    })
    assert res.status_code == 422
    assert "vazio" in res.text

    # 3. relevant=True mas relevance == IRRELEVANTE
    res = client.put("/review/dev/DEV-001", json={
        "human_relevant": True,
        "human_relevance": "IRRELEVANTE",
        "human_categories": ["COZINHA"],
        "human_confidence": 5,
    })
    assert res.status_code == 422
    assert "ALTA, MEDIA ou BAIXA" in res.text

    # 4. Categoria inexistente
    res = client.put("/review/dev/DEV-001", json={
        "human_relevant": True,
        "human_relevance": "ALTA",
        "human_categories": ["CATEGORIA_INVENTADA"],
        "human_confidence": 5,
    })
    assert res.status_code == 422
    assert "Categorias inválidas" in res.text


def test_dev_save_persists_and_reloads(tmp_path: Path):
    """Garante que a anotação salva é persistida em disco e recarregada fielmente."""
    temp_ann = tmp_path / "test_persist_ann.csv"
    temp_ann.write_text(DEV_ANNOTATIONS_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    app = create_app(dev_corpus_path=DEV_CORPUS_PATH, dev_annotations_path=temp_ann)
    client = TestClient(app)

    payload = {
        "human_relevant": True,
        "human_relevance": "ALTA",
        "human_categories": ["COZINHA", "INOX"],
        "human_confidence": 5,
        "human_notes": "Anotação persistida para validação.",
    }
    put_res = client.put("/review/dev/DEV-001", json=payload)
    assert put_res.status_code == 200

    # Recarrega via GET /review/dev/DEV-001
    get_res = client.get("/review/dev/DEV-001")
    assert get_res.status_code == 200
    detail = get_res.json()
    assert detail["human"]["human_relevant"] is True
    assert detail["human"]["human_relevance"] == "ALTA"
    assert set(detail["human"]["human_categories"]) == {"COZINHA", "INOX"}
    assert detail["human"]["human_confidence"] == 5
    assert detail["human"]["human_notes"] == "Anotação persistida para validação."
    assert detail["human"]["is_reviewed"] is True
    assert detail["human"]["reviewed_at"] is not None

    # Valida resumo
    sum_res = client.get("/review/dev")
    assert sum_res.status_code == 200
    summary = sum_res.json()
    assert summary["total"] == 120
    assert summary["reviewed"] == 1
    assert summary["pending"] == 119
    assert summary["progress_percent"] == 0.8


def test_dev_corpus_remains_immutable(tmp_path: Path):
    """Garante que salvar anotações no DEV JAMAIS altera o arquivo do corpus DEV."""
    sha_before = hashlib.sha256(DEV_CORPUS_PATH.read_bytes()).hexdigest()

    temp_ann = tmp_path / "test_immutability_ann.csv"
    temp_ann.write_text(DEV_ANNOTATIONS_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    app = create_app(dev_corpus_path=DEV_CORPUS_PATH, dev_annotations_path=temp_ann)
    client = TestClient(app)

    payload = {
        "human_relevant": False,
        "human_relevance": "IRRELEVANTE",
        "human_categories": [],
        "human_confidence": 5,
        "human_notes": "Teste de imutabilidade do corpus.",
    }
    res = client.put("/review/dev/DEV-002", json=payload)
    assert res.status_code == 200

    sha_after = hashlib.sha256(DEV_CORPUS_PATH.read_bytes()).hexdigest()
    assert sha_before == sha_after, "O corpus de desenvolvimento DEV foi modificado! Deve ser estritamente imutável."


def test_freeze_metadata_and_hash_generation():
    """Valida integridade criptográfica do hash SHA-256 e metadados no manifest."""
    assert DEV_MANIFEST_PATH.exists()
    manifest = json.loads(DEV_MANIFEST_PATH.read_text(encoding="utf-8"))

    assert manifest["corpus_version"] == "dev-0.1.0"
    assert manifest["total_records"] == 120
    assert manifest["distribution"]["potential_relevant"] == 30
    assert manifest["distribution"]["hard_negatives"] == 30
    assert manifest["distribution"]["negative_context"] == 20
    assert manifest["distribution"]["ambiguous"] == 20
    assert manifest["distribution"]["obvious_negatives"] == 20

    # Recalcula SHA-256 do arquivo em disco
    computed_sha = hashlib.sha256(DEV_CORPUS_PATH.read_bytes()).hexdigest()
    assert computed_sha == manifest["sha256"]


def test_dev_temporal_window_is_strictly_posterior():
    """Garante que todo registro no DEV foi publicado estritamente após a data limite do Test Set."""
    cut_off = "2026-09-11T08:30:06"
    with DEV_CORPUS_PATH.open("r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    for r in rows:
        assert r["data_publicacao"] > cut_off, f"Registro {r['review_id']} tem data {r['data_publicacao']} <= {cut_off}"
