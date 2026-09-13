"""Aplicação FastAPI somente leitura sobre Gold JSONL."""

from __future__ import annotations

import math
import os
from collections import Counter
from pathlib import Path
from typing import Annotated, Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from fastapi.responses import PlainTextResponse

from src.api.repository import GoldRepository
from src.api.review_repository import ReviewRepository, VALID_CATEGORIES
from src.api.schemas import (
    EvidenceResponse,
    HealthResponse,
    HumanAnnotationUpdate,
    OpportunityPage,
    OpportunityResponse,
    ReviewDetailResponse,
    ReviewSummaryResponse,
    StatsResponse,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def create_app(
    gold_dir: Path | None = None,
    corpus_path: Path | None = None,
    annotations_path: Path | None = None,
    dev_corpus_path: Path | None = None,
    dev_annotations_path: Path | None = None,
) -> FastAPI:
    app = FastAPI(title="KITCHEN INTEL API", version="0.1.0", description="API de oportunidades Gold e revisão humana.")
    origins = [origin.strip() for origin in os.getenv("KITCHEN_INTEL_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",") if origin.strip()]
    app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=False, allow_methods=["GET", "PUT"], allow_headers=["Accept", "Content-Type"])
    repository = GoldRepository(gold_dir or PROJECT_ROOT / "data" / "gold" / "opportunities")
    review_repo = ReviewRepository(
        corpus_path or PROJECT_ROOT / "reports" / "evaluation_corpus_v0.1.0.csv",
        annotations_path or PROJECT_ROOT / "reports" / "human_annotations_v0.1.0.csv",
    )
    dev_review_repo = ReviewRepository(
        dev_corpus_path or PROJECT_ROOT / "reports" / "development_corpus_v0.1.0.csv",
        dev_annotations_path or PROJECT_ROOT / "reports" / "development_annotations_v0.1.0.csv",
        blind_mode=True,
    )

    @app.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse(status="ok")

    @app.get("/stats", response_model=StatsResponse)
    def stats() -> StatsResponse:
        records = _records(repository)
        relevance = Counter(item["relevance"] for item in records)
        temporal = Counter(item["temporal_status"] for item in records)
        categories = Counter(category for item in records for category in item.get("categories", []))
        scores = [item["opportunity_score"] for item in records]
        confidences = [item["confidence_score"] for item in records]
        ticket_total = sum(float(item["valor_total_estimado"]) for item in records if isinstance(item.get("valor_total_estimado"), (int, float)))
        return StatsResponse(total_gold=len(records), relevant=len(records) - relevance["IRRELEVANTE"], irrelevant=relevance["IRRELEVANTE"], high=relevance["ALTA"], medium=relevance["MEDIA"], low=relevance["BAIXA"], active=temporal["ATIVA"], future=temporal["FUTURA"], closed=temporal["ENCERRADA"], indeterminate=temporal["INDETERMINADA"], average_opportunity_score=round(sum(scores) / len(scores), 2) if scores else None, average_confidence_score=round(sum(confidences) / len(confidences), 2) if confidences else None, estimated_ticket_total=ticket_total, categories=dict(sorted(categories.items())))

    @app.get("/opportunities", response_model=OpportunityPage)
    def opportunities(
        q: Annotated[str | None, Query(max_length=200)] = None,
        uf: Annotated[str | None, Query(min_length=2, max_length=2)] = None,
        municipio: Annotated[str | None, Query(max_length=100)] = None,
        category: Annotated[str | None, Query(max_length=50)] = None,
        relevance: Annotated[str | None, Query(pattern="^(ALTA|MEDIA|BAIXA|IRRELEVANTE)$")] = None,
        temporal_status: Annotated[str | None, Query(pattern="^(ATIVA|FUTURA|ENCERRADA|INDETERMINADA)$")] = None,
        min_score: Annotated[int | None, Query(ge=0, le=100)] = None,
        min_confidence: Annotated[int | None, Query(ge=0, le=100)] = None,
        page: Annotated[int, Query(ge=1)] = 1,
        page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    ) -> OpportunityPage:
        records = _filter(_records(repository), q, uf, municipio, category, relevance, temporal_status, min_score, min_confidence)
        records.sort(key=lambda item: (-item["opportunity_score"], -item["confidence_score"], item["opportunity_id"]))
        total = len(records)
        start = (page - 1) * page_size
        return OpportunityPage(items=[OpportunityResponse.model_validate(item) for item in records[start : start + page_size]], total=total, page=page, page_size=page_size, total_pages=math.ceil(total / page_size) if total else 0)

    @app.get("/opportunities/{opportunity_id}", response_model=OpportunityResponse)
    def opportunity_detail(opportunity_id: str) -> OpportunityResponse:
        return OpportunityResponse.model_validate(_find(_records(repository), opportunity_id))

    @app.get("/opportunities/{opportunity_id}/evidence", response_model=EvidenceResponse)
    def opportunity_evidence(opportunity_id: str) -> EvidenceResponse:
        item = _find(_records(repository), opportunity_id)
        return EvidenceResponse(opportunity_id=opportunity_id, matched_terms=item.get("matched_terms", []), negative_matches=item.get("negative_matches", []), reason_codes=item.get("reason_codes", []), score_breakdown=item.get("score_breakdown", {}), lineage={"source": item["source"], "source_record_id": item["source_record_id"], "source_silver_file": item.get("source_silver_file"), "source_bronze_files": item.get("source_bronze_files", [])})

    @app.get("/review", response_model=ReviewSummaryResponse)
    def review_summary() -> ReviewSummaryResponse:
        try:
            return ReviewSummaryResponse.model_validate(review_repo.get_summary())
        except RuntimeError as error:
            raise HTTPException(status_code=503, detail=str(error)) from error

    @app.get("/review/export")
    def review_export() -> PlainTextResponse:
        try:
            content = review_repo.export_annotations_text()
            return PlainTextResponse(
                content=content,
                media_type="text/csv",
                headers={"Content-Disposition": 'attachment; filename="human_annotations_v0.1.0.csv"'},
            )
        except RuntimeError as error:
            raise HTTPException(status_code=503, detail=str(error)) from error

    # =========================================================================
    # DEV SET BLIND REVIEW ENDPOINTS (Gate 5D)
    # =========================================================================

    @app.get("/review/dev", response_model=ReviewSummaryResponse)
    def dev_review_summary() -> ReviewSummaryResponse:
        try:
            return ReviewSummaryResponse.model_validate(dev_review_repo.get_summary())
        except RuntimeError as error:
            raise HTTPException(status_code=503, detail=str(error)) from error

    @app.get("/review/dev/export")
    def dev_review_export() -> PlainTextResponse:
        try:
            content = dev_review_repo.export_annotations_text()
            return PlainTextResponse(
                content=content,
                media_type="text/csv",
                headers={"Content-Disposition": 'attachment; filename="development_annotations_v0.1.0.csv"'},
            )
        except RuntimeError as error:
            raise HTTPException(status_code=503, detail=str(error)) from error

    @app.get("/review/dev/{review_id}", response_model=ReviewDetailResponse)
    def dev_review_detail(review_id: str) -> ReviewDetailResponse:
        try:
            detail = dev_review_repo.get_detail(review_id)
        except RuntimeError as error:
            raise HTTPException(status_code=503, detail=str(error)) from error
        if detail is None:
            raise HTTPException(status_code=404, detail="Item de revisão DEV não encontrado")
        return ReviewDetailResponse.model_validate(detail)

    def _validate_annotation_payload(payload: HumanAnnotationUpdate) -> None:
        invalid_cats = set(payload.human_categories) - VALID_CATEGORIES
        if invalid_cats:
            raise HTTPException(
                status_code=422,
                detail=f"Categorias inválidas: {sorted(invalid_cats)}. Válidas: {sorted(VALID_CATEGORIES)}",
            )
        if not payload.human_relevant:
            if payload.human_relevance != "IRRELEVANTE":
                raise HTTPException(
                    status_code=422,
                    detail="Quando human_relevant for falso, human_relevance deve ser IRRELEVANTE.",
                )
            if payload.human_categories:
                raise HTTPException(
                    status_code=422,
                    detail="Quando human_relevant for falso, human_categories deve ser vazio.",
                )
        else:
            if payload.human_relevance == "IRRELEVANTE":
                raise HTTPException(
                    status_code=422,
                    detail="Quando human_relevant for verdadeiro, human_relevance deve ser ALTA, MEDIA ou BAIXA.",
                )

    @app.put("/review/dev/{review_id}", response_model=ReviewDetailResponse)
    def update_dev_review(review_id: str, payload: HumanAnnotationUpdate) -> ReviewDetailResponse:
        _validate_annotation_payload(payload)
        try:
            updated = dev_review_repo.save_annotation(
                review_id=review_id,
                human_relevant=payload.human_relevant,
                human_relevance=payload.human_relevance,
                human_categories=payload.human_categories,
                human_confidence=payload.human_confidence,
                human_notes=payload.human_notes,
            )
            return ReviewDetailResponse.model_validate(updated)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except RuntimeError as error:
            raise HTTPException(status_code=503, detail=str(error)) from error

    @app.get("/review/{review_id}", response_model=ReviewDetailResponse)
    def review_detail(review_id: str) -> ReviewDetailResponse:
        try:
            detail = review_repo.get_detail(review_id)
        except RuntimeError as error:
            raise HTTPException(status_code=503, detail=str(error)) from error
        if detail is None:
            raise HTTPException(status_code=404, detail="Item de revisão não encontrado")
        return ReviewDetailResponse.model_validate(detail)

    @app.put("/review/{review_id}", response_model=ReviewDetailResponse)
    def update_review(review_id: str, payload: HumanAnnotationUpdate) -> ReviewDetailResponse:
        _validate_annotation_payload(payload)
        try:
            updated = review_repo.save_annotation(
                review_id=review_id,
                human_relevant=payload.human_relevant,
                human_relevance=payload.human_relevance,
                human_categories=payload.human_categories,
                human_confidence=payload.human_confidence,
                human_notes=payload.human_notes,
            )
            return ReviewDetailResponse.model_validate(updated)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except RuntimeError as error:
            raise HTTPException(status_code=503, detail=str(error)) from error

    return app


def _records(repository: GoldRepository) -> list[dict[str, Any]]:
    try:
        return repository.records()
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


def _find(records: list[dict[str, Any]], opportunity_id: str) -> dict[str, Any]:
    for item in records:
        if item["opportunity_id"] == opportunity_id:
            return item
    raise HTTPException(status_code=404, detail="Oportunidade não encontrada")


def _filter(records: list[dict[str, Any]], q: str | None, uf: str | None, municipio: str | None, category: str | None, relevance: str | None, temporal_status: str | None, min_score: int | None, min_confidence: int | None) -> list[dict[str, Any]]:
    query = q.casefold() if q else None
    return [item for item in records if (not query or query in " ".join(str(item.get(field) or "") for field in ("objeto_original", "orgao_nome", "unidade_nome")).casefold()) and (not uf or item.get("uf") == uf.upper()) and (not municipio or municipio.casefold() in str(item.get("municipio") or "").casefold()) and (not category or category.upper() in item.get("categories", [])) and (not relevance or item.get("relevance") == relevance) and (not temporal_status or item.get("temporal_status") == temporal_status) and (min_score is None or item.get("opportunity_score", 0) >= min_score) and (min_confidence is None or item.get("confidence_score", 0) >= min_confidence)]


app = create_app()
