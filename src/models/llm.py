"""Modelos de dados para classificação LLM e auditoria de inferência (Gate 5)."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal
from pydantic import BaseModel, Field, field_validator

VALID_CATEGORIES = {
    "COZINHA",
    "REFEITORIO",
    "INOX",
    "COCCAO",
    "REFRIGERACAO",
    "EXAUSTAO",
    "LAVAGEM",
    "INFRAESTRUTURA",
    "ALIMENTACAO_COLETIVA",
}


class LLMStructuredOutput(BaseModel):
    """Schema estrito para validação da resposta JSON estruturada gerada pelo LLM."""

    relevant: bool
    relevance: Literal["ALTA", "MEDIA", "BAIXA", "IRRELEVANTE"]
    categories: list[str] = Field(default_factory=list)
    confidence: int = Field(ge=0, le=100)
    reason: str = Field(min_length=3, max_length=2000)

    @field_validator("categories")
    @classmethod
    def validate_categories(cls, cats: list[str]) -> list[str]:
        invalid = [c for c in cats if c not in VALID_CATEGORIES]
        if invalid:
            raise ValueError(f"Categorias inválidas fornecidas pelo modelo: {invalid}. Válidas: {sorted(VALID_CATEGORIES)}")
        return sorted(set(cats))

    @field_validator("relevant")
    @classmethod
    def validate_relevance_consistency(cls, v: bool, values: Any) -> bool:
        return v


@dataclass(frozen=True)
class LLMClassificationResult:
    """Registro completo de auditoria e predição de uma inferência de LLM."""

    review_id: str
    source_record_id: str
    relevant: bool | None
    relevance: str | None
    categories: tuple[str, ...]
    confidence: int | None
    reason: str | None
    provider: str
    model: str
    prompt_version: str
    input_hash: str
    output_raw: str | None
    input_tokens: int
    output_tokens: int
    total_tokens: int
    latency_ms: float
    estimated_cost: float
    status: Literal["SUCCESS", "ERROR", "BLOCKED", "CACHED"]
    error: str | None
    classified_at: str
    reasoning_effort: str | None = None
    temperature: float | None = None
    rate_limit_headers: dict[str, str] | None = None
    attempt_number: int | None = None
    error_type: str | None = None
    http_status: int | None = None
    exception_class: str | None = None
    retry_count: int | None = None
    retry_after: str | None = None
    provider_error_code: str | None = None
    provider_error_message_sanitized: str | None = None
    terminal_error: bool | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["categories"] = list(self.categories)
        return data


@dataclass(frozen=True)
class AttemptTrace:
    """Rastreabilidade de uma tentativa de inferência com provedor específico."""

    provider: str
    model: str
    attempt_number: int
    started_at: str
    finished_at: str
    http_status: int | None
    status: str
    error_type: str | None
    latency_ms: float
    retry_count: int
    error_message_sanitized: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class OperationalClassificationResult:
    """Resultado canônico de inferência operacional com suporte a failover auditável."""

    request_id: str
    provider_requested: str
    model_requested: str
    provider_used: str
    model_used: str
    fallback_used: bool
    fallback_level: int
    fallback_reason: str | None
    providers_attempted: list[str]
    prompt_version: str
    input_hash: str
    relevant: bool | None
    relevance: str | None
    categories: list[str]
    confidence: int | None
    reason: str | None
    input_tokens: int
    output_tokens: int
    total_tokens: int
    latency_ms: float
    estimated_cost: float
    started_at: str
    finished_at: str
    attempt_traces: list[AttemptTrace]
    status: Literal["SUCCESS", "ERROR"] = "SUCCESS"
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["attempt_traces"] = [t.to_dict() if hasattr(t, "to_dict") else t for t in self.attempt_traces]
        return data

