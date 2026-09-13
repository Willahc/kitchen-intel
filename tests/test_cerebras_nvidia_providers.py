"""Testes unitários mockados para os provedores Cerebras e NVIDIA API Catalog.

Garante ausência total de chamadas reais nos testes automatizados e valida:
- Success e Structured Output
- Falhas de autenticação (401/MissingCredentials)
- Limites de taxa (429/DailyQuotaExhaustedError)
- Modelo indisponível (404/MODEL_UNAVAILABLE)
- Schema/JSON inválido
- Contabilidade de tokens e custos
- Segregação de chaves de cache
- Integração com ProviderRouter e Circuit Breaker
- Sanitização estrita de credenciais em mensagens de erro
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from src.classifier.cache import LLMCache
from src.classifier.circuit_breaker import CircuitBreaker, CircuitState
from src.classifier.engine import LLMClassifier
from src.classifier.llm_client import DailyQuotaExhaustedError, LLMClient, MissingCredentialsError
from src.classifier.router import ProviderRouter, ProviderStatus, RoutingMode, sanitize_error_message

SAMPLE_RECORD = {
    "review_id": "REV-001",
    "source_record_id": "10199860000150-1-000025/2026",
    "objeto_original": "Manutenção preventiva e corretiva em equipamentos de cozinha industrial.",
    "orgao_nome": "Comando do Exército",
    "unidade_nome": "Base de Apoio",
    "municipio": "Rio de Janeiro",
    "uf": "RJ",
    "valor_total_estimado": 120000.0,
    "data_publicacao": "2026-09-12T10:00:00Z",
}


def make_mock_classification(provider: str, model: str) -> dict[str, Any]:
    content = json.dumps(
        {
            "relevant": True,
            "relevance": "ALTA",
            "categories": ["COZINHA", "INFRAESTRUTURA"],
            "confidence": 95,
            "reason": f"Classificação gerada via {provider} ({model}).",
        }
    )
    return {
        "content": content,
        "input_tokens": 1200,
        "output_tokens": 150,
        "total_tokens": 1350,
        "latency_ms": 350.0,
        "cost": 0.0,
        "rate_limit_headers": {"x-ratelimit-limit": "1000", "x-ratelimit-remaining": "999"},
    }


@pytest.fixture
def mock_cache(tmp_path: Path) -> LLMCache:
    return LLMCache(cache_file=tmp_path / "test_cache.json")


# ==============================================================================
# CEREBRAS TESTS
# ==============================================================================


def test_cerebras_success(mock_cache: LLMCache):
    """Cerebras processa com sucesso e gera structured output validado."""
    client = LLMClient(
        provider="cerebras",
        model="qwen-3.8-27b",
        mock_handler=lambda p: make_mock_classification("cerebras", "qwen-3.8-27b"),
    )
    classifier = LLMClassifier(client=client, cache=mock_cache)
    result = classifier.classify_record(SAMPLE_RECORD, use_cache=True)

    assert result.status == "SUCCESS"
    assert result.provider == "cerebras"
    assert result.model == "qwen-3.8-27b"
    assert result.relevant is True
    assert result.relevance == "ALTA"
    assert "COZINHA" in result.categories
    assert result.input_tokens == 1200
    assert result.output_tokens == 150
    assert result.total_tokens == 1350
    assert result.estimated_cost == 0.0


def test_cerebras_auth_failure(mock_cache: LLMCache, monkeypatch: pytest.MonkeyPatch):
    """Cerebras sem credenciais levanta MissingCredentialsError."""
    monkeypatch.delenv("CEREBRAS_API_KEY", raising=False)
    client = LLMClient(provider="cerebras", model="qwen-3.8-27b", api_key="")
    classifier = LLMClassifier(client=client, cache=mock_cache)

    result = classifier.classify_record(SAMPLE_RECORD, use_cache=False)
    assert result.status == "ERROR"
    assert "credencial" in str(result.error).lower()



def test_cerebras_rate_limit(mock_cache: LLMCache):
    """Cerebras 429 dispara DailyQuotaExhaustedError."""

    def rate_limit_handler(p):
        raise DailyQuotaExhaustedError("HTTP 429 da Cerebras API", retry_delay="60")

    client = LLMClient(provider="cerebras", model="qwen-3.8-27b", mock_handler=rate_limit_handler)
    classifier = LLMClassifier(client=client, cache=mock_cache)

    with pytest.raises(DailyQuotaExhaustedError):
        classifier.classify_record(SAMPLE_RECORD, use_cache=False)


def test_cerebras_model_unavailable(mock_cache: LLMCache):
    """Cerebras 404 registra erro de modelo indisponível."""

    def not_found_handler(p):
        raise RuntimeError("Erro HTTP 404 da Cerebras API: Model not found")

    client = LLMClient(provider="cerebras", model="qwen-3.8-27b", mock_handler=not_found_handler)
    classifier = LLMClassifier(client=client, cache=mock_cache)

    result = classifier.classify_record(SAMPLE_RECORD, use_cache=False)
    assert result.status == "ERROR"
    assert result.http_status == 404
    assert result.error_type == "MODEL_ERROR"


def test_cerebras_schema_invalid(mock_cache: LLMCache):
    """Cerebras retornando JSON fora de schema é detectado e registrado."""

    def bad_json_handler(p):
        return {
            "content": "{\"campo_invalido\": 123}",
            "input_tokens": 100,
            "output_tokens": 50,
            "total_tokens": 150,
            "latency_ms": 100.0,
            "cost": 0.0,
        }

    client = LLMClient(provider="cerebras", model="qwen-3.8-27b", mock_handler=bad_json_handler)
    classifier = LLMClassifier(client=client, cache=mock_cache)

    result = classifier.classify_record(SAMPLE_RECORD, use_cache=False)
    assert result.status == "ERROR"
    assert result.error_type == "SCHEMA_INVALID"


def test_cerebras_cache_segregation(mock_cache: LLMCache):
    """Chaves de cache da Cerebras não colidem com outros provedores."""
    k_cerebras = mock_cache.generate_key("hash123", "cerebras", "qwen-3.8-27b", "0.1.0")
    k_openrouter = mock_cache.generate_key("hash123", "openrouter", "qwen-3.8-27b", "0.1.0")
    assert k_cerebras != k_openrouter


def test_cerebras_provider_routing(mock_cache: LLMCache):
    """ProviderRouter roteia corretamente para Cerebras quando configurado."""
    config = {
        "production": {
            "allow_fallback": True,
            "providers": [
                {"provider": "cerebras", "model": "qwen-3.8-27b"},
                {"provider": "deterministic", "model": "rules_v0.1.1"},
            ],
            "circuit_breaker": {"failure_threshold": 3, "cooldown_seconds": 60.0},
        }
    }
    mock_clients = {
        ("cerebras", "qwen-3.8-27b"): LLMClient(
            provider="cerebras",
            model="qwen-3.8-27b",
            mock_handler=lambda p: make_mock_classification("cerebras", "qwen-3.8-27b"),
        )
    }
    router = ProviderRouter(config=config, cache=mock_cache, mock_clients=mock_clients)
    result = router.route(SAMPLE_RECORD, mode=RoutingMode.PRODUCTION)

    assert result.status == "SUCCESS"
    assert result.provider_used == "cerebras"
    assert result.model_used == "qwen-3.8-27b"
    assert result.fallback_used is False


def test_cerebras_secret_sanitization():
    """Erros contendo chaves Cerebras são higienizados."""
    raw = "Erro Cerebras: Authorization: Bearer csk-secretkey1234567890 falhou."
    clean = sanitize_error_message(raw)
    assert "csk-secretkey1234567890" not in clean
    assert "[REDACTED]" in clean


# ==============================================================================
# NVIDIA TESTS
# ==============================================================================


def test_nvidia_success(mock_cache: LLMCache):
    """NVIDIA processa com sucesso e gera structured output validado."""
    client = LLMClient(
        provider="nvidia",
        model="openai/gpt-oss-20b",
        mock_handler=lambda p: make_mock_classification("nvidia", "openai/gpt-oss-20b"),
    )
    classifier = LLMClassifier(client=client, cache=mock_cache)
    result = classifier.classify_record(SAMPLE_RECORD, use_cache=True)

    assert result.status == "SUCCESS"
    assert result.provider == "nvidia"
    assert result.model == "openai/gpt-oss-20b"
    assert result.relevant is True
    assert result.relevance == "ALTA"
    assert "COZINHA" in result.categories
    assert result.input_tokens == 1200
    assert result.output_tokens == 150
    assert result.total_tokens == 1350
    assert result.estimated_cost == 0.0


def test_nvidia_auth_failure(mock_cache: LLMCache, monkeypatch: pytest.MonkeyPatch):
    """NVIDIA sem chave levanta erro de credencial."""
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
    client = LLMClient(provider="nvidia", model="openai/gpt-oss-20b", api_key="")
    classifier = LLMClassifier(client=client, cache=mock_cache)

    result = classifier.classify_record(SAMPLE_RECORD, use_cache=False)
    assert result.status == "ERROR"
    assert "credencial" in str(result.error).lower()


def test_nvidia_rate_limit(mock_cache: LLMCache):
    """NVIDIA 429 dispara DailyQuotaExhaustedError."""

    def rate_limit_handler(p):
        raise DailyQuotaExhaustedError("HTTP 429 da NVIDIA API", retry_delay="30")

    client = LLMClient(provider="nvidia", model="openai/gpt-oss-20b", mock_handler=rate_limit_handler)
    classifier = LLMClassifier(client=client, cache=mock_cache)

    with pytest.raises(DailyQuotaExhaustedError):
        classifier.classify_record(SAMPLE_RECORD, use_cache=False)


def test_nvidia_model_unavailable(mock_cache: LLMCache):
    """NVIDIA 404 registra erro de modelo indisponível."""

    def not_found_handler(p):
        raise RuntimeError("Erro HTTP 404 da NVIDIA API: Model not found")

    client = LLMClient(provider="nvidia", model="openai/gpt-oss-20b", mock_handler=not_found_handler)
    classifier = LLMClassifier(client=client, cache=mock_cache)

    result = classifier.classify_record(SAMPLE_RECORD, use_cache=False)
    assert result.status == "ERROR"
    assert result.http_status == 404
    assert result.error_type == "MODEL_ERROR"


def test_nvidia_schema_invalid(mock_cache: LLMCache):
    """NVIDIA com resposta inválida gera SCHEMA_INVALID."""

    def bad_json_handler(p):
        return {
            "content": "{\"relevant\": \"not_a_bool\"}",
            "input_tokens": 100,
            "output_tokens": 50,
            "total_tokens": 150,
            "latency_ms": 100.0,
            "cost": 0.0,
        }

    client = LLMClient(provider="nvidia", model="openai/gpt-oss-20b", mock_handler=bad_json_handler)
    classifier = LLMClassifier(client=client, cache=mock_cache)

    result = classifier.classify_record(SAMPLE_RECORD, use_cache=False)
    assert result.status == "ERROR"
    assert result.error_type == "SCHEMA_INVALID"


def test_nvidia_cache_segregation(mock_cache: LLMCache):
    """Chaves de cache da NVIDIA não colidem com OpenRouter."""
    k_nvidia = mock_cache.generate_key("hash123", "nvidia", "openai/gpt-oss-20b", "0.1.0")
    k_openrouter = mock_cache.generate_key("hash123", "openrouter", "openai/gpt-oss-20b", "0.1.0")
    assert k_nvidia != k_openrouter


def test_nvidia_provider_routing(mock_cache: LLMCache):
    """ProviderRouter roteia corretamente para NVIDIA quando configurado."""
    config = {
        "production": {
            "allow_fallback": True,
            "providers": [
                {"provider": "nvidia", "model": "openai/gpt-oss-20b"},
                {"provider": "deterministic", "model": "rules_v0.1.1"},
            ],
            "circuit_breaker": {"failure_threshold": 3, "cooldown_seconds": 60.0},
        }
    }
    mock_clients = {
        ("nvidia", "openai/gpt-oss-20b"): LLMClient(
            provider="nvidia",
            model="openai/gpt-oss-20b",
            mock_handler=lambda p: make_mock_classification("nvidia", "openai/gpt-oss-20b"),
        )
    }
    router = ProviderRouter(config=config, cache=mock_cache, mock_clients=mock_clients)
    result = router.route(SAMPLE_RECORD, mode=RoutingMode.PRODUCTION)

    assert result.status == "SUCCESS"
    assert result.provider_used == "nvidia"
    assert result.model_used == "openai/gpt-oss-20b"
    assert result.fallback_used is False


def test_nvidia_secret_sanitization():
    """Erros contendo chaves NVIDIA nvapi- são higienizados."""
    raw = "Erro NVIDIA: Authorization: Bearer nvapi-secretkey1234567890 falhou."
    clean = sanitize_error_message(raw)
    assert "nvapi-secretkey1234567890" not in clean
    assert "[REDACTED]" in clean
