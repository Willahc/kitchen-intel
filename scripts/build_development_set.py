"""Script determinístico de construção e governança do Development Set (Gate 5D).

Gera:
- reports/development_corpus_v0.1.0.csv (120 registros reais do PNCP, zero overlap com Test Set)
- reports/development_annotations_v0.1.0.csv (arquivo de anotações humanas vazio para Blind Review)

Garante:
- Janela temporal estritamente posterior ao Test Set (> 2026-09-11T08:30:06)
- IDs dedicados: DEV-001 a DEV-120
- Distribuição estratificada:
  - 30 Potencialmente Relevantes
  - 30 Hard Negatives
  - 20 Negative Context
  - 20 Obvious Negatives
  - 20 Ambiguous / Borderline
- Zero overlap por source_record_id e zero colisão de texto normalizado com o Test Set
- Cálculo e exibição do hash SHA-256 para congelamento
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
import unicodedata
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.opportunity.engine import build_opportunity, load_rules


def norm_text(text: str | None) -> str:
    if not text:
        return ""
    t = unicodedata.normalize("NFKD", text).encode("ASCII", "ignore").decode("ASCII").lower()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", t)).strip()


def build_dev_corpus() -> dict[str, Any]:
    test_corpus_path = PROJECT_ROOT / "reports" / "evaluation_corpus_v0.1.0.csv"
    if not test_corpus_path.exists():
        raise FileNotFoundError(f"Test Set não encontrado em {test_corpus_path}")

    with test_corpus_path.open("r", encoding="utf-8") as f:
        test_records = list(csv.DictReader(f))

    test_ids = {r["source_record_id"] for r in test_records}
    test_hashes = {hashlib.sha256(norm_text(r["objeto_original"]).encode("utf-8")).hexdigest() for r in test_records}

    # Carregar Silver mais recente
    silver_files = sorted((PROJECT_ROOT / "data" / "silver" / "pncp").glob("*.jsonl"))
    if not silver_files:
        raise FileNotFoundError("Nenhum arquivo Silver encontrado em data/silver/pncp")
    latest_silver = silver_files[-1]

    silver_records: list[dict[str, Any]] = []
    with latest_silver.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                silver_records.append(json.loads(line))

    # Filtrar candidatos estritamente posteriores ao Test Set e sem overlap
    cut_off_date = "2026-09-11T08:30:06"
    candidates: list[dict[str, Any]] = []
    seen_hashes: set[str] = set()

    for r in silver_records:
        sid = r.get("source_record_id")
        pub = r.get("data_publicacao", "")
        if not sid or sid in test_ids or pub <= cut_off_date:
            continue
        h = hashlib.sha256(norm_text(r.get("objeto_compra", "")).encode("utf-8")).hexdigest()
        if h in test_hashes or h in seen_hashes:
            continue
        seen_hashes.add(h)
        candidates.append(r)

    # Classificar via regras baseline 0.1.1
    rules = load_rules(PROJECT_ROOT / "config" / "opportunity_rules.json")
    as_of = date(2026, 9, 13)
    gen_time = datetime.now(timezone.utc).isoformat()

    opps = [build_opportunity(c, latest_silver.name, as_of, gen_time, rules) for c in candidates]

    # Estratificação em 5 buckets metodológicos
    pot_rel: list[Any] = []
    hard_neg: list[Any] = []
    neg_ctx: list[Any] = []
    ambiguous: list[Any] = []
    obv_neg: list[Any] = []

    for c, o in zip(candidates, opps):
        obj = (o.objeto_original or "").lower()
        n_terms = [m["term"] for m in o.negative_matches]

        is_neg_ctx = len(n_terms) > 0 or any(
            k in obj
            for k in [
                "climatiz",
                "ar condicionado",
                "ar-condicionado",
                "chiller",
                "split",
                "odontol",
                "necrot",
                "hospitalar",
                "oxigênio",
                "medicamento",
                "gas glp",
                "botijão de gás",
                "botijao de gas",
                "combustível",
                "combustivel",
                "gasolina",
                "diesel",
            ]
        )

        is_pot_rel = (
            o.relevance in ("ALTA", "MEDIA", "BAIXA")
            or any(
                k in obj
                for k in [
                    "cozinha",
                    "refeitório",
                    "refeitorio",
                    "alimentação pronta",
                    "alimentacao pronta",
                    "merenda escolar",
                    "forno",
                    "fogão",
                    "fogao",
                    "câmara fria",
                    "camara fria",
                    "freezer industrial",
                    "balcão térmico",
                    "balcao termico",
                    "lavadora de louça",
                    "coifa",
                    "açougue",
                    "panificação",
                    "padaria",
                    "buffet",
                    "dietas",
                    "nutrição",
                    "refeição",
                ]
            )
        ) and not is_neg_ctx

        if is_pot_rel:
            pot_rel.append((c, o))
        elif is_neg_ctx:
            neg_ctx.append((c, o))
        elif any(
            k in obj
            for k in [
                "gêneros alimentícios",
                "generos alimenticios",
                "carnes",
                "hortifruti",
                "pão",
                "leite",
                "limpeza",
                "copa",
                "utensílios",
                "utensilios",
                "termômetro",
                "termometro",
                "mesas e cadeiras",
                "bancos",
            ]
        ):
            hard_neg.append((c, o))
        elif any(
            k in obj
            for k in [
                "manutenção",
                "manutencao",
                "reforma",
                "instalação",
                "instalacao",
                "inox",
                "aço",
                "ventilador",
                "exaustor",
            ]
        ):
            ambiguous.append((c, o))
        else:
            obv_neg.append((c, o))

    # Seleção exata das cotas: 30, 30, 20, 20, 20 = 120
    selected_tuples: list[tuple[dict[str, Any], Any, str]] = []

    for c, o in pot_rel[:30]:
        selected_tuples.append((c, o, "POTENTIAL_RELEVANT"))
    for c, o in hard_neg[:30]:
        selected_tuples.append((c, o, "HARD_NEGATIVE"))
    for c, o in neg_ctx[:20]:
        selected_tuples.append((c, o, "NEGATIVE_CONTEXT"))
    for c, o in ambiguous[:20]:
        selected_tuples.append((c, o, "AMBIGUOUS"))
    for c, o in obv_neg[:20]:
        selected_tuples.append((c, o, "OBVIOUS_NEGATIVE"))

    assert len(selected_tuples) == 120, f"Esperado 120, obteve {len(selected_tuples)}"

    # Ordenar por data de publicação para manter integridade cronológica
    selected_tuples.sort(key=lambda t: t[0].get("data_publicacao", ""))

    dev_rows: list[dict[str, Any]] = []
    annotation_rows: list[dict[str, Any]] = []

    for idx, (c, o, bucket) in enumerate(selected_tuples, 1):
        dev_id = f"DEV-{idx:03d}"
        sid = c["source_record_id"]

        # Formatar baseline_categories como string separada por vírgula
        cats_str = ", ".join(o.categories)

        # Formatar matched_terms
        matched_str = "; ".join(f"{m['term']} -> {m['category']}" for m in o.matched_terms)
        neg_str = "; ".join(f"{m['term']} -> {m['reason_code']}" for m in o.negative_matches)

        row = {
            "review_id": dev_id,
            "source_record_id": sid,
            "objeto_original": o.objeto_original or "",
            "orgao_nome": o.orgao_nome or "",
            "unidade_nome": o.unidade_nome or "",
            "municipio": o.municipio or "",
            "uf": o.uf or "",
            "valor_total_estimado": str(o.valor_total_estimado) if o.valor_total_estimado is not None else "",
            "data_publicacao": o.data_publicacao or "",
            "baseline_relevance": o.relevance,
            "baseline_categories": cats_str,
            "baseline_score": str(o.opportunity_score),
            "baseline_confidence": str(o.confidence_score),
            "matched_terms": matched_str,
            "negative_matches": neg_str,
        }
        dev_rows.append(row)

        annotation_row = {
            "review_id": dev_id,
            "source_record_id": sid,
            "human_relevant": "",
            "human_relevance": "",
            "human_categories": "",
            "human_confidence": "",
            "human_notes": "",
            "reviewed_at": "",
        }
        annotation_rows.append(annotation_row)

    # Escrever reports/development_corpus_v0.1.0.csv
    dev_corpus_file = PROJECT_ROOT / "reports" / "development_corpus_v0.1.0.csv"
    dev_fields = [
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
    ]
    with dev_corpus_file.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=dev_fields)
        writer.writeheader()
        writer.writerows(dev_rows)

    # Escrever reports/development_annotations_v0.1.0.csv
    dev_ann_file = PROJECT_ROOT / "reports" / "development_annotations_v0.1.0.csv"
    ann_fields = [
        "review_id",
        "source_record_id",
        "human_relevant",
        "human_relevance",
        "human_categories",
        "human_confidence",
        "human_notes",
        "reviewed_at",
    ]
    with dev_ann_file.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=ann_fields)
        writer.writeheader()
        writer.writerows(annotation_rows)

    corpus_bytes = dev_corpus_file.read_bytes()
    corpus_sha = hashlib.sha256(corpus_bytes).hexdigest()

    summary = {
        "corpus_version": "dev-0.1.0",
        "total_records": len(dev_rows),
        "sha256": corpus_sha,
        "collection_start": min(r["data_publicacao"] for r in dev_rows),
        "collection_end": max(r["data_publicacao"] for r in dev_rows),
        "distribution": {
            "potential_relevant": 30,
            "hard_negatives": 30,
            "negative_context": 20,
            "ambiguous": 20,
            "obvious_negatives": 20,
        },
        "dev_corpus_path": str(dev_corpus_file),
        "dev_annotations_path": str(dev_ann_file),
    }

    # Salvar metadados de freeze
    freeze_meta_path = PROJECT_ROOT / "reports" / "development_corpus_v0.1.0.manifest.json"
    freeze_meta_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    return summary


if __name__ == "__main__":
    result = build_dev_corpus()
    print("==================================================")
    print("DEVELOPMENT CORPUS CREATED & FROZEN")
    print("==================================================")
    print(f"Version:      {result['corpus_version']}")
    print(f"Records:      {result['total_records']}")
    print(f"SHA-256:      {result['sha256']}")
    print(f"Window Start: {result['collection_start']}")
    print(f"Window End:   {result['collection_end']}")
    print(f"Distribution: {result['distribution']}")
    print("==================================================")
