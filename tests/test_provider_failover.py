"""Testes unitários totalmente mockados para a camada Multi-Provider Failover e Circuit Breaker.

Garante ausência total de chamadas reais de rede e conformidade com:
- BENCHMARK_MODE (sem fallback)
- PRODUCTION_MODE (cascata auditável de provedores até determinístico)
- Circuit Breaker (CLOSED -> OPEN -> HALF_OPEN -> CLOSED)
- Rastreabilidade de tentativas (attempt traces, fallback_level, fallback_reason)
- Segregação de cache criptográfico
- Sanitização de credenciais em logs/erros
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from src.classifier.cache import LLMCache
from src.classifier.circuit_breaker import CircuitBreaker, CircuitState
from src.classifier.llm_client import DailyQuotaExhaustedError, LLMClient, MissingCredentialsError
from src.classifier.router import (
    FAILOVER_ELIGIBLE_ERRORS,
    NON_FAILOVER_ERRORS,
    ProviderRouter,
    ProviderStatus,
    RoutingMode,
    classify_error,
    sanitize_error_message,
)

SAMPLE_RECORD = {
    "review_id": "REV-TEST-001",
    "source_record_id": "12345678000199-1-000001/2026",
    "objeto_original": "Aquisição de fogão industrial e refrigerador para cozinha do hospital regional.",
    "orgao_nome": "Hospital Regional",
    "unidade_nome": "Serviço de Nutrição Dietética",
    "municipio": "Campinas",
    "uf": "SP",
    "valor_total_estimado": 52000.0,
    "data_publicacao": "2026-09-12T10:00:00Z",
}


def make_mock_success_response(provider: str, model: str) -> dict[str, Any]:
    content = json.dumps(
        {
            "relevant": True,
            "relevance": "ALTA",
            "categories": ["COZINHA", "COCCAO", "REFRIGERACAO"],
            "confidence": 95,
            "reason": f"Classificado com sucesso pelo provedor {provider} e modelo {model}.",
        }
    )
    return {
        "content": content,
        "input_tokens": 820,
        "output_tokens": 110,
        "total_tokens": 930,
        "latency_ms": 125.0,
        "cost": 0.00005,
    }


class SimulatedClock:
    def __init__(self, initial_time: float = 1000.0):
        self.current_time = initial_time

    def time(self) -> float:
        return self.current_time

    def advance(self, seconds: float) -> None:
        self.current_time += seconds


@pytest.fixture
def mock_cache(tmp_path: Path) -> LLMCache:
    cache_path = tmp_path / "test_llm_cache.json"
    return LLMCache(cache_file=cache_path)



# ==============================================================================
# 1. TESTES BÁSICOS DE CASCATA E FALHA DE PROVEDORES (PRODUCTION_MODE)
# ==============================================================================


def test_openrouter_success(mock_cache: LLMCache):
    """1. OpenRouter tem sucesso direto sem fallback."""
    clock = SimulatedClock()
    mock_clients = {
        ("openrouter", "nvidia/nemotron-3-super-120b-a12b:free"): LLMClient(
            provider="openrouter",
            model="nvidia/nemotron-3-super-120b-a12b:free",
            mock_handler=lambda p: make_mock_success_response("openrouter", "nvidia/nemotron-3-super-120b-a12b:free"),
        )
    }
    router = ProviderRouter(cache=mock_cache, time_fn=clock.time, mock_clients=mock_clients)
    result = router.route(SAMPLE_RECORD, mode=RoutingMode.PRODUCTION)

    assert result.status == "SUCCESS"
    assert result.provider_used == "openrouter"
    assert result.model_used == "nvidia/nemotron-3-super-120b-a12b:free"
    assert result.fallback_used is False
    assert result.fallback_level == 0
    assert result.fallback_reason is None
    assert result.providers_attempted == ["openrouter"]
    assert len(result.attempt_traces) == 1
    assert result.attempt_traces[0].status == "SUCCESS"
    assert result.relevant is True


def test_openrouter_rate_limit_to_gemini_success(mock_cache: LLMCache):
    """2. OpenRouter esgota cota diária (429) -> failover para Gemini com sucesso."""
    clock = SimulatedClock()

    def openrouter_fail(payload):
        raise DailyQuotaExhaustedError("HTTP 429 Daily rate limit reached")

    mock_clients = {
        ("openrouter", "nvidia/nemotron-3-super-120b-a12b:free"): LLMClient(
            provider="openrouter",
            model="nvidia/nemotron-3-super-120b-a12b:free",
            mock_handler=openrouter_fail,
        ),
        ("gemini", "gemini-2.5-flash"): LLMClient(
            provider="gemini",
            model="gemini-2.5-flash",
            mock_handler=lambda p: make_mock_success_response("gemini", "gemini-2.5-flash"),
        ),
    }

    router = ProviderRouter(cache=mock_cache, time_fn=clock.time, mock_clients=mock_clients)
    result = router.route(SAMPLE_RECORD, mode=RoutingMode.PRODUCTION)

    assert result.status == "SUCCESS"
    assert result.provider_used == "gemini"
    assert result.model_used == "gemini-2.5-flash"
    assert result.fallback_used is True
    assert result.fallback_level == 1
    assert "quota" in str(result.fallback_reason).lower() or "rate limit" in str(result.fallback_reason).lower()
    assert result.providers_attempted == ["openrouter", "gemini"]
    assert len(result.attempt_traces) == 2
    assert result.attempt_traces[0].status == "FAILED"
    assert result.attempt_traces[0].error_type == "RATE_LIMITED"
    assert result.attempt_traces[1].status == "SUCCESS"


def test_openrouter_timeout_to_gemini_success(mock_cache: LLMCache):
    """3. OpenRouter sofre timeout -> failover para Gemini com sucesso."""
    clock = SimulatedClock()

    def openrouter_timeout(payload):
        raise TimeoutError("Connection to OpenRouter timed out after 45s")

    mock_clients = {
        ("openrouter", "nvidia/nemotron-3-super-120b-a12b:free"): LLMClient(
            provider="openrouter",
            model="nvidia/nemotron-3-super-120b-a12b:free",
            mock_handler=openrouter_timeout,
        ),
        ("gemini", "gemini-2.5-flash"): LLMClient(
            provider="gemini",
            model="gemini-2.5-flash",
            mock_handler=lambda p: make_mock_success_response("gemini", "gemini-2.5-flash"),
        ),
    }

    router = ProviderRouter(cache=mock_cache, time_fn=clock.time, mock_clients=mock_clients)
    result = router.route(SAMPLE_RECORD, mode=RoutingMode.PRODUCTION)

    assert result.status == "SUCCESS"
    assert result.provider_used == "gemini"
    assert result.fallback_used is True
    assert result.fallback_level == 1
    assert result.attempt_traces[0].error_type == "TIMEOUT"


def test_openrouter_5xx_to_gemini_success(mock_cache: LLMCache):
    """4. OpenRouter retorna 502/5xx -> failover para Gemini com sucesso."""
    clock = SimulatedClock()

    def openrouter_5xx(payload):
        raise RuntimeError("Erro HTTP 502 Bad Gateway do OpenRouter")

    mock_clients = {
        ("openrouter", "nvidia/nemotron-3-super-120b-a12b:free"): LLMClient(
            provider="openrouter",
            model="nvidia/nemotron-3-super-120b-a12b:free",
            mock_handler=openrouter_5xx,
        ),
        ("gemini", "gemini-2.5-flash"): LLMClient(
            provider="gemini",
            model="gemini-2.5-flash",
            mock_handler=lambda p: make_mock_success_response("gemini", "gemini-2.5-flash"),
        ),
    }

    router = ProviderRouter(cache=mock_cache, time_fn=clock.time, mock_clients=mock_clients)
    result = router.route(SAMPLE_RECORD, mode=RoutingMode.PRODUCTION)

    assert result.status == "SUCCESS"
    assert result.provider_used == "gemini"
    assert result.fallback_used is True
    assert result.attempt_traces[0].error_type == "PROVIDER_5XX"


def test_openrouter_rate_limit_and_gemini_rate_limit_to_groq_success(mock_cache: LLMCache):
    """5. OpenRouter e Gemini atingem rate limit -> Groq é acionado e sucede."""
    clock = SimulatedClock()

    mock_clients = {
        ("openrouter", "nvidia/nemotron-3-super-120b-a12b:free"): LLMClient(
            provider="openrouter",
            model="nvidia/nemotron-3-super-120b-a12b:free",
            mock_handler=lambda p: (_ for _ in ()).throw(DailyQuotaExhaustedError("OpenRouter 429")),
        ),
        ("gemini", "gemini-2.5-flash"): LLMClient(
            provider="gemini",
            model="gemini-2.5-flash",
            mock_handler=lambda p: (_ for _ in ()).throw(DailyQuotaExhaustedError("Gemini 429")),
        ),
        ("groq", "openai/gpt-oss-120b"): LLMClient(
            provider="groq",
            model="openai/gpt-oss-120b",
            mock_handler=lambda p: make_mock_success_response("groq", "openai/gpt-oss-120b"),
        ),
    }

    router = ProviderRouter(cache=mock_cache, time_fn=clock.time, mock_clients=mock_clients)
    result = router.route(SAMPLE_RECORD, mode=RoutingMode.PRODUCTION)

    assert result.status == "SUCCESS"
    assert result.provider_used == "groq"
    assert result.fallback_used is True
    assert result.fallback_level == 2
    assert result.providers_attempted == ["openrouter", "gemini", "groq"]
    assert len(result.attempt_traces) == 3


def test_groq_auth_failure_to_openai_success(mock_cache: LLMCache):
    """6. Provedor com falha de credencial (401/MissingCredentials) avança para o próximo."""
    clock = SimulatedClock()

    custom_config = {
        "production": {
            "allow_fallback": True,
            "providers": [
                {"provider": "groq", "model": "openai/gpt-oss-120b"},
                {"provider": "openai", "model": "gpt-5.6-luna"},
                {"provider": "deterministic", "model": "rules_v0.1.1"},
            ],
            "circuit_breaker": {"failure_threshold": 3, "cooldown_seconds": 60.0},
        }
    }

    mock_clients = {
        ("groq", "openai/gpt-oss-120b"): LLMClient(
            provider="groq",
            model="openai/gpt-oss-120b",
            mock_handler=lambda p: (_ for _ in ()).throw(MissingCredentialsError("groq", "GROQ_API_KEY")),
        ),
        ("openai", "gpt-5.6-luna"): LLMClient(
            provider="openai",
            model="gpt-5.6-luna",
            mock_handler=lambda p: make_mock_success_response("openai", "gpt-5.6-luna"),
        ),
    }

    router = ProviderRouter(
        config=custom_config,
        cache=mock_cache,
        time_fn=clock.time,
        mock_clients=mock_clients,
    )
    result = router.route(SAMPLE_RECORD, mode=RoutingMode.PRODUCTION)

    assert result.status == "SUCCESS"
    assert result.provider_used == "openai"
    assert result.fallback_used is True
    assert result.fallback_level == 1
    assert result.attempt_traces[0].error_type == "AUTH_FAILED"


def test_all_llm_providers_fail_to_deterministic_fallback(mock_cache: LLMCache):
    """7. Todos os LLMs falham -> fallback determinístico de regras é acionado."""
    clock = SimulatedClock()

    # Todos os LLMs falham com 500 ou 429
    def failing_handler(payload):
        raise RuntimeError("HTTP 500 Internal Server Error")

    mock_clients = {
        ("openrouter", "nvidia/nemotron-3-super-120b-a12b:free"): LLMClient(
            provider="openrouter",
            model="nvidia/nemotron-3-super-120b-a12b:free",
            mock_handler=failing_handler,
        ),
        ("gemini", "gemini-2.5-flash"): LLMClient(
            provider="gemini",
            model="gemini-2.5-flash",
            mock_handler=failing_handler,
        ),
        ("groq", "openai/gpt-oss-120b"): LLMClient(
            provider="groq",
            model="openai/gpt-oss-120b",
            mock_handler=failing_handler,
        ),
        ("openai", "gpt-5.6-luna"): LLMClient(
            provider="openai",
            model="gpt-5.6-luna",
            mock_handler=failing_handler,
        ),
    }

    router = ProviderRouter(cache=mock_cache, time_fn=clock.time, mock_clients=mock_clients)
    result = router.route(SAMPLE_RECORD, mode=RoutingMode.PRODUCTION)

    assert result.status == "SUCCESS"
    assert result.provider_used == "deterministic"
    assert result.model_used == "rules_v0.1.1"
    assert result.fallback_used is True
    assert result.fallback_level == 4
    assert result.input_tokens == 0
    assert result.output_tokens == 0
    assert result.total_tokens == 0
    assert result.estimated_cost == 0.0
    assert "Classificação determinística" in result.reason
    assert result.relevant is True
    assert "COZINHA" in result.categories
    assert len(result.attempt_traces) == 5


# ==============================================================================
# 2. TESTES DE BENCHMARK MODE (SEM FALLBACK)
# ==============================================================================


def test_benchmark_mode_provider_failure_no_fallback(mock_cache: LLMCache):
    """8. BENCHMARK_MODE: Qualquer falha do provedor configurado NÃO executa fallback."""
    clock = SimulatedClock()

    def openrouter_fail(payload):
        raise DailyQuotaExhaustedError("HTTP 429 Daily rate limit reached")

    mock_clients = {
        ("openrouter", "nvidia/nemotron-3-super-120b-a12b:free"): LLMClient(
            provider="openrouter",
            model="nvidia/nemotron-3-super-120b-a12b:free",
            mock_handler=openrouter_fail,
        ),
        ("gemini", "gemini-2.5-flash"): LLMClient(
            provider="gemini",
            model="gemini-2.5-flash",
            mock_handler=lambda p: make_mock_success_response("gemini", "gemini-2.5-flash"),
        ),
    }

    router = ProviderRouter(cache=mock_cache, time_fn=clock.time, mock_clients=mock_clients)
    result = router.route(SAMPLE_RECORD, mode=RoutingMode.BENCHMARK)

    assert result.status == "ERROR"
    assert result.fallback_used is False
    assert result.fallback_level == 0
    assert result.providers_attempted == ["openrouter"]
    assert len(result.attempt_traces) == 1
    assert result.attempt_traces[0].status == "FAILED"
    assert result.attempt_traces[0].error_type == "RATE_LIMITED"


# ==============================================================================
# 3. TESTES DO CIRCUIT BREAKER (CLOSED -> OPEN -> HALF_OPEN -> CLOSED)
# ==============================================================================


def test_circuit_breaker_opens_after_failures():
    """9. Circuit breaker abre após limiar de falhas consecutivas."""
    clock = SimulatedClock(initial_time=100.0)
    cb = CircuitBreaker(failure_threshold=3, cooldown_seconds=60.0, time_fn=clock.time)

    assert cb.state == CircuitState.CLOSED
    assert cb.can_attempt() is True

    cb.record_failure("TIMEOUT")
    assert cb.state == CircuitState.CLOSED
    cb.record_failure("TIMEOUT")
    assert cb.state == CircuitState.CLOSED

    # 3ª falha atinge o limiar: transição para OPEN
    cb.record_failure("TIMEOUT")
    assert cb.state == CircuitState.OPEN
    assert cb.can_attempt() is False


def test_circuit_breaker_half_open_after_cooldown():
    """10. Circuit breaker transiciona para HALF_OPEN após expiração do cooldown."""
    clock = SimulatedClock(initial_time=100.0)
    cb = CircuitBreaker(failure_threshold=2, cooldown_seconds=30.0, time_fn=clock.time)

    cb.record_failure("500")
    cb.record_failure("500")
    assert cb.state == CircuitState.OPEN
    assert cb.can_attempt() is False

    # Avançar relógio antes do cooldown (20s < 30s)
    clock.advance(20.0)
    assert cb.can_attempt() is False
    assert cb.state == CircuitState.OPEN

    # Avançar relógio além do cooldown (mais 15s -> total 35s > 30s)
    clock.advance(15.0)
    assert cb.can_attempt() is True
    assert cb.state == CircuitState.HALF_OPEN


def test_circuit_breaker_closes_after_successful_probe():
    """11. Circuit breaker fecha após prova bem-sucedida em HALF_OPEN."""
    clock = SimulatedClock(initial_time=100.0)
    cb = CircuitBreaker(failure_threshold=2, cooldown_seconds=30.0, time_fn=clock.time)

    cb.record_failure("429")
    cb.record_failure("429")
    assert cb.state == CircuitState.OPEN

    clock.advance(35.0)
    assert cb.can_attempt() is True
    assert cb.state == CircuitState.HALF_OPEN

    # Prova bem-sucedida fecha o circuito
    cb.record_success()
    assert cb.state == CircuitState.CLOSED
    assert cb.consecutive_failures == 0
    assert cb.can_attempt() is True


def test_circuit_breaker_reopens_on_probe_failure():
    """Se a prova em HALF_OPEN falhar, circuito reabre imediatamente."""
    clock = SimulatedClock(initial_time=100.0)
    cb = CircuitBreaker(failure_threshold=2, cooldown_seconds=30.0, time_fn=clock.time)

    cb.record_failure("429")
    cb.record_failure("429")
    clock.advance(35.0)
    assert cb.can_attempt() is True
    assert cb.state == CircuitState.HALF_OPEN

    # Falha na prova
    cb.record_failure("429")
    assert cb.state == CircuitState.OPEN
    assert cb.can_attempt() is False


# ==============================================================================
# 4. TESTES DE METADADOS, RASTREABILIDADE E CACHE
# ==============================================================================


def test_attempt_trace_and_metadata_completeness(mock_cache: LLMCache):
    """12, 13, 14, 15. Attempt traces e metadados contêm todos os campos exigidos."""
    clock = SimulatedClock()

    mock_clients = {
        ("openrouter", "nvidia/nemotron-3-super-120b-a12b:free"): LLMClient(
            provider="openrouter",
            model="nvidia/nemotron-3-super-120b-a12b:free",
            mock_handler=lambda p: (_ for _ in ()).throw(TimeoutError("Timeout simulado")),
        ),
        ("gemini", "gemini-2.5-flash"): LLMClient(
            provider="gemini",
            model="gemini-2.5-flash",
            mock_handler=lambda p: make_mock_success_response("gemini", "gemini-2.5-flash"),
        ),
    }

    router = ProviderRouter(cache=mock_cache, time_fn=clock.time, mock_clients=mock_clients)
    result = router.route(SAMPLE_RECORD, mode=RoutingMode.PRODUCTION, request_id="req_test_abc123")

    # Campos canônicos do resultado operacional
    assert result.request_id == "req_test_abc123"
    assert result.provider_requested == "openrouter"
    assert result.model_requested == "nvidia/nemotron-3-super-120b-a12b:free"
    assert result.provider_used == "gemini"
    assert result.model_used == "gemini-2.5-flash"
    assert result.fallback_used is True
    assert result.fallback_level == 1
    assert "timeout" in result.fallback_reason.lower()
    assert result.prompt_version == "0.1.0"
    assert len(result.input_hash) == 64
    assert result.latency_ms > 0

    # Validação estrutural do AttemptTrace
    assert len(result.attempt_traces) == 2
    t0 = result.attempt_traces[0]
    assert t0.provider == "openrouter"
    assert t0.model == "nvidia/nemotron-3-super-120b-a12b:free"
    assert t0.attempt_number == 1
    assert t0.status == "FAILED"
    assert t0.error_type == "TIMEOUT"
    assert t0.started_at is not None
    assert t0.finished_at is not None

    t1 = result.attempt_traces[1]
    assert t1.provider == "gemini"
    assert t1.model == "gemini-2.5-flash"
    assert t1.attempt_number == 2
    assert t1.status == "SUCCESS"


def test_cache_segregation_by_provider_and_model(mock_cache: LLMCache):
    """16. Cache é estritamente segregado por input_hash + provider + model + prompt_version."""
    # Criar duas chaves para o mesmo input_hash mas provedores diferentes
    key_openrouter = mock_cache.generate_key("abc123hash", "openrouter", "nvidia/nemotron", "0.1.0")
    key_gemini = mock_cache.generate_key("abc123hash", "gemini", "gemini-2.5-flash", "0.1.0")


    assert key_openrouter != key_gemini

    mock_cache.set(key_openrouter, {"result": "from_openrouter"})
    mock_cache.set(key_gemini, {"result": "from_gemini"})

    assert mock_cache.get(key_openrouter)["result"] == "from_openrouter"
    assert mock_cache.get(key_gemini)["result"] == "from_gemini"


def test_no_api_keys_in_logs_or_traces():
    """17. Nenhuma chave de API ou segredo vaza para os traces de erro ou logs."""
    leaked_message = (
        "Erro na chamada: Authorization: Bearer sk-live-supersecrettoken1234567890 failed. "
        "Key parameter: api_key=gsk_mygroqsecretkeyabc123456789"
    )
    sanitized = sanitize_error_message(leaked_message)

    assert "sk-live-supersecrettoken1234567890" not in sanitized
    assert "gsk_mygroqsecretkeyabc123456789" not in sanitized
    assert "[REDACTED]" in sanitized


def test_non_failover_errors_do_not_cascade(mock_cache: LLMCache):
    """Erros de schema ou validação de dados NÃO realizam fallback automático."""
    clock = SimulatedClock()

    def schema_fail(payload):
        # Retorna JSON que viola o schema estrito (campo obrigatório ausente)
        return {
            "content": json.dumps({"relevant": True, "relevance": "INVALIDO"}),
            "input_tokens": 100,
            "output_tokens": 50,
            "total_tokens": 150,
            "latency_ms": 50.0,
            "cost": 0.0,
        }

    mock_clients = {
        ("openrouter", "nvidia/nemotron-3-super-120b-a12b:free"): LLMClient(
            provider="openrouter",
            model="nvidia/nemotron-3-super-120b-a12b:free",
            mock_handler=schema_fail,
        ),
        ("gemini", "gemini-2.5-flash"): LLMClient(
            provider="gemini",
            model="gemini-2.5-flash",
            mock_handler=lambda p: make_mock_success_response("gemini", "gemini-2.5-flash"),
        ),
    }

    router = ProviderRouter(cache=mock_cache, time_fn=clock.time, mock_clients=mock_clients)
    result = router.route(SAMPLE_RECORD, mode=RoutingMode.PRODUCTION)

    # Não deve haver cascata para Gemini diante de erro de schema
    assert result.status == "ERROR"
    assert result.fallback_used is False
    assert result.providers_attempted == ["openrouter"]
    assert result.attempt_traces[0].error_type == "SCHEMA_ERROR"
