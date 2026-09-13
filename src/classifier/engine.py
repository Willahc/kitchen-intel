"""Orquestrador de classificação e validação estruturada com LLM (Gate 5).

Garante ausência total de Data Leakage:
- Filtra estritamente apenas os 7 campos públicos permitidos.
- Bloqueia qualquer metadado derivado do baseline ou anotações humanas.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from src.classifier.cache import LLMCache
from src.classifier.llm_client import DailyQuotaExhaustedError, LLMClient
from src.models.llm import LLMClassificationResult, LLMStructuredOutput

PERMITTED_INPUT_FIELDS = (
    "objeto_original",
    "orgao_nome",
    "unidade_nome",
    "municipio",
    "uf",
    "valor_total_estimado",
    "data_publicacao",
)

FORBIDDEN_PATTERNS = (
    "human_",
    "baseline_",
    "matched_terms",
    "negative_matches",
    "ground_truth",
)


class LLMClassifier:
    """Motor de inferência e validação para classificação B2B de compras públicas."""

    def __init__(
        self,
        client: LLMClient,
        cache: LLMCache | None = None,
        prompt_path: Path | None = None,
        prompt_version: str = "0.1.0",
        temperature: float = 0.0,
        max_schema_retries: int = 1,
    ) -> None:
        self.client = client
        self.cache = cache or LLMCache()
        self.prompt_path = prompt_path or Path("prompts/classifier_v0.1.0.txt")
        self.prompt_version = prompt_version
        self.temperature = temperature
        self.max_schema_retries = max_schema_retries

        if not self.prompt_path.exists():
            raise FileNotFoundError(f"Arquivo de prompt não encontrado: {self.prompt_path}")
        self.system_prompt = self.prompt_path.read_text(encoding="utf-8")

    @staticmethod
    def prepare_input(record: dict[str, Any]) -> tuple[dict[str, Any], str]:
        """Filtra estritamente os campos permitidos e calcula o hash determinístico da entrada."""
        clean_input: dict[str, Any] = {}
        for field in PERMITTED_INPUT_FIELDS:
            clean_input[field] = record.get(field)

        # Verificação rigorosa contra vazamento de dados
        for key in clean_input:
            if any(forbidden in key.lower() for forbidden in FORBIDDEN_PATTERNS):
                raise ValueError(f"Campo proibido detectado no payload do LLM: {key}")

        canonical_bytes = json.dumps(clean_input, sort_keys=True, ensure_ascii=False).encode("utf-8")
        input_hash = hashlib.sha256(canonical_bytes).hexdigest()
        return clean_input, input_hash

    def classify_record(self, record: dict[str, Any], use_cache: bool = True) -> LLMClassificationResult:
        """Classifica um registro público garantindo structured output, cache e auditoria."""
        review_id = str(record.get("review_id", ""))
        source_record_id = str(record.get("source_record_id", ""))
        clean_input, input_hash = self.prepare_input(record)

        cache_key = self.cache.generate_key(
            input_hash=input_hash,
            provider=self.client.provider,
            model=self.client.model,
            prompt_version=self.prompt_version,
        )

        if use_cache:
            cached = self.cache.get(cache_key)
            if cached:
                cached_data = dict(cached)
                cached_data["status"] = "CACHED"
                cached_data["review_id"] = review_id
                cached_data["source_record_id"] = source_record_id
                return LLMClassificationResult(
                    review_id=review_id,
                    source_record_id=source_record_id,
                    relevant=cached_data.get("relevant"),
                    relevance=cached_data.get("relevance"),
                    categories=tuple(cached_data.get("categories", ())),
                    confidence=cached_data.get("confidence"),
                    reason=cached_data.get("reason"),
                    provider=cached_data.get("provider", self.client.provider),
                    model=cached_data.get("model", self.client.model),
                    prompt_version=cached_data.get("prompt_version", self.prompt_version),
                    input_hash=input_hash,
                    output_raw=cached_data.get("output_raw"),
                    input_tokens=cached_data.get("input_tokens", 0),
                    output_tokens=cached_data.get("output_tokens", 0),
                    total_tokens=cached_data.get("total_tokens", 0),
                    latency_ms=cached_data.get("latency_ms", 0.0),
                    estimated_cost=cached_data.get("estimated_cost", 0.0),
                    status="CACHED",
                    error=None,
                    classified_at=cached_data.get("classified_at", datetime.now(timezone.utc).isoformat()),
                    reasoning_effort=cached_data.get("reasoning_effort"),
                    temperature=cached_data.get("temperature"),
                    rate_limit_headers=cached_data.get("rate_limit_headers"),
                )

        user_prompt = (
            "Analise a seguinte contratação pública e gere a classificação estruturada em JSON:\n\n"
            + json.dumps(clean_input, indent=2, ensure_ascii=False)
        )

        now_iso = datetime.now(timezone.utc).isoformat()
        retries_done = 0
        current_user_prompt = user_prompt
        last_error: str | None = None
        last_exception: Exception | None = None
        raw_output: str | None = None
        total_in_tokens = 0
        total_out_tokens = 0
        total_latency = 0.0
        total_cost = 0.0

        while retries_done <= self.max_schema_retries:
            try:
                response = self.client.complete(
                    system_prompt=self.system_prompt,
                    user_prompt=current_user_prompt,
                    temperature=self.temperature,
                )
                raw_output = response["content"]
                total_in_tokens += response["input_tokens"]
                total_out_tokens += response["output_tokens"]
                total_latency += response["latency_ms"]
                total_cost += response["cost"]

                structured = LLMStructuredOutput.model_validate_json(raw_output)

                result = LLMClassificationResult(
                    review_id=review_id,
                    source_record_id=source_record_id,
                    relevant=structured.relevant,
                    relevance=structured.relevance,
                    categories=tuple(structured.categories),
                    confidence=structured.confidence,
                    reason=structured.reason,
                    provider=self.client.provider,
                    model=self.client.model,
                    prompt_version=self.prompt_version,
                    input_hash=input_hash,
                    output_raw=raw_output,
                    input_tokens=total_in_tokens,
                    output_tokens=total_out_tokens,
                    total_tokens=total_in_tokens + total_out_tokens,
                    latency_ms=round(total_latency, 2),
                    estimated_cost=round(total_cost, 8),
                    status="SUCCESS",
                    error=None,
                    classified_at=now_iso,
                    reasoning_effort=self.client.reasoning_effort,
                    temperature=self.temperature,
                    rate_limit_headers=response.get("rate_limit_headers"),
                )

                # Gravar em cache
                if use_cache:
                    self.cache.set(cache_key, result.to_dict())

                return result

            except (ValidationError, json.JSONDecodeError) as err:
                last_error = f"Erro de validação de schema: {err}"
                last_exception = err
                retries_done += 1
                if retries_done <= self.max_schema_retries:
                    current_user_prompt = (
                        user_prompt
                        + f"\n\n[ATENÇÃO: A resposta anterior foi inválida devido ao seguinte erro:\n{err}\n"
                        + "Corrija e retorne rigorosamente apenas o JSON válido.]"
                    )
            except DailyQuotaExhaustedError:
                raise
            except Exception as err:
                last_error = f"Erro de inferência: {err}"
                last_exception = err
                break

        error_text = str(last_exception or "")
        status_match = re.search(r"HTTP\s+(\d{3})", error_text, re.IGNORECASE)
        http_status = int(status_match.group(1)) if status_match else None
        if isinstance(last_exception, (ValidationError, json.JSONDecodeError)):
            error_type = "SCHEMA_INVALID"
        elif http_status is not None and 500 <= http_status <= 599:
            error_type = "PROVIDER_5XX"
        elif isinstance(last_exception, TimeoutError) or "timeout" in error_text.lower():
            error_type = "TIMEOUT"
        elif isinstance(last_exception, (ConnectionError,)) or any(x in error_text.lower() for x in ("connect", "network", "dns")):
            error_type = "NETWORK_TRANSIENT"
        elif http_status is not None:
            error_type = "MODEL_ERROR" if http_status in (400, 404) else "UNKNOWN"
        else:
            error_type = "UNKNOWN"
        sanitized = re.sub(r"(?i)(authorization|api[-_ ]?key|bearer)\s*[:=]\s*\S+", "[REDACTED]", error_text)
        sanitized = sanitized[:500]

        return LLMClassificationResult(
            review_id=review_id,
            source_record_id=source_record_id,
            relevant=None,
            relevance=None,
            categories=(),
            confidence=None,
            reason=None,
            provider=self.client.provider,
            model=self.client.model,
            prompt_version=self.prompt_version,
            input_hash=input_hash,
            output_raw=raw_output,
            input_tokens=total_in_tokens,
            output_tokens=total_out_tokens,
            total_tokens=total_in_tokens + total_out_tokens,
            latency_ms=round(total_latency, 2),
            estimated_cost=round(total_cost, 8),
            status="ERROR",
            error=last_error,
            classified_at=now_iso,
            reasoning_effort=self.client.reasoning_effort,
            temperature=self.temperature,
            rate_limit_headers=None,
            attempt_number=retries_done + 1,
            error_type=error_type,
            http_status=http_status,
            exception_class=type(last_exception).__name__ if last_exception else None,
            retry_count=retries_done,
            provider_error_message_sanitized=sanitized or None,
            terminal_error=True,
        )
