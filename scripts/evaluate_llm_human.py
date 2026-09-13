"""Script de avaliação do LLM contra Ground Truth e comparação com o Baseline (Gate 5).

Gera:
- Relatório de métricas do LLM
- Comparação formal contra baseline determinístico (reports/gate5_comparison.json)
- Análise técnica detalhada de erros: Falsos Positivos e Falsos Negativos (reports/gate5_error_analysis.md)
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
    if not val or not str(val).strip():
        return None
    c = str(val).strip().lower()
    if c in {"true", "1", "sim", "s"}:
        return True
    if c in {"false", "0", "nao", "não", "n"}:
        return False
    return None


def parse_categories(val: Any) -> set[str]:
    if not val:
        return set()
    if isinstance(val, (list, tuple, set)):
        return {str(x).strip().upper() for x in val if str(x).strip()}
    return {item.strip().upper() for item in str(val).replace(";", ",").split(",") if item.strip()}


def load_llm_predictions(jsonl_path: Path) -> list[dict[str, Any]]:
    if not jsonl_path.exists():
        raise FileNotFoundError(f"Arquivo de predições do LLM não encontrado: {jsonl_path}")
    results = []
    with jsonl_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                results.append(json.loads(line))
    return results


def load_human_annotations(csv_path: Path) -> dict[str, dict[str, Any]]:
    if not csv_path.exists():
        raise FileNotFoundError(f"Arquivo de anotações humanas não encontrado: {csv_path}")
    with csv_path.open("r", encoding="utf-8") as f:
        return {r["review_id"]: r for r in csv.DictReader(f)}


def load_corpus_objects(corpus_path: Path) -> dict[str, str]:
    if not corpus_path.exists():
        return {}
    with corpus_path.open("r", encoding="utf-8") as f:
        return {r["review_id"]: r.get("objeto_original", "") for r in csv.DictReader(f)}


def compute_llm_metrics(
    predictions: list[dict[str, Any]],
    annotations: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    tp = fp = tn = fn = 0
    joined_count = 0
    error_records: list[dict[str, Any]] = []

    relevance_matches = 0
    relevance_total = 0

    cat_exact_matches = 0
    cat_total_samples = 0
    cat_total_intersections = 0
    cat_total_predicted = 0
    cat_total_gold = 0

    for pred in predictions:
        rid = pred["review_id"]
        ann = annotations.get(rid)
        if not ann:
            continue

        h_bool = parse_human_bool(ann.get("human_relevant"))
        if h_bool is None:
            continue

        joined_count += 1
        model_relevant = bool(pred.get("relevant"))
        model_relevance = str(pred.get("relevance") or "").strip().upper()
        human_relevance = str(ann.get("human_relevance") or "").strip().upper()

        # Classificação binária
        if model_relevant and h_bool:
            tp += 1
        elif model_relevant and not h_bool:
            fp += 1
            error_records.append({
                "type": "FP",
                "review_id": rid,
                "model_relevant": model_relevant,
                "model_relevance": model_relevance,
                "model_reason": pred.get("reason", ""),
                "human_relevant": h_bool,
                "human_relevance": human_relevance,
                "human_notes": ann.get("human_notes", ""),
            })
        elif not model_relevant and not h_bool:
            tn += 1
        else:
            fn += 1
            error_records.append({
                "type": "FN",
                "review_id": rid,
                "model_relevant": model_relevant,
                "model_relevance": model_relevance,
                "model_reason": pred.get("reason", ""),
                "human_relevant": h_bool,
                "human_relevance": human_relevance,
                "human_notes": ann.get("human_notes", ""),
            })

        # Multiclasse Relevância
        if human_relevance in {"ALTA", "MEDIA", "BAIXA", "IRRELEVANTE"}:
            if model_relevance == human_relevance:
                relevance_matches += 1
            relevance_total += 1

        # Multilabel Categorias
        h_cats_raw = ann.get("human_categories")
        if h_cats_raw and str(h_cats_raw).strip():
            cat_total_samples += 1
            h_cats = parse_categories(h_cats_raw)
            m_cats = parse_categories(pred.get("categories"))
            if h_cats == m_cats:
                cat_exact_matches += 1
            inter = len(h_cats & m_cats)
            cat_total_intersections += inter
            cat_total_predicted += len(m_cats)
            cat_total_gold += len(h_cats)

    accuracy = (tp + tn) / joined_count if joined_count else 0.0
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = (2 * precision * recall) / (precision + recall) if (precision + recall) else 0.0

    cat_exact_acc = cat_exact_matches / cat_total_samples if cat_total_samples else 0.0
    cat_precision = cat_total_intersections / cat_total_predicted if cat_total_predicted else (1.0 if cat_total_gold == 0 else 0.0)
    cat_recall = cat_total_intersections / cat_total_gold if cat_total_gold else (1.0 if cat_total_predicted == 0 else 0.0)
    cat_f1 = (2 * cat_precision * cat_recall) / (cat_precision + cat_recall) if (cat_precision + cat_recall) else 0.0

    return {
        "status": "EVALUATED",
        "total_evaluated": joined_count,
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
            "relevance_accuracy": round(relevance_matches / relevance_total, 4) if relevance_total else 0.0,
        },
        "multilabel_categories": {
            "evaluated_count": cat_total_samples,
            "exact_match_accuracy": round(cat_exact_acc, 4),
            "micro_precision": round(cat_precision, 4),
            "micro_recall": round(cat_recall, 4),
            "micro_f1": round(cat_f1, 4),
        },
        "error_records": error_records,
    }


def generate_error_analysis_md(
    error_records: list[dict[str, Any]],
    corpus_objects: dict[str, str],
    output_path: Path,
) -> None:
    """Gera relatório qualitativo descritivo dos Falsos Positivos e Falsos Negativos do LLM."""
    fps = [e for e in error_records if e["type"] == "FP"]
    fns = [e for e in error_records if e["type"] == "FN"]

    lines = [
        "# Relatório de Análise de Erros — Gate 5: Classificador LLM vs Ground Truth",
        "",
        "Este documento apresenta a auditoria técnica qualitativa de cada discrepância entre a predição",
        "do modelo de linguagem e o padrão-ouro (Ground Truth) validado por William.",
        "",
        f"**Total de Falsos Positivos (FP):** {len(fps)}",
        f"**Total de Falsos Negativos (FN):** {len(fns)}",
        "",
        "---",
        "",
        "## 1. Falsos Positivos (O modelo classificou como relevante, mas William julgou irrelevante)",
        "",
    ]

    if not fps:
        lines.append("Nenhum Falso Positivo identificado.")
    else:
        for fp in fps:
            rid = fp["review_id"]
            obj = corpus_objects.get(rid, "Objeto não localizado")
            lines.extend([
                f"### Caso {rid} (Falso Positivo)",
                f"- **Objeto Oficial:** {obj}",
                f"- **Predição do Modelo:** `{fp['model_relevance']}` (relevant=True)",
                f"- **Justificativa do Modelo (Reason):** {fp['model_reason']}",
                f"- **Ground Truth (William):** `{fp['human_relevance']}` (relevant=False)",
                f"- **Notas de William:** {fp['human_notes'] or 'Sem observações adicionais'}",
                f"- **Diagnóstico Técnico:** O modelo interpretou o contexto como aderente ao setor de alimentação, porém William considerou fora de escopo comercial prático.",
                "",
            ])

    lines.extend([
        "---",
        "",
        "## 2. Falsos Negativos (O modelo classificou como irrelevante, mas William julgou relevante)",
        "",
    ])

    if not fns:
        lines.append("Nenhum Falso Negativo identificado.")
    else:
        for fn in fns:
            rid = fn["review_id"]
            obj = corpus_objects.get(rid, "Objeto não localizado")
            lines.extend([
                f"### Caso {rid} (Falso Negativo)",
                f"- **Objeto Oficial:** {obj}",
                f"- **Predição do Modelo:** `{fn['model_relevance']}` (relevant=False)",
                f"- **Justificativa do Modelo (Reason):** {fn['model_reason']}",
                f"- **Ground Truth (William):** `{fn['human_relevance']}` (relevant=True)",
                f"- **Notas de William:** {fn['human_notes'] or 'Sem observações adicionais'}",
                f"- **Diagnóstico Técnico:** Oportunidade perdida pelo modelo. O edital continha sinal de demanda considerado legítimo pelo revisor de negócio.",
                "",
            ])

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines), encoding="utf-8")


def generate_comparison_json(
    baseline_metrics: dict[str, Any],
    llm_metrics: dict[str, Any],
    output_path: Path,
) -> dict[str, Any]:
    b_bm = baseline_metrics.get("binary_metrics", {})
    l_bm = llm_metrics.get("binary_metrics", {})

    b_prec = b_bm.get("precision", 0.0)
    l_prec = l_bm.get("precision", 0.0)
    b_rec = b_bm.get("recall", 0.0)
    l_rec = l_bm.get("recall", 0.0)
    b_f1 = b_bm.get("f1_score", 0.0)
    l_f1 = l_bm.get("f1_score", 0.0)
    b_acc = b_bm.get("accuracy", 0.0)
    l_acc = l_bm.get("accuracy", 0.0)

    delta = {
        "precision_delta": round(l_prec - b_prec, 4),
        "recall_delta": round(l_rec - b_rec, 4),
        "f1_score_delta": round(l_f1 - b_f1, 4),
        "accuracy_delta": round(l_acc - b_acc, 4),
    }

    comparison = {
        "baseline": baseline_metrics,
        "llm": {
            "confusion_matrix": llm_metrics["confusion_matrix"],
            "binary_metrics": llm_metrics["binary_metrics"],
            "multiclass_relevance": llm_metrics["multiclass_relevance"],
            "multilabel_categories": llm_metrics["multilabel_categories"],
        },
        "delta": delta,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(comparison, indent=2, ensure_ascii=False), encoding="utf-8")
    return comparison


def main() -> int:
    parser = argparse.ArgumentParser(description="Avalia predições de LLM contra Ground Truth e compara com baseline.")
    parser.add_argument("--predictions", type=Path, default=Path("reports/llm_predictions_v0.1.0.jsonl"))
    parser.add_argument("--annotations", type=Path, default=Path("reports/human_annotations_v0.1.0.csv"))
    parser.add_argument("--corpus", type=Path, default=Path("reports/evaluation_corpus_v0.1.0.csv"))
    parser.add_argument("--baseline-json", type=Path, default=Path("reports/baseline_human_evaluation_v0.1.0.json"))
    parser.add_argument("--output-comparison", type=Path, default=Path("reports/gate5_comparison.json"))
    parser.add_argument("--output-error-analysis", type=Path, default=Path("reports/gate5_error_analysis.md"))
    parser.add_argument("--allow-incomplete", action="store_true", help="Permite avaliar mesmo se o corpus estiver incompleto (apenas para testes)")
    args = parser.parse_args()

    predictions = load_llm_predictions(args.predictions)
    annotations = load_human_annotations(args.annotations)
    corpus_objects = load_corpus_objects(args.corpus)

    valid_predictions = [
        p for p in predictions
        if p.get("status", "SUCCESS") in ("SUCCESS", "CACHED") and p.get("relevant") is not None
    ]
    distinct_models = {p.get("model") for p in valid_predictions if p.get("model")}
    distinct_prompt_versions = {p.get("prompt_version") for p in valid_predictions if p.get("prompt_version")}
    total_expected = len(annotations)

    if not args.allow_incomplete and (len(valid_predictions) < total_expected or len(distinct_models) > 1 or len(distinct_prompt_versions) > 1):
        print("==================================================")
        print(f"BENCHMARK INCOMPLETE — {len(valid_predictions)}/{total_expected}")
        print("==================================================")
        print("A avaliação formal contra o Ground Truth exige todas as 76 predições")
        print("válidas sob exatamente o MESMO modelo e prompt_version.")
        print(f"Predições válidas:     {len(valid_predictions)}/{total_expected}")
        print(f"Modelos detectados:    {list(distinct_models) or 'Nenhum'}")
        print(f"Versões de prompt:     {list(distinct_prompt_versions) or 'Nenhuma'}")
        print(f"Pendentes:             {total_expected - len(valid_predictions)}")
        print("\nNenhuma métrica final contra o ground truth gerada.")
        print("Execute novos lotes incrementais com scripts/run_llm_classification.py.")
        return 1

    if not args.baseline_json.exists():
        raise FileNotFoundError(f"Relatório formal do baseline não encontrado: {args.baseline_json}")
    baseline_metrics = json.loads(args.baseline_json.read_text(encoding="utf-8"))

    llm_metrics = compute_llm_metrics(valid_predictions, annotations)

    # 1. Gerar comparação formal
    comparison = generate_comparison_json(baseline_metrics, llm_metrics, args.output_comparison)

    # 2. Gerar relatório de análise de erros
    generate_error_analysis_md(llm_metrics["error_records"], corpus_objects, args.output_error_analysis)

    print("==================================================")
    print(f"COMPARAÇÃO DE PERFORMANCE: LLM vs BASELINE ({llm_metrics['total_evaluated']} registros)")
    print("==================================================")
    bm_b = baseline_metrics["binary_metrics"]
    bm_l = llm_metrics["binary_metrics"]
    delta = comparison["delta"]

    print(f"Métrica      Baseline     LLM          Delta")
    print(f"Precisão:    {bm_b['precision']:>7.2%}     {bm_l['precision']:>7.2%}     {delta['precision_delta']:>+7.2%}")
    print(f"Recall:      {bm_b['recall']:>7.2%}     {bm_l['recall']:>7.2%}     {delta['recall_delta']:>+7.2%}")
    print(f"F1 Score:    {bm_b['f1_score']:>7.2%}     {bm_l['f1_score']:>7.2%}     {delta['f1_score_delta']:>+7.2%}")
    print(f"Acurácia:    {bm_b['accuracy']:>7.2%}     {bm_l['accuracy']:>7.2%}     {delta['accuracy_delta']:>+7.2%}")
    print(f"\nComparação salva em: {args.output_comparison}")
    print(f"Análise de erros salva em: {args.output_error_analysis}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
