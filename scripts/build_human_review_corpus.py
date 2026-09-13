"""Montagem determinística do corpus real de avaliação e revisão humana (Gate 4.5)."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

CORPUS_VERSION = "0.1.0"
DEFAULT_SEED = 42

CSV_COLUMNS = [
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
    "human_relevant",
    "human_relevance",
    "human_categories",
    "human_confidence",
    "human_notes",
]


def load_latest_gold(gold_dir: Path) -> tuple[Path, list[dict[str, Any]]]:
    candidates = list(gold_dir.glob("opportunities_*.jsonl"))
    if not candidates:
        raise RuntimeError(f"Nenhum arquivo Gold encontrado em {gold_dir}")
    latest = max(candidates, key=lambda p: p.stat().st_mtime)
    records: list[dict[str, Any]] = []
    for line in latest.read_text(encoding="utf-8").splitlines():
        line_str = line.strip()
        if line_str:
            records.append(json.loads(line_str))
    return latest, records


def select_evaluation_corpus(
    records: list[dict[str, Any]],
    target_difficult_negatives: int = 24,
    target_random_negatives: int = 26,
    seed: int = DEFAULT_SEED,
) -> list[dict[str, Any]]:
    """Seleciona uma amostra representativa, balanceada e reproduzível."""
    rng = random.Random(seed)

    # 1. Todos os relevantes pelo baseline
    altas = [r for r in records if r.get("relevance") == "ALTA"]
    medias = [r for r in records if r.get("relevance") == "MEDIA"]
    baixas = [r for r in records if r.get("relevance") == "BAIXA"]
    relevantes = altas + medias + baixas

    relevantes_ids = {r["opportunity_id"] for r in relevantes}

    # 2. Negativos com negative_matches explícitos
    irrelevantes = [r for r in records if r.get("relevance") == "IRRELEVANTE" and r["opportunity_id"] not in relevantes_ids]
    with_neg_matches = [r for r in irrelevantes if r.get("negative_matches")]

    # 3. Negativos difíceis / limítrofes (contêm palavras de infraestrutura, saúde, alimento, reforma, etc.)
    boundary_keywords = [
        "manuten", "reforma", "hospital", "escola", "inox", "aco", "alimento",
        "nutri", "refei", "cozinha", "maquina", "equipamento", "predial", "gas"
    ]
    excluded_ids = relevantes_ids | {r["opportunity_id"] for r in with_neg_matches}
    
    candidate_difficult: list[dict[str, Any]] = []
    obvious_negatives: list[dict[str, Any]] = []

    for r in irrelevantes:
        if r["opportunity_id"] in excluded_ids:
            continue
        obj = str(r.get("objeto_original") or "").casefold()
        if any(kw in obj for kw in boundary_keywords):
            candidate_difficult.append(r)
        else:
            obvious_negatives.append(r)

    # Ordenação determinística antes de amostragem
    candidate_difficult.sort(key=lambda r: r["opportunity_id"])
    obvious_negatives.sort(key=lambda r: r["opportunity_id"])

    # Seleção de difíceis
    sample_difficult = candidate_difficult[:target_difficult_negatives] if len(candidate_difficult) <= target_difficult_negatives else rng.sample(candidate_difficult, target_difficult_negatives)

    # Seleção de óbvios
    sample_obvious = obvious_negatives[:target_random_negatives] if len(obvious_negatives) <= target_random_negatives else rng.sample(obvious_negatives, target_random_negatives)

    corpus = relevantes + with_neg_matches + sample_difficult + sample_obvious
    # Ordenar por oportunidade_id para desempate estável
    corpus.sort(key=lambda r: (-r.get("opportunity_score", 0), -r.get("confidence_score", 0), r["opportunity_id"]))
    return corpus


def build_review_rows(corpus: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for idx, item in enumerate(corpus, 1):
        matched_str = "; ".join(f"{m.get('term')} -> {m.get('category')}" for m in item.get("matched_terms", []))
        neg_str = "; ".join(f"{n.get('term')} -> {n.get('reason_code')}" for n in item.get("negative_matches", []))
        cat_str = ", ".join(item.get("categories", []))

        rows.append({
            "review_id": f"REV-{idx:03d}",
            "source_record_id": item.get("source_record_id", ""),
            "objeto_original": item.get("objeto_original", "") or "",
            "orgao_nome": item.get("orgao_nome", "") or "",
            "unidade_nome": item.get("unidade_nome", "") or "",
            "municipio": item.get("municipio", "") or "",
            "uf": item.get("uf", "") or "",
            "valor_total_estimado": item.get("valor_total_estimado", "") or "",
            "data_publicacao": item.get("data_publicacao", "") or "",
            "baseline_relevance": item.get("relevance", ""),
            "baseline_categories": cat_str,
            "baseline_score": item.get("opportunity_score", 0),
            "baseline_confidence": item.get("confidence_score", 0),
            "matched_terms": matched_str,
            "negative_matches": neg_str,
            "human_relevant": "",
            "human_relevance": "",
            "human_categories": "",
            "human_confidence": "",
            "human_notes": "",
        })
    return rows


def write_corpus_csv(rows: list[dict[str, Any]], output_path: Path) -> str:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    raw_bytes = output_path.read_bytes()
    return hashlib.sha256(raw_bytes).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description="Gera dataset real para revisão humana Gate 4.5.")
    parser.add_argument("--gold-dir", type=Path, default=Path("data/gold/opportunities"))
    parser.add_argument("--output-csv", type=Path, default=Path("reports/gate4_5_human_review.csv"))
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    args = parser.parse_args()

    latest_file, records = load_latest_gold(args.gold_dir)
    print(f"Lido Gold mais recente: {latest_file.name} com {len(records)} registros")

    corpus = select_evaluation_corpus(records, seed=args.seed)
    rows = build_review_rows(corpus)
    sha256 = write_corpus_csv(rows, args.output_csv)

    print(f"Corpus de avaliação criado: {args.output_csv}")
    print(f"Total de registros para revisão: {len(rows)}")
    print(f"Versão do corpus: {CORPUS_VERSION}")
    print(f"SHA-256: {sha256}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
