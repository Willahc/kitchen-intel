"""Avaliação do baseline determinístico contra anotações humanas (Gate 4.6).

Este script opera em modo puro (sem dependências pesadas de ML).
Separação de corpus e anotação humana:
- Corpus imutável: reports/evaluation_corpus_v0.1.0.csv
- Anotações humanas de William: reports/human_annotations_v0.1.0.csv

Por padrão, exige 100% de cobertura de revisão humana para emissão
do relatório formal de benchmark. A flag --allow-partial permite
inspeção de métricas intermediárias durante a anotação.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def parse_human_bool(val: str | None) -> bool | None:
    if not val or not val.strip():
        return None
    cleaned = val.strip().lower()
    if cleaned in {"true", "1", "sim", "s", "verdadeiro", "v"}:
        return True
    if cleaned in {"false", "0", "nao", "não", "n", "falso", "f"}:
        return False
    return None


def parse_categories(val: str | None) -> set[str]:
    if not val or not val.strip():
        return set()
    items = [item.strip().upper() for item in val.replace(";", ",").split(",") if item.strip()]
    return set(items)


def compute_evaluation_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Calcula métricas de classificação binária, ordinal e multicategoria."""
    reviewed_binary = []
    for r in rows:
        h_bool = parse_human_bool(r.get("human_relevant"))
        if h_bool is not None:
            reviewed_binary.append((r, h_bool))

    if not reviewed_binary:
        return {
            "status": "PENDING_REVIEW",
            "message": "Corpus ainda não revisado. Nenhuma avaliação humana preenchida.",
            "total_records": len(rows),
            "reviewed_records": 0,
        }

    tp = fp = tn = fn = 0
    for r, human_truth in reviewed_binary:
        pred_relevant = r.get("baseline_relevance") in {"ALTA", "MEDIA", "BAIXA"}
        if pred_relevant and human_truth:
            tp += 1
        elif pred_relevant and not human_truth:
            fp += 1
        elif not pred_relevant and not human_truth:
            tn += 1
        else:
            fn += 1

    total_reviewed = len(reviewed_binary)
    accuracy = (tp + tn) / total_reviewed if total_reviewed else 0.0
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = (2 * precision * recall) / (precision + recall) if (precision + recall) else 0.0

    # Multiclasse: human_relevance (ALTA, MEDIA, BAIXA, IRRELEVANTE)
    relevance_matches = 0
    relevance_total = 0
    for r in rows:
        h_rel = str(r.get("human_relevance") or "").strip().upper()
        if h_rel in {"ALTA", "MEDIA", "BAIXA", "IRRELEVANTE"}:
            b_rel = str(r.get("baseline_relevance") or "").strip().upper()
            if b_rel == h_rel:
                relevance_matches += 1
            relevance_total += 1

    relevance_accuracy = relevance_matches / relevance_total if relevance_total else None

    # Multilabel: Categorias
    cat_exact_matches = 0
    cat_reviewed_total = 0
    total_intersections = 0
    total_predicted = 0
    total_gold = 0

    for r in rows:
        h_cats_raw = r.get("human_categories")
        if h_cats_raw and str(h_cats_raw).strip():
            cat_reviewed_total += 1
            h_cats = parse_categories(h_cats_raw)
            b_cats = parse_categories(r.get("baseline_categories"))
            if h_cats == b_cats:
                cat_exact_matches += 1
            inter = len(h_cats & b_cats)
            total_intersections += inter
            total_predicted += len(b_cats)
            total_gold += len(h_cats)

    category_exact_accuracy = cat_exact_matches / cat_reviewed_total if cat_reviewed_total else None
    category_precision = total_intersections / total_predicted if total_predicted else (1.0 if total_gold == 0 else 0.0)
    category_recall = total_intersections / total_gold if total_gold else (1.0 if total_predicted == 0 else 0.0)
    if (category_precision + category_recall) > 0:
        category_f1 = (2 * category_precision * category_recall) / (category_precision + category_recall)
    else:
        category_f1 = 0.0

    return {
        "status": "EVALUATED",
        "total_records": len(rows),
        "reviewed_records": total_reviewed,
        "confusion_matrix": {
            "true_positive": tp,
            "false_positive": fp,
            "true_negative": tn,
            "false_negative": fn,
        },
        "binary_metrics": {
            "accuracy": round(accuracy, 4),
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1_score": round(f1, 4),
        },
        "multiclass_relevance": {
            "evaluated_count": relevance_total,
            "exact_matches": relevance_matches,
            "relevance_accuracy": round(relevance_accuracy, 4) if relevance_accuracy is not None else None,
        },
        "multilabel_categories": {
            "evaluated_count": cat_reviewed_total,
            "exact_match_accuracy": round(category_exact_accuracy, 4) if category_exact_accuracy is not None else None,
            "category_precision": round(category_precision, 4) if cat_reviewed_total else None,
            "category_recall": round(category_recall, 4) if cat_reviewed_total else None,
            "category_f1": round(category_f1, 4) if cat_reviewed_total else None,
        },
    }


