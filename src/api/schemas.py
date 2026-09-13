"""Contratos HTTP; regras de classificação permanecem no Opportunity Engine."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str


class StatsResponse(BaseModel):
    total_gold: int
    relevant: int
    irrelevant: int
    high: int
    medium: int
    low: int
    active: int
    future: int
    closed: int
    indeterminate: int
    average_opportunity_score: float | None
    average_confidence_score: float | None
    estimated_ticket_total: float
    categories: dict[str, int]


class OpportunityResponse(BaseModel):
    opportunity_id: str
    source: str
    source_record_id: str
    orgao_nome: str | None = None
    orgao_cnpj: str | None = None
    unidade_nome: str | None = None
    municipio: str | None = None
    uf: str | None = None
    objeto_original: str | None = None
    categories: list[str] = Field(default_factory=list)
    relevance: str
    temporal_status: str
    data_publicacao: str | None = None
    data_abertura_proposta: str | None = None
    data_encerramento_proposta: str | None = None
    valor_total_estimado: float | None = None
    opportunity_score: int
    confidence_score: int
    rules_version: str
    generated_at: str


class OpportunityPage(BaseModel):
    items: list[OpportunityResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class EvidenceResponse(BaseModel):
    opportunity_id: str
    matched_terms: list[dict[str, str]]
    negative_matches: list[dict[str, str]]
    reason_codes: list[str]
    score_breakdown: dict[str, dict[str, Any]]
    lineage: dict[str, Any]


class ReviewItemSummary(BaseModel):
    review_id: str
    source_record_id: str
    orgao_nome: str
    objeto_original: str
    is_reviewed: bool
    reviewed_at: str | None = None


class ReviewSummaryResponse(BaseModel):
    total: int
    reviewed: int
    pending: int
    progress_percent: float
    items: list[ReviewItemSummary]


class ReviewBaseline(BaseModel):
    relevance: str | None = None
    categories: list[str] = Field(default_factory=list)
    opportunity_score: int
    confidence_score: int
    matched_terms: str
    negative_matches: str


class ReviewHumanAnnotation(BaseModel):
    human_relevant: bool | None = None
    human_relevance: str | None = None
    human_categories: list[str] = Field(default_factory=list)
    human_confidence: int | None = None
    human_notes: str = ""
    reviewed_at: str | None = None
    is_reviewed: bool = False


class ReviewDetailResponse(BaseModel):
    review_id: str
    source_record_id: str
    objeto_original: str
    orgao_nome: str
    unidade_nome: str
    municipio: str
    uf: str
    valor_total_estimado: float | None = None
    data_publicacao: str
    baseline: ReviewBaseline | None = None
    human: ReviewHumanAnnotation


class HumanAnnotationUpdate(BaseModel):
    human_relevant: bool
    human_relevance: str = Field(pattern="^(ALTA|MEDIA|BAIXA|IRRELEVANTE)$")
    human_categories: list[str] = Field(default_factory=list)
    human_confidence: int = Field(ge=1, le=5)
    human_notes: str | None = Field(default=None, max_length=1000)

