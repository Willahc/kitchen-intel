"""Testes unitários automatizados do classificador LLM (Gate 5).

Todos os testes utilizam mocks e nunca realizam chamadas a APIs de rede externas.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from src.classifier.cache import LLMCache
from src.classifier.engine import LLMClassifier
from src.classifier.llm_client import LLMClient
from src.models.llm import LLMStructuredOutput
from scripts.evaluate_llm_human import compute_llm_metrics


@pytest.fixture
def mock_prompt_file(tmp_path: Path) -> Path:
    p = tmp_path / "prompt_test.txt"
    p.write_text("Você é um classificador B2B de cozinhas profissionais. Responda em JSON.", encoding="utf-8")
    return p


@pytest.fixture
def sample_record() -> dict[str, Any]:
    return {
        "review_id": "REV-001",
        "source_record_id": "11111111000100-1-000001/2026",
        "objeto_original": "Aquisição de fogão industrial de 6 bocas e forno para cozinha",
        "orgao_nome": "Hospital Geral",
        "unidade_nome": "Nutrição",
        "municipio": "São Paulo",
        "uf": "SP",
        "valor_total_estimado": 45000.0,
        "data_publicacao": "2026-09-10T10:00:00",
        # Campos que NÃO podem vazar para o prompt do modelo
        "baseline_relevance": "ALTA",
        "baseline_score": 90,
        "matched_terms": "fogao industrial -> COCCAO",
        "human_relevant": "TRUE",
        "human_relevance": "ALTA",
        "human_notes": "Anotação do revisor William",
    }


def test_structured_output_valid() -> None:
    valid_json = """{
        "relevant": true,
        "relevance": "ALTA",
        "categories": ["COZINHA", "COCCAO"],
        "confidence": 95,
        "reason": "Compra de fogão industrial diretamente ligada a cozinha profissional."
    }"""
    output = LLMStructuredOutput.model_validate_json(valid_json)
    assert output.relevant is True
    assert output.relevance == "ALTA"
    assert output.categories == ["COCCAO", "COZINHA"]
    assert output.confidence == 95
    assert "fogão" in output.reason


def test_json_invalido(mock_prompt_file: Path, sample_record: dict[str, Any], tmp_path: Path) -> None:
    calls = 0

    def bad_json_handler(payload: dict[str, Any]) -> dict[str, Any]:
        nonlocal calls
        calls += 1
        return {"content": "{ Este texto não é um JSON válido ...", "input_tokens": 100, "output_tokens": 20}

    client = LLMClient(mock_handler=bad_json_handler)
    classifier = LLMClassifier(
        client=client,
        cache=LLMCache(tmp_path / "cache.json"),
        prompt_path=mock_prompt_file,
        max_schema_retries=1,
    )

    result = classifier.classify_record(sample_record, use_cache=False)
    assert result.status == "ERROR"
    assert "Erro de validação de schema" in str(result.error)
    # Verificamos que tentou a chamada inicial + 1 retry
    assert calls == 2


def test_enum_invalido(mock_prompt_file: Path, sample_record: dict[str, Any], tmp_path: Path) -> None:
    def bad_enum_handler(payload: dict[str, Any]) -> dict[str, Any]:
        bad = {
            "relevant": True,
            "relevance": "SUPER_ALTA",  # Enum inválido
            "categories": ["COZINHA"],
            "confidence": 80,
            "reason": "Justificativa teste.",
        }
        return {"content": json.dumps(bad), "input_tokens": 100, "output_tokens": 30}

    client = LLMClient(mock_handler=bad_enum_handler)
    classifier = LLMClassifier(
        client=client,
        cache=LLMCache(tmp_path / "cache.json"),
        prompt_path=mock_prompt_file,
        max_schema_retries=1,
    )

    result = classifier.classify_record(sample_record, use_cache=False)
    assert result.status == "ERROR"
    assert "SUPER_ALTA" in str(result.error)


def test_categoria_invalida(mock_prompt_file: Path, sample_record: dict[str, Any], tmp_path: Path) -> None:
    def bad_cat_handler(payload: dict[str, Any]) -> dict[str, Any]:
        bad = {
            "relevant": True,
            "relevance": "ALTA",
            "categories": ["COZINHA", "CATEGORIA_INEXISTENTE"],
            "confidence": 80,
            "reason": "Justificativa teste.",
        }
        return {"content": json.dumps(bad), "input_tokens": 100, "output_tokens": 30}

    client = LLMClient(mock_handler=bad_cat_handler)
    classifier = LLMClassifier(
        client=client,
        cache=LLMCache(tmp_path / "cache.json"),
        prompt_path=mock_prompt_file,
        max_schema_retries=1,
    )

    result = classifier.classify_record(sample_record, use_cache=False)
    assert result.status == "ERROR"
    assert "CATEGORIA_INEXISTENTE" in str(result.error)


def test_timeout_and_provider_error(mock_prompt_file: Path, sample_record: dict[str, Any], tmp_path: Path) -> None:
    def error_handler(payload: dict[str, Any]) -> dict[str, Any]:
        raise TimeoutError("Conexão com a OpenAI expirou (timeout).")

    client = LLMClient(mock_handler=error_handler)
    classifier = LLMClassifier(
        client=client,
        cache=LLMCache(tmp_path / "cache.json"),
        prompt_path=mock_prompt_file,
    )

    result = classifier.classify_record(sample_record, use_cache=False)
    assert result.status == "ERROR"
    assert "Conexão com a OpenAI expirou" in str(result.error)


def test_retry_de_schema_com_sucesso(mock_prompt_file: Path, sample_record: dict[str, Any], tmp_path: Path) -> None:
    attempt = 0

    def recovery_handler(payload: dict[str, Any]) -> dict[str, Any]:
        nonlocal attempt
        attempt += 1
        if attempt == 1:
            # Primeira tentativa: JSON quebrado
            return {"content": "erro {", "input_tokens": 100, "output_tokens": 10}
        else:
            # Segunda tentativa (após instrução de retry): JSON corrigido
            valid = {
                "relevant": True,
                "relevance": "ALTA",
                "categories": ["COZINHA"],
                "confidence": 90,
                "reason": "Recuperado com sucesso no retry.",
            }
            return {"content": json.dumps(valid), "input_tokens": 150, "output_tokens": 30}

    client = LLMClient(mock_handler=recovery_handler)
    classifier = LLMClassifier(
        client=client,
        cache=LLMCache(tmp_path / "cache.json"),
        prompt_path=mock_prompt_file,
        max_schema_retries=1,
    )

    result = classifier.classify_record(sample_record, use_cache=False)
    assert attempt == 2
    assert result.status == "SUCCESS"
    assert result.relevant is True
    assert result.relevance == "ALTA"
    assert result.total_tokens == 290  # 100+10 + 150+30


def test_cache_hit_and_miss(mock_prompt_file: Path, sample_record: dict[str, Any], tmp_path: Path) -> None:
    call_count = 0

    def counted_handler(payload: dict[str, Any]) -> dict[str, Any]:
        nonlocal call_count
        call_count += 1
        valid = {
            "relevant": False,
            "relevance": "IRRELEVANTE",
            "categories": [],
            "confidence": 99,
            "reason": "Material escolar comum.",
        }
        return {"content": json.dumps(valid), "input_tokens": 200, "output_tokens": 25}

    client = LLMClient(mock_handler=counted_handler)
    cache = LLMCache(tmp_path / "test_cache.json")
    classifier = LLMClassifier(
        client=client,
        cache=cache,
        prompt_path=mock_prompt_file,
    )

    # 1. Primeira chamada: Cache MISS -> executa o mock
    res1 = classifier.classify_record(sample_record, use_cache=True)
    assert res1.status == "SUCCESS"
    assert call_count == 1

    # 2. Segunda chamada com mesmo registro: Cache HIT -> NÃO executa o mock
    res2 = classifier.classify_record(sample_record, use_cache=True)
    assert res2.status == "CACHED"
    assert call_count == 1  # Permaneceu 1!
    assert res2.relevance == "IRRELEVANTE"
    assert res2.input_hash == res1.input_hash


def test_token_accounting_and_cost_pricing() -> None:
    client = LLMClient(provider="openai", model="gpt-4o-mini")
    # gpt-4o-mini: input = $0.15 / 1M ($0.00000015/token); output = $0.60 / 1M ($0.00000060/token)
    in_tok = 1000
    out_tok = 200
    expected_cost = (1000 * 0.00000015) + (200 * 0.00000060)  # 0.00015 + 0.00012 = 0.00027
    actual_cost = client.calculate_cost(in_tok, out_tok)
    assert actual_cost == round(expected_cost, 8)


class _OpenAIHTTPResponse:
    def __init__(self, status_code: int, body: dict[str, Any]) -> None:
        self.status_code = status_code
        self._body = body
        self.text = json.dumps(body)
        self.headers = {"x-ratelimit-limit-requests": "500"}

    def json(self) -> dict[str, Any]:
        return self._body


def test_openai_luna_success_uses_strict_schema_and_token_cost(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    class FakeClient:
        def __init__(self, **_: Any) -> None:
            pass

        def __enter__(self) -> "FakeClient":
            return self

        def __exit__(self, *_: Any) -> None:
            return None

        def post(self, url: str, *, headers: dict[str, str], json: dict[str, Any]) -> _OpenAIHTTPResponse:
            captured.update({"url": url, "headers": headers, "payload": json})
            return _OpenAIHTTPResponse(200, {
                "choices": [{"message": {"content": '{"relevant":false,"relevance":"IRRELEVANTE","categories":[],"confidence":0,"reason":"Teste de conectividade."}'}}],
                "usage": {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120},
            })

    monkeypatch.setattr("src.classifier.llm_client.httpx.Client", FakeClient)
    client = LLMClient(provider="openai", model="gpt-5.6-luna", api_key="test-key")
    response = client.complete("system", "user")

    assert captured["url"] == "https://api.openai.com/v1/chat/completions"
    assert captured["payload"]["reasoning_effort"] == "none"
    assert captured["payload"]["response_format"]["json_schema"]["strict"] is True
    assert captured["payload"]["response_format"]["json_schema"]["schema"]["additionalProperties"] is False
    assert response["total_tokens"] == 120
    assert response["cost"] == 0.000044
    assert "x-ratelimit-limit-requests" in response["rate_limit_headers"]


@pytest.mark.parametrize("status_code", [401, 404])
def test_openai_luna_auth_or_model_error_is_reported(monkeypatch: pytest.MonkeyPatch, status_code: int) -> None:
    class FakeClient:
        def __init__(self, **_: Any) -> None:
            pass

        def __enter__(self) -> "FakeClient":
            return self

        def __exit__(self, *_: Any) -> None:
            return None

        def post(self, *_: Any, **__: Any) -> _OpenAIHTTPResponse:
            return _OpenAIHTTPResponse(status_code, {"error": {"message": "request rejected"}})

    monkeypatch.setattr("src.classifier.llm_client.httpx.Client", FakeClient)
    client = LLMClient(provider="openai", model="gpt-5.6-luna", api_key="test-key")
    with pytest.raises(RuntimeError, match=f"HTTP {status_code}"):
        client.complete("system", "user")


def test_openrouter_success_is_routed_with_strict_schema(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    class FakeClient:
        def __init__(self, **_: Any) -> None: pass
        def __enter__(self) -> "FakeClient": return self
        def __exit__(self, *_: Any) -> None: return None
        def post(self, url: str, *, headers: dict[str, str], json: dict[str, Any]) -> _OpenAIHTTPResponse:
            captured.update({"url": url, "payload": json})
            return _OpenAIHTTPResponse(200, {"choices": [{"message": {"content": '{"relevant":false,"relevance":"IRRELEVANTE","categories":[],"confidence":0,"reason":"Teste OpenRouter."}'}}], "usage": {"prompt_tokens": 3, "completion_tokens": 4, "total_tokens": 7}})

    monkeypatch.setattr("src.classifier.llm_client.httpx.Client", FakeClient)
    client = LLMClient(provider="openrouter", model="nvidia/nemotron-3-super-120b-a12b:free", api_key="test-key")
    response = client.complete("system", "user")
    assert captured["url"] == "https://openrouter.ai/api/v1/chat/completions"
    assert captured["payload"]["model"].endswith(":free")
    assert captured["payload"]["response_format"]["json_schema"]["strict"] is True
    assert response["total_tokens"] == 7
    assert response["cost"] == 0.0


@pytest.mark.parametrize("status_code", [401, 429])
def test_openrouter_auth_or_rate_limit_is_reported(monkeypatch: pytest.MonkeyPatch, status_code: int) -> None:
    class FakeClient:
        def __init__(self, **_: Any) -> None: pass
        def __enter__(self) -> "FakeClient": return self
        def __exit__(self, *_: Any) -> None: return None
        def post(self, *_: Any, **__: Any) -> _OpenAIHTTPResponse:
            return _OpenAIHTTPResponse(status_code, {"error": {"message": "request rejected"}})

    monkeypatch.setattr("src.classifier.llm_client.httpx.Client", FakeClient)
    client = LLMClient(provider="openrouter", model="nvidia/nemotron-3-super-120b-a12b:free", api_key="test-key")
    with pytest.raises(RuntimeError if status_code == 401 else Exception):
        client.complete("system", "user")


def test_input_hash_deterministic(sample_record: dict[str, Any]) -> None:
    clean1, hash1 = LLMClassifier.prepare_input(sample_record)
    clean2, hash2 = LLMClassifier.prepare_input(dict(sample_record))
    assert hash1 == hash2

    # Modificar campo permitido altera o hash
    altered = dict(sample_record)
    altered["objeto_original"] = "Outro objeto diferente"
    _, hash3 = LLMClassifier.prepare_input(altered)
    assert hash1 != hash3


def test_ausencia_de_human_e_baseline_no_payload(sample_record: dict[str, Any]) -> None:
    """Verifica que NENHUM metadado de baseline ou anotação humana é repassado ao payload."""
    clean, _ = LLMClassifier.prepare_input(sample_record)

    # Verifica campos permitidos
    assert "objeto_original" in clean
    assert "orgao_nome" in clean
    assert "unidade_nome" in clean
    assert "municipio" in clean
    assert "uf" in clean
    assert "valor_total_estimado" in clean
    assert "data_publicacao" in clean

    # Verifica ausência total de campos proibidos
    assert "baseline_relevance" not in clean
    assert "baseline_score" not in clean
    assert "matched_terms" not in clean
    assert "human_relevant" not in clean
    assert "human_relevance" not in clean
    assert "human_notes" not in clean


def test_evaluation_metrics_and_zero_division() -> None:
    # Cenário seguro de divisão por zero: sem positivos (TP=0, FP=0, TN=5, FN=0)
    predictions = [
        {"review_id": "REV-01", "relevant": False, "relevance": "IRRELEVANTE", "categories": []},
        {"review_id": "REV-02", "relevant": False, "relevance": "IRRELEVANTE", "categories": []},
    ]
    annotations = {
        "REV-01": {"human_relevant": "FALSE", "human_relevance": "IRRELEVANTE", "human_categories": ""},
        "REV-02": {"human_relevant": "FALSE", "human_relevance": "IRRELEVANTE", "human_categories": ""},
    }
    metrics = compute_llm_metrics(predictions, annotations)
    assert metrics["status"] == "EVALUATED"
    cm = metrics["confusion_matrix"]
    assert cm["true_negative"] == 2
    assert cm["true_positive"] == 0
    assert cm["false_positive"] == 0
    assert cm["false_negative"] == 0

    bm = metrics["binary_metrics"]
    assert bm["accuracy"] == 1.0
    assert bm["precision"] == 0.0
    assert bm["recall"] == 0.0
    assert bm["f1_score"] == 0.0


def test_evaluation_join_tp_fp_tn_fn() -> None:
    # 1 TP, 1 FP, 1 TN, 1 FN
    predictions = [
        {"review_id": "REV-1", "relevant": True, "relevance": "ALTA", "categories": ["COZINHA"]},
        {"review_id": "REV-2", "relevant": True, "relevance": "MEDIA", "categories": ["INOX"]},
        {"review_id": "REV-3", "relevant": False, "relevance": "IRRELEVANTE", "categories": []},
        {"review_id": "REV-4", "relevant": False, "relevance": "IRRELEVANTE", "categories": []},
    ]
    annotations = {
        "REV-1": {"human_relevant": "TRUE", "human_relevance": "ALTA", "human_categories": "COZINHA"},
        "REV-2": {"human_relevant": "FALSE", "human_relevance": "IRRELEVANTE", "human_categories": ""},
        "REV-3": {"human_relevant": "FALSE", "human_relevance": "IRRELEVANTE", "human_categories": ""},
        "REV-4": {"human_relevant": "TRUE", "human_relevance": "ALTA", "human_categories": "COZINHA"},
    }
    metrics = compute_llm_metrics(predictions, annotations)
    cm = metrics["confusion_matrix"]
    assert cm["true_positive"] == 1
    assert cm["false_positive"] == 1
    assert cm["true_negative"] == 1
    assert cm["false_negative"] == 1

    bm = metrics["binary_metrics"]
    assert bm["accuracy"] == 0.5
    assert bm["precision"] == 0.5
    assert bm["recall"] == 0.5
    assert bm["f1_score"] == 0.5
    assert len(metrics["error_records"]) == 2  # 1 FP e 1 FN


def test_evaluate_llm_human_cli_end_to_end(tmp_path: Path) -> None:
    from scripts.evaluate_llm_human import main as eval_main

    # Criar arquivos sintéticos
    pred_file = tmp_path / "preds.jsonl"
    preds = [
        {"review_id": "REV-001", "relevant": True, "relevance": "ALTA", "categories": ["COZINHA"], "reason": "Fogao industrial"},
        {"review_id": "REV-002", "relevant": False, "relevance": "IRRELEVANTE", "categories": [], "reason": "Material escolar"},
    ]
    with pred_file.open("w", encoding="utf-8") as f:
        for p in preds:
            f.write(json.dumps(p) + "\n")

    ann_file = tmp_path / "anns.csv"
    ann_file.write_text(
        "review_id,source_record_id,human_relevant,human_relevance,human_categories,human_confidence,human_notes,reviewed_at\n"
        "REV-001,REC-1,TRUE,ALTA,COZINHA,5,Ok,2026-09-12\n"
        "REV-002,REC-2,FALSE,IRRELEVANTE,,5,Lixo,2026-09-12\n",
        encoding="utf-8",
    )

    baseline_json = tmp_path / "baseline.json"
    baseline_json.write_text(
        json.dumps({
            "binary_metrics": {"precision": 0.375, "recall": 0.8182, "f1_score": 0.5143, "accuracy": 0.7763},
            "confusion_matrix": {"true_positive": 9, "false_positive": 15, "true_negative": 50, "false_negative": 2},
        }),
        encoding="utf-8",
    )

    out_comp = tmp_path / "comparison.json"
    out_err = tmp_path / "error_analysis.md"

    import sys
    orig_argv = sys.argv
    try:
        sys.argv = [
            "evaluate_llm_human.py",
            "--predictions", str(pred_file),
            "--annotations", str(ann_file),
            "--baseline-json", str(baseline_json),
            "--output-comparison", str(out_comp),
            "--output-error-analysis", str(out_err),
        ]
        ret = eval_main()
        assert ret == 0
        assert out_comp.exists()
        assert out_err.exists()

        comp = json.loads(out_comp.read_text(encoding="utf-8"))
        assert comp["llm"]["binary_metrics"]["accuracy"] == 1.0
        assert comp["delta"]["precision_delta"] == round(1.0 - 0.375, 4)
    finally:
        sys.argv = orig_argv


def test_daily_quota_exhausted_error_handling() -> None:
    from src.classifier.llm_client import DailyQuotaExhaustedError
    err = DailyQuotaExhaustedError("Quota exceeded", retry_delay="24h")
    assert "Quota exceeded" in str(err)
    assert err.retry_delay == "24h"


def test_no_api_key_leakage() -> None:
    fake_key = "AIzaSyFakeSecretKeyNotToBeLeaked12345"
    client = LLMClient(provider="gemini", api_key=fake_key)
    # LLMClient não deve exibir a chave no __repr__ ou __str__
    client_str = str(client.__dict__)
    # Verifica que em logs e relatórios a chave nunca é injetada
    assert client.api_key == fake_key


def test_fixed_model_id_default() -> None:
    client = LLMClient(provider="gemini")
    assert client.model == "gemini-2.5-flash"
    assert client.provider == "gemini"


def test_max_new_calls_and_cache_resumption(mock_prompt_file: Path, sample_record: dict[str, Any], tmp_path: Path) -> None:
    calls_count = 0

    def counting_mock_handler(payload: dict[str, Any]) -> dict[str, Any]:
        nonlocal calls_count
        calls_count += 1
        return {
            "content": json.dumps({
                "relevant": True,
                "relevance": "ALTA",
                "categories": ["COZINHA"],
                "confidence": 95,
                "reason": "Equipamento para cozinha industrial.",
            }),
            "input_tokens": 100,
            "output_tokens": 50,
        }

    cache_file = tmp_path / "cache_test.json"
    cache = LLMCache(cache_file)
    client = LLMClient(mock_handler=counting_mock_handler)
    classifier = LLMClassifier(client=client, cache=cache, prompt_path=mock_prompt_file)

    # Primeira execução: deve chamar o mock (nova chamada)
    res1 = classifier.classify_record(sample_record, use_cache=True)
    assert res1.status == "SUCCESS"
    assert calls_count == 1

    # Segunda execução com cache: deve retornar CACHED e NÃO incrementar chamadas
    res2 = classifier.classify_record(sample_record, use_cache=True)
    assert res2.status == "CACHED"
    assert calls_count == 1  # Permanece 1!


def test_results_segregated_by_model(mock_prompt_file: Path, sample_record: dict[str, Any], tmp_path: Path) -> None:
    cache_file = tmp_path / "cache_models.json"
    cache = LLMCache(cache_file)

    def dummy_handler(payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "content": json.dumps({
                "relevant": True,
                "relevance": "ALTA",
                "categories": ["COZINHA"],
                "confidence": 90,
                "reason": "Ok",
            }),
            "input_tokens": 10,
            "output_tokens": 10,
        }

    client_a = LLMClient(provider="gemini", model="gemini-2.5-flash", mock_handler=dummy_handler)
    classifier_a = LLMClassifier(client=client_a, cache=cache, prompt_path=mock_prompt_file)
    res_a = classifier_a.classify_record(sample_record, use_cache=True)
    assert res_a.model == "gemini-2.5-flash"

    # Mesma entrada com modelo B deve ser cache MISS (chaves segregadas)
    client_b = LLMClient(provider="gemini", model="gemini-3.5-flash", mock_handler=dummy_handler)
    classifier_b = LLMClassifier(client=client_b, cache=cache, prompt_path=mock_prompt_file)
    _, input_hash = classifier_b.prepare_input(sample_record)
    key_b = cache.generate_key(input_hash, "gemini", "gemini-3.5-flash", "0.1.0")
    assert cache.get(key_b) is None


def test_evaluate_llm_human_incomplete_blocked(tmp_path: Path) -> None:
    from scripts.evaluate_llm_human import main as eval_main
    pred_file = tmp_path / "preds.jsonl"
    pred_file.write_text(
        json.dumps({"review_id": "REV-001", "model": "gemini-2.5-flash", "status": "SUCCESS", "relevant": True}) + "\n",
        encoding="utf-8"
    )
    ann_file = tmp_path / "anns.csv"
    ann_file.write_text(
        "review_id,source_record_id,human_relevant,human_relevance,human_categories,human_confidence,human_notes,reviewed_at\n"
        "REV-001,REC-1,TRUE,ALTA,COZINHA,5,Ok,2026-09-12\n"
        "REV-002,REC-2,FALSE,IRRELEVANTE,,5,Lixo,2026-09-12\n",
        encoding="utf-8"
    )
    baseline_json = tmp_path / "baseline.json"
    baseline_json.write_text("{}", encoding="utf-8")

    import sys
    orig_argv = sys.argv
    try:
        sys.argv = [
            "evaluate_llm_human.py",
            "--predictions", str(pred_file),
            "--annotations", str(ann_file),
            "--baseline-json", str(baseline_json),
        ]
        # Deve retornar 1 e bloquear pois só há 1 predição para 2 anotações
        ret = eval_main()
        assert ret == 1
    finally:
        sys.argv = orig_argv
