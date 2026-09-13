"""Roteador de inferência e cascata de provedores LLM (Multi-Provider Failover).

Suporta dois modos operacionais estritos:
- BENCHMARK_MODE: Provedor e modelo fixos, sem fallback; qualquer erro encerra a chamada
  para preservar integridade científica.
- PRODUCTION_MODE: Cascata declarativa entre provedores prioritários, com fallback
  auditável e Circuit Breaker por provedor, culminando no baseline determinístico.
"""

from __future__ import annotations

import json
import re
import time
import uuid
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable

from src.classifier.cache import LLMCache
from src.classifier.circuit_breaker import CircuitBreaker, CircuitState
from src.classifier.engine import LLMClassifier
from src.classifier.llm_client import DailyQuotaExhaustedError, LLMClient, MissingCredentialsError
from src.models.llm import AttemptTrace, OperationalClassificationResult
from src.opportunity.classifier import classify_text


class RoutingMode(str, Enum):
    """Modos de roteamento do classificador."""

    BENCHMARK = "benchmark"
    PRODUCTION = "production"


class ProviderStatus(str, Enum):
    """Status operacional do provedor."""

    AVAILABLE = "AVAILABLE"
    RATE_LIMITED = "RATE_LIMITED"
    AUTH_FAILED = "AUTH_FAILED"
    NO_CREDITS = "NO_CREDITS"
    MODEL_UNAVAILABLE = "MODEL_UNAVAILABLE"
    TIMEOUT = "TIMEOUT"
    NETWORK_ERROR = "NETWORK_ERROR"
    SCHEMA_ERROR = "SCHEMA_ERROR"
    PROVIDER_5XX = "PROVIDER_5XX"
    CIRCUIT_OPEN = "CIRCUIT_OPEN"
    UNKNOWN = "UNKNOWN"


# Erros elegíveis para fallback operacional em PRODUCTION_MODE
FAILOVER_ELIGIBLE_ERRORS = {
    ProviderStatus.RATE_LIMITED.value,
    ProviderStatus.TIMEOUT.value,
    ProviderStatus.NETWORK_ERROR.value,
    ProviderStatus.MODEL_UNAVAILABLE.value,
    ProviderStatus.PROVIDER_5XX.value,
    ProviderStatus.AUTH_FAILED.value,
    ProviderStatus.NO_CREDITS.value,
    ProviderStatus.CIRCUIT_OPEN.value,
}

# Erros que NÃO devem disparar fallback automático
NON_FAILOVER_ERRORS = {
    ProviderStatus.SCHEMA_ERROR.value,
    "INVALID_REQUEST",
    "DATA_VALIDATION_ERROR",
}


def sanitize_error_message(text: str | None) -> str | None:
    """Remove qualquer chave de API, token ou credencial de mensagens de erro."""
    if not text:
        return None
    sanitized = re.sub(
        r"(?i)(authorization\s*:\s*bearer\s+\S+|authorization\s*[:=]\s*\S+|api[-_ ]?key\s*[:=]\s*\S+|bearer\s+\S+|token\s*[:=]\s*\S+)",
        "[REDACTED]",
        text,
    )
    sanitized = re.sub(
        r"\b(sk-[a-zA-Z0-9_-]{8,}|gsk_[a-zA-Z0-9_-]{8,}|aior-[a-zA-Z0-9_-]{8,}|nvapi-[a-zA-Z0-9_-]{8,}|csk-[a-zA-Z0-9_-]{8,})\b",
        "[REDACTED]",
        sanitized,
    )
    return sanitized[:500]



