"""Repositório de persistência e consulta do corpus de avaliação e anotações humanas (Gate 4.6).

O corpus de avaliação é estritamente IMUTÁVEL (somente leitura).
Apenas o arquivo reports/human_annotations_v0.1.0.csv é atualizado pelas anotações de William.
"""

from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

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


class ReviewRepository:
    """Gerencia leitura do corpus imutável e persistência das anotações humanas."""

    def __init__(self, corpus_path: Path, annotations_path: Path, blind_mode: bool = False) -> None:
        self.corpus_path = corpus_path
        self.annotations_path = annotations_path
        self.blind_mode = blind_mode

    def _read_corpus(self) -> list[dict[str, str]]:
        if not self.corpus_path.exists():
            raise RuntimeError(f"Corpus de avaliação não encontrado em {self.corpus_path}")
        with self.corpus_path.open("r", encoding="utf-8") as f:
            return list(csv.DictReader(f))

    def _read_annotations(self) -> list[dict[str, str]]:
        if not self.annotations_path.exists():
            raise RuntimeError(f"Arquivo de anotações não encontrado em {self.annotations_path}")
        with self.annotations_path.open("r", encoding="utf-8") as f:
            return list(csv.DictReader(f))

    def get_summary(self) -> dict[str, Any]:
        corpus = self._read_corpus()
        annotations = {a["review_id"]: a for a in self._read_annotations()}

        reviewed_count = 0
        items = []

        for c in corpus:
            rid = c["review_id"]
            a = annotations.get(rid, {})
            is_rev = bool(a.get("reviewed_at") and a.get("reviewed_at").strip())
            if is_rev:
                reviewed_count += 1
            items.append({
                "review_id": rid,
                "source_record_id": c.get("source_record_id", ""),
                "orgao_nome": c.get("orgao_nome", ""),
                "objeto_original": c.get("objeto_original", ""),
                "is_reviewed": is_rev,
                "reviewed_at": a.get("reviewed_at") or None,
            })

        total = len(corpus)
        pending = total - reviewed_count
        percent = round((reviewed_count / total) * 100, 1) if total else 0.0

        return {
            "total": total,
            "reviewed": reviewed_count,
            "pending": pending,
            "progress_percent": percent,
            "items": items,
        }

    def get_detail(self, review_id: str) -> dict[str, Any] | None:
        corpus = self._read_corpus()
        c_item = next((c for c in corpus if c["review_id"] == review_id), None)
        if not c_item:
            return None

        annotations = {a["review_id"]: a for a in self._read_annotations()}
        a_item = annotations.get(review_id, {})

        is_reviewed = bool(a_item.get("reviewed_at") and a_item.get("reviewed_at").strip())

        # Baseline predictions (omitted in blind review mode to prevent anchoring bias)
        if self.blind_mode:
            baseline = None
        else:
            raw_cats = [x.strip() for x in (c_item.get("baseline_categories") or "").split(",") if x.strip()]
            baseline = {
                "relevance": c_item.get("baseline_relevance"),
                "categories": raw_cats,
                "opportunity_score": int(c_item.get("baseline_score") or 0),
                "confidence_score": int(c_item.get("baseline_confidence") or 0),
                "matched_terms": c_item.get("matched_terms") or "",
                "negative_matches": c_item.get("negative_matches") or "",
            }

        # Human annotation
        h_rel_bool = None
        if a_item.get("human_relevant"):
            val = a_item["human_relevant"].strip().upper()
            if val in {"TRUE", "1", "SIM"}:
                h_rel_bool = True
            elif val in {"FALSE", "0", "NAO", "NÃO"}:
                h_rel_bool = False

        h_cats = [x.strip() for x in (a_item.get("human_categories") or "").split(",") if x.strip()]
        h_conf = int(a_item["human_confidence"]) if (a_item.get("human_confidence") and a_item["human_confidence"].strip().isdigit()) else None

        human = {
            "human_relevant": h_rel_bool,
            "human_relevance": a_item.get("human_relevance") or None,
            "human_categories": h_cats,
            "human_confidence": h_conf,
            "human_notes": a_item.get("human_notes") or "",
            "reviewed_at": a_item.get("reviewed_at") or None,
            "is_reviewed": is_reviewed,
        }

        return {
            "review_id": review_id,
            "source_record_id": c_item.get("source_record_id", ""),
            "objeto_original": c_item.get("objeto_original", ""),
            "orgao_nome": c_item.get("orgao_nome", ""),
            "unidade_nome": c_item.get("unidade_nome", ""),
            "municipio": c_item.get("municipio", ""),
            "uf": c_item.get("uf", ""),
            "valor_total_estimado": float(c_item["valor_total_estimado"]) if c_item.get("valor_total_estimado") else None,
            "data_publicacao": c_item.get("data_publicacao", ""),
            "baseline": baseline,
            "human": human,
        }

    def save_annotation(
        self,
        review_id: str,
        human_relevant: bool,
        human_relevance: str,
        human_categories: list[str],
        human_confidence: int,
        human_notes: str | None,
    ) -> dict[str, Any]:
        """Salva a anotação humana exclusivamente no arquivo de anotações."""
        # 1. Verifica existência no corpus imutável
        corpus = self._read_corpus()
        if not any(c["review_id"] == review_id for c in corpus):
            raise KeyError(f"Identificador de revisão {review_id} não encontrado")

        # 2. Lê anotações existentes
        annotations = self._read_annotations()
        found = False
        now_iso = datetime.now(timezone.utc).isoformat()

        for a in annotations:
            if a["review_id"] == review_id:
                a["human_relevant"] = "TRUE" if human_relevant else "FALSE"
                a["human_relevance"] = human_relevance.upper()
                a["human_categories"] = ", ".join(sorted(set(human_categories)))
                a["human_confidence"] = str(human_confidence)
                a["human_notes"] = (human_notes or "").strip()
                a["reviewed_at"] = now_iso
                found = True
                break

        if not found:
            raise KeyError(f"Registro {review_id} ausente no arquivo de anotações")

        # 3. Grava exclusivamente no arquivo de anotações
        fieldnames = [
            "review_id",
            "source_record_id",
            "human_relevant",
            "human_relevance",
            "human_categories",
            "human_confidence",
            "human_notes",
            "reviewed_at",
        ]
        with self.annotations_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(annotations)

        detail = self.get_detail(review_id)
        if detail is None:
            raise RuntimeError("Falha ao recuperar detalhe após salvamento")
        return detail

    def export_annotations_text(self) -> str:
        return self.annotations_path.read_text(encoding="utf-8")