def load_joined_data(corpus_path: Path, annotations_path: Path) -> tuple[list[dict[str, Any]], int, int]:
    """Lê corpus imutável e anotações humanas, realizando join por review_id."""
    if not corpus_path.exists():
        raise FileNotFoundError(f"Corpus de avaliação não encontrado: {corpus_path}")
    if not annotations_path.exists():
        raise FileNotFoundError(f"Arquivo de anotações não encontrado: {annotations_path}")

    with corpus_path.open("r", encoding="utf-8") as f:
        corpus = list(csv.DictReader(f))

    with annotations_path.open("r", encoding="utf-8") as f:
        annotations = {a["review_id"]: a for a in csv.DictReader(f)}

    merged = []
    reviewed_count = 0
    for c in corpus:
        rid = c["review_id"]
        a = annotations.get(rid, {})
        if a and a.get("source_record_id") and a.get("source_record_id") != c.get("source_record_id"):
            raise ValueError(
                f"Inconsistência de source_record_id no review_id {rid}: corpus={c.get('source_record_id')} vs anotação={a.get('source_record_id')}"
            )

        is_rev = bool(a.get("reviewed_at") and a.get("reviewed_at").strip())
        if is_rev:
            reviewed_count += 1

        row = dict(c)
        row["human_relevant"] = a.get("human_relevant", "")
        row["human_relevance"] = a.get("human_relevance", "")
        row["human_categories"] = a.get("human_categories", "")
        row["human_confidence"] = a.get("human_confidence", "")
        row["human_notes"] = a.get("human_notes", "")
        row["reviewed_at"] = a.get("reviewed_at", "")
        merged.append(row)

    pending_count = len(corpus) - reviewed_count
    return merged, reviewed_count, pending_count


def load_review_csv(csv_path: Path) -> list[dict[str, Any]]:
    """Carrega arquivo CSV único (compatibilidade com Gate 4.5)."""
    if not csv_path.exists():
        raise FileNotFoundError(f"Arquivo CSV não encontrado: {csv_path}")
    with csv_path.open("r", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def main() -> int:
    parser = argparse.ArgumentParser(description="Calcula métricas de avaliação contra anotação humana (Gate 4.6).")
    parser.add_argument("--corpus", type=Path, default=Path("reports/evaluation_corpus_v0.1.0.csv"), help="Caminho do corpus imutável")
    parser.add_argument("--annotations", type=Path, default=Path("reports/human_annotations_v0.1.0.csv"), help="Caminho das anotações humanas")
    parser.add_argument("--csv", type=Path, default=None, help="Caminho legado de CSV único (se aplicável)")
    parser.add_argument("--output-json", type=Path, default=None, help="Caminho para salvar o resultado em JSON")
    parser.add_argument("--allow-partial", action="store_true", help="Permite inspeção de métricas com anotação parcial (<100%%)")
    args = parser.parse_args()

    if args.csv:
        rows = load_review_csv(args.csv)
        reviewed_count = sum(1 for r in rows if r.get("human_relevant") and str(r.get("human_relevant")).strip())
        pending_count = len(rows) - reviewed_count
    else:
        rows, reviewed_count, pending_count = load_joined_data(args.corpus, args.annotations)

    total_count = len(rows)
    pct = (reviewed_count / total_count * 100) if total_count else 0.0

    if pending_count > 0 and not args.allow_partial:
        print("==================================================")
        print("AVALIAÇÃO FORMAL BLOQUEADA — ANOTAÇÃO INCOMPLETA")
        print("==================================================")
        print(f"Progresso atual: {reviewed_count}/{total_count} ({pct:.1f}%) registros anotados.")
        print(f"Pendências: {pending_count} registros aguardando anotação humana por William.")
        print("\nPara a emissão de métricas oficiais de Ground Truth, 100% dos registros devem ser anotados.")
        print("Para visualizar resultados preliminares ou parciais para fins de diagnóstico, use:")
        print("    python scripts/evaluate_baseline_human.py --allow-partial")
        return 1

    if args.allow_partial and pending_count > 0:
        print(f"[AVISO] Executando avaliação PARCIAL ({reviewed_count}/{total_count} anotados, {pending_count} pendentes).\n")

    results = compute_evaluation_metrics(rows)

    if results["status"] == "PENDING_REVIEW":
        print(f"Corpus ainda não revisado. Total de registros: {results['total_records']}. {results['message']}")
        return 0

    print("==================================================")
    print(f"RESULTADOS DA AVALIAÇÃO HUMANA ({results['reviewed_records']}/{results['total_records']} revisados)")
    print("==================================================")
    cm = results["confusion_matrix"]
    print("Matriz de Confusão:")
    print(f"  TP (Verdadeiro Positivo): {cm['true_positive']}")
    print(f"  FP (Falso Positivo):      {cm['false_positive']}")
    print(f"  TN (Verdadeiro Negativo): {cm['true_negative']}")
    print(f"  FN (Falso Negativo):      {cm['false_negative']}")
    print("\nMétricas Binárias:")
    bm = results["binary_metrics"]
    print(f"  Acurácia:  {bm['accuracy']:.2%}")
    print(f"  Precisão:  {bm['precision']:.2%}")
    print(f"  Recall:    {bm['recall']:.2%}")
    print(f"  F1 Score:  {bm['f1_score']:.2%}")

    if args.output_json:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\nRelatório salvo em: {args.output_json}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