def classify_error(
    err_text: str,
    http_status: int | None = None,
    exc: Exception | None = None,
    exception_class: str | None = None,
) -> str:
    """Classifica a categoria canônica do erro de inferência."""
    err_lower = err_text.lower()
    exc_name = (exception_class or (type(exc).__name__ if exc else "")).lower()

    if (
        http_status == 429
        or "429" in err_lower
        or "quota" in err_lower
        or "rate limit" in err_lower
        or isinstance(exc, DailyQuotaExhaustedError)
        or "dailyquotaexhausted" in exc_name
    ):
        return ProviderStatus.RATE_LIMITED.value

    if (
        http_status in (401, 403)
        or "401" in err_lower
        or "403" in err_lower
        or "unauthorized" in err_lower
        or "forbidden" in err_lower
        or "credencial" in err_lower
        or "missingcredentials" in exc_name
        or isinstance(exc, MissingCredentialsError)
    ):
        return ProviderStatus.AUTH_FAILED.value

    if "credit" in err_lower or "balance" in err_lower or "exhausted" in err_lower:
        return ProviderStatus.NO_CREDITS.value

    if (
        isinstance(exc, TimeoutError)
        or "timeouterror" in exc_name
        or "timeout" in err_lower
        or "timed out" in err_lower
    ):
        return ProviderStatus.TIMEOUT.value

    if http_status == 404 or "not found" in err_lower or "model_unavailable" in err_lower:
        return ProviderStatus.MODEL_UNAVAILABLE.value

    if (
        isinstance(exc, ConnectionError)
        or "connection" in exc_name
        or any(x in err_lower for x in ("connection", "connect", "network", "dns"))
    ):
        return ProviderStatus.NETWORK_ERROR.value

    if (
        (http_status is not None and 500 <= http_status <= 599)
        or any(f"http {code}" in err_lower for code in (500, 502, 503, 504))
        or "502" in err_lower
        or "503" in err_lower
    ):
        return ProviderStatus.PROVIDER_5XX.value

    if (
        "validation" in err_lower
        or "schema" in err_lower
        or "jsondecode" in err_lower
        or "validationerror" in exc_name
    ):
        return ProviderStatus.SCHEMA_ERROR.value

    return ProviderStatus.UNKNOWN.value



class ProviderRouter:
    """Orquestrador de cascata multi-provedor com Circuit Breaker e rastreabilidade."""

    def __init__(
        self,
        config_path: Path | None = None,
        config: dict[str, Any] | None = None,
        cache: LLMCache | None = None,
        prompt_path: Path | None = None,
        prompt_version: str = "0.1.0",
        temperature: float = 0.0,
        time_fn: Callable[[], float] | None = None,
        mock_clients: dict[tuple[str, str], LLMClient] | None = None,
        rules_path: Path | None = None,
    ) -> None:
        self.config_path = config_path or Path("config/provider_routing.json")
        if config is not None:
            self.config = config
        elif self.config_path.exists():
            self.config = json.loads(self.config_path.read_text(encoding="utf-8"))
        else:
            self.config = {
                "default_mode": "benchmark",
                "benchmark": {"allow_fallback": False, "provider": "openrouter", "model": "nvidia/nemotron-3-super-120b-a12b:free"},
                "production": {
                    "allow_fallback": True,
                    "providers": [
                        {"provider": "openrouter", "model": "nvidia/nemotron-3-super-120b-a12b:free"},
                        {"provider": "gemini", "model": "gemini-2.5-flash"},
                        {"provider": "groq", "model": "openai/gpt-oss-120b"},
                        {"provider": "openai", "model": "gpt-5.6-luna"},
                        {"provider": "deterministic", "model": "rules_v0.1.1"},
                    ],
                    "circuit_breaker": {"failure_threshold": 3, "cooldown_seconds": 60.0},
                },
            }

        self.cache = cache or LLMCache()
        self.prompt_path = prompt_path or Path("prompts/classifier_v0.1.0.txt")
        self.prompt_version = prompt_version
        self.temperature = temperature
        self.time_fn = time_fn or time.time
        self.mock_clients = mock_clients or {}

        rules_file = rules_path or Path("config/opportunity_rules.json")
        if rules_file.exists():
            self.opportunity_rules = json.loads(rules_file.read_text(encoding="utf-8"))
        else:
            self.opportunity_rules = {"rules_version": "0.1.1"}

        # Instanciar Circuit Breakers por provedor
        cb_cfg = self.config.get("production", {}).get("circuit_breaker", {})
        failure_threshold = cb_cfg.get("failure_threshold", 3)
        cooldown_seconds = cb_cfg.get("cooldown_seconds", 60.0)

        self.circuit_breakers: dict[str, CircuitBreaker] = {}
        all_providers = {
            p["provider"]
            for p in self.config.get("production", {}).get("providers", [])
            if p["provider"] != "deterministic"
        }
        benchmark_provider = self.config.get("benchmark", {}).get("provider")
        if benchmark_provider and benchmark_provider != "deterministic":
            all_providers.add(benchmark_provider)

        for prov in all_providers:
            self.circuit_breakers[prov] = CircuitBreaker(
                failure_threshold=failure_threshold,
                cooldown_seconds=cooldown_seconds,
                time_fn=self.time_fn,
            )

    def _get_client(self, provider: str, model: str) -> LLMClient:
        key = (provider, model)
        if key in self.mock_clients:
            return self.mock_clients[key]
        return LLMClient(provider=provider, model=model)

    def _execute_deterministic_fallback(
        self,
        record: dict[str, Any],
        model_name: str,
        attempt_number: int,
    ) -> tuple[dict[str, Any], AttemptTrace]:
        """Executa classificação baseada em regras sem chamada de rede."""
        started_at = datetime.now(timezone.utc).isoformat()
        t0 = self.time_fn()
        obj_text = record.get("objeto_original")
        det_result = classify_text(obj_text, self.opportunity_rules)
        latency_ms = round((self.time_fn() - t0) * 1000, 2)
        finished_at = datetime.now(timezone.utc).isoformat()

        relevance = det_result["relevance"]
        relevant = relevance in ("ALTA", "MEDIA", "BAIXA")
        categories = list(det_result["categories"])
        rules_version = self.opportunity_rules.get("rules_version", "0.1.1")
        reason = f"Classificação determinística via regras {rules_version}: {list(det_result.get('reason_codes', []))}"

        trace = AttemptTrace(
            provider="deterministic",
            model=model_name,
            attempt_number=attempt_number,
            started_at=started_at,
            finished_at=finished_at,
            http_status=None,
            status="SUCCESS",
            error_type=None,
            latency_ms=latency_ms,
            retry_count=0,
            error_message_sanitized=None,
        )

        res_data = {
            "relevant": relevant,
            "relevance": relevance,
            "categories": categories,
            "confidence": 100,
            "reason": reason,
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "latency_ms": latency_ms,
            "estimated_cost": 0.0,
        }
        return res_data, trace

    def route(
        self,
        record: dict[str, Any],
        mode: RoutingMode | str = RoutingMode.PRODUCTION,
        request_id: str | None = None,
        use_cache: bool = True,
    ) -> OperationalClassificationResult:
        """Executa a rota de inferência com observabilidade completa e failover auditável."""
        req_id = request_id or f"req_{uuid.uuid4().hex[:12]}"
        mode_str = mode.value if isinstance(mode, RoutingMode) else str(mode).lower()

        clean_input, input_hash = LLMClassifier.prepare_input(record)
        started_iso = datetime.now(timezone.utc).isoformat()

        if mode_str == RoutingMode.BENCHMARK.value:
            targets = [self.config.get("benchmark", {})]
            allow_fallback = False
        else:
            targets = self.config.get("production", {}).get("providers", [])
            allow_fallback = self.config.get("production", {}).get("allow_fallback", True)

        if not targets:
            raise ValueError(f"Nenhum provedor configurado para o modo '{mode_str}'.")

        provider_requested = targets[0].get("provider", "unknown")
        model_requested = targets[0].get("model", "unknown")

        providers_attempted: list[str] = []
        attempt_traces: list[AttemptTrace] = []
        last_failure_reason: str | None = None

        for lvl, target in enumerate(targets):
            provider = target.get("provider", "unknown")
            model = target.get("model", "unknown")
            providers_attempted.append(provider)
            attempt_num = len(attempt_traces) + 1

            # 1. Fallback Determinístico
            if provider == "deterministic":
                det_data, trace = self._execute_deterministic_fallback(record, model, attempt_num)
                attempt_traces.append(trace)
                finished_iso = datetime.now(timezone.utc).isoformat()

                return OperationalClassificationResult(
                    request_id=req_id,
                    provider_requested=provider_requested,
                    model_requested=model_requested,
                    provider_used=provider,
                    model_used=model,
                    fallback_used=(lvl > 0),
                    fallback_level=lvl,
                    fallback_reason=last_failure_reason if lvl > 0 else None,
                    providers_attempted=providers_attempted,
                    prompt_version=self.prompt_version,
                    input_hash=input_hash,
                    relevant=det_data["relevant"],
                    relevance=det_data["relevance"],
                    categories=det_data["categories"],
                    confidence=det_data["confidence"],
                    reason=det_data["reason"],
                    input_tokens=det_data["input_tokens"],
                    output_tokens=det_data["output_tokens"],
                    total_tokens=det_data["total_tokens"],
                    latency_ms=det_data["latency_ms"],
                    estimated_cost=det_data["estimated_cost"],
                    started_at=started_iso,
                    finished_at=finished_iso,
                    attempt_traces=attempt_traces,
                    status="SUCCESS",
                    error=None,
                )

            # 2. Provedor LLM: Checar Circuit Breaker
            cb = self.circuit_breakers.get(provider)
            if cb and not cb.can_attempt():
                now_str = datetime.now(timezone.utc).isoformat()
                trace = AttemptTrace(
                    provider=provider,
                    model=model,
                    attempt_number=attempt_num,
                    started_at=now_str,
                    finished_at=now_str,
                    http_status=None,
                    status="SKIPPED",
                    error_type=ProviderStatus.CIRCUIT_OPEN.value,
                    latency_ms=0.0,
                    retry_count=0,
                    error_message_sanitized=f"Circuit Breaker for {provider} is {cb.state.value}",
                )
                attempt_traces.append(trace)
                last_failure_reason = f"{provider} circuit breaker is OPEN"

                if not allow_fallback:
                    break
                continue

            # 3. Provedor LLM: Execução
            attempt_started = datetime.now(timezone.utc).isoformat()
            t0 = self.time_fn()
            client = self._get_client(provider, model)

            classifier = LLMClassifier(
                client=client,
                cache=self.cache,
                prompt_path=self.prompt_path,
                prompt_version=self.prompt_version,
                temperature=self.temperature,
            )

            try:
                llm_res = classifier.classify_record(record, use_cache=use_cache)
                latency_ms = round((self.time_fn() - t0) * 1000, 2)
                attempt_finished = datetime.now(timezone.utc).isoformat()

                if llm_res.status in ("SUCCESS", "CACHED"):
                    if cb:
                        cb.record_success()

                    trace = AttemptTrace(
                        provider=provider,
                        model=model,
                        attempt_number=attempt_num,
                        started_at=attempt_started,
                        finished_at=attempt_finished,
                        http_status=200,
                        status=llm_res.status,
                        error_type=None,
                        latency_ms=latency_ms,
                        retry_count=0,
                        error_message_sanitized=None,
                    )
                    attempt_traces.append(trace)
                    finished_iso = datetime.now(timezone.utc).isoformat()

                    return OperationalClassificationResult(
                        request_id=req_id,
                        provider_requested=provider_requested,
                        model_requested=model_requested,
                        provider_used=provider,
                        model_used=model,
                        fallback_used=(lvl > 0),
                        fallback_level=lvl,
                        fallback_reason=last_failure_reason if lvl > 0 else None,
                        providers_attempted=providers_attempted,
                        prompt_version=self.prompt_version,
                        input_hash=input_hash,
                        relevant=llm_res.relevant,
                        relevance=llm_res.relevance,
                        categories=list(llm_res.categories),
                        confidence=llm_res.confidence,
                        reason=llm_res.reason,
                        input_tokens=llm_res.input_tokens,
                        output_tokens=llm_res.output_tokens,
                        total_tokens=llm_res.total_tokens,
                        latency_ms=llm_res.latency_ms or latency_ms,
                        estimated_cost=llm_res.estimated_cost,
                        started_at=started_iso,
                        finished_at=finished_iso,
                        attempt_traces=attempt_traces,
                        status="SUCCESS",
                        error=None,
                    )
                else:
                    # Falha reportada pelo classificador
                    err_msg = sanitize_error_message(llm_res.error)
                    err_type = classify_error(
                        err_msg or "",
                        http_status=llm_res.http_status,
                        exception_class=llm_res.exception_class,
                    )
                    if cb:

                        cb.record_failure(err_type)

                    trace = AttemptTrace(
                        provider=provider,
                        model=model,
                        attempt_number=attempt_num,
                        started_at=attempt_started,
                        finished_at=attempt_finished,
                        http_status=llm_res.http_status,
                        status="FAILED",
                        error_type=err_type,
                        latency_ms=latency_ms,
                        retry_count=llm_res.retry_count or 0,
                        error_message_sanitized=err_msg,
                    )
                    attempt_traces.append(trace)
                    last_failure_reason = f"{provider} failed: {err_type} ({err_msg})"

                    if not allow_fallback or err_type in NON_FAILOVER_ERRORS:
                        break

            except DailyQuotaExhaustedError as err:
                latency_ms = round((self.time_fn() - t0) * 1000, 2)
                attempt_finished = datetime.now(timezone.utc).isoformat()
                err_type = ProviderStatus.RATE_LIMITED.value
                if cb:
                    cb.record_failure(err_type)

                trace = AttemptTrace(
                    provider=provider,
                    model=model,
                    attempt_number=attempt_num,
                    started_at=attempt_started,
                    finished_at=attempt_finished,
                    http_status=429,
                    status="FAILED",
                    error_type=err_type,
                    latency_ms=latency_ms,
                    retry_count=0,
                    error_message_sanitized=sanitize_error_message(str(err)),
                )
                attempt_traces.append(trace)
                last_failure_reason = f"{provider} quota exhausted (429)"

                if not allow_fallback:
                    break

            except MissingCredentialsError as err:
                latency_ms = round((self.time_fn() - t0) * 1000, 2)
                attempt_finished = datetime.now(timezone.utc).isoformat()
                err_type = ProviderStatus.AUTH_FAILED.value
                if cb:
                    cb.record_failure(err_type)

                trace = AttemptTrace(
                    provider=provider,
                    model=model,
                    attempt_number=attempt_num,
                    started_at=attempt_started,
                    finished_at=attempt_finished,
                    http_status=401,
                    status="FAILED",
                    error_type=err_type,
                    latency_ms=latency_ms,
                    retry_count=0,
                    error_message_sanitized=sanitize_error_message(str(err)),
                )
                attempt_traces.append(trace)
                last_failure_reason = f"{provider} credentials missing"

                if not allow_fallback:
                    break

            except Exception as err:
                latency_ms = round((self.time_fn() - t0) * 1000, 2)
                attempt_finished = datetime.now(timezone.utc).isoformat()
                raw_err = str(err)
                status_match = re.search(r"HTTP\s+(\d{3})", raw_err, re.IGNORECASE)
                http_st = int(status_match.group(1)) if status_match else None
                err_type = classify_error(raw_err, http_status=http_st, exc=err)

                if cb:
                    cb.record_failure(err_type)

                trace = AttemptTrace(
                    provider=provider,
                    model=model,
                    attempt_number=attempt_num,
                    started_at=attempt_started,
                    finished_at=attempt_finished,
                    http_status=http_st,
                    status="FAILED",
                    error_type=err_type,
                    latency_ms=latency_ms,
                    retry_count=0,
                    error_message_sanitized=sanitize_error_message(raw_err),
                )
                attempt_traces.append(trace)
                last_failure_reason = f"{provider} error: {err_type}"

                if not allow_fallback or err_type in NON_FAILOVER_ERRORS:
                    break

        # Se esgotou todas as tentativas sem sucesso
        finished_iso = datetime.now(timezone.utc).isoformat()
        return OperationalClassificationResult(
            request_id=req_id,
            provider_requested=provider_requested,
            model_requested=model_requested,
            provider_used=providers_attempted[-1] if providers_attempted else "none",
            model_used="none",
            fallback_used=False,
            fallback_level=0,
            fallback_reason=last_failure_reason,
            providers_attempted=providers_attempted,
            prompt_version=self.prompt_version,
            input_hash=input_hash,
            relevant=None,
            relevance=None,
            categories=[],
            confidence=None,
            reason=None,
            input_tokens=0,
            output_tokens=0,
            total_tokens=0,
            latency_ms=0.0,
            estimated_cost=0.0,
            started_at=started_iso,
            finished_at=finished_iso,
            attempt_traces=attempt_traces,
            status="ERROR",
            error=last_failure_reason or "Todas as tentativas de provedores falharam.",
        )
