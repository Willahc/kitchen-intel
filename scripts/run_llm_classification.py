"""Script de execução experimental de classificação com LLM (Gate 5).

Executa em 3 fases graduais:
- FASE A (smoke): 5 registros
- FASE B (sample): 10 registros
- FASE C (full): 76 registros

Possui trava mandatória de segurança de custo (máx. US$ 2.00)
e bloqueio automático caso nenhuma credencial esteja configurada.
NUNCA lê arquivos de anotações humanas (zero data leakage).
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.classifier.cache import LLMCache
from src.classifier.engine import LLMClassifier
from src.classifier.llm_client import DailyQuotaExhaustedError, LLMClient, MissingCredentialsError
from src.models.llm import LLMClassificationResult

MAX_COST_LIMIT_USD = 2.00


def write_run_manifest(path: Path, manifest: dict[str, Any]) -> None:
    """Persiste somente telemetria operacional, sem payloads ou credenciais."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")


def load_corpus(corpus_path: Path) -> list[dict[str, Any]]:
    if not corpus_path.exists():
        raise FileNotFoundError(f"Corpus imutável não encontrado: {corpus_path}")
    with corpus_path.open("r", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def run_consistency_test(
    classifier: LLMClassifier,
    records: list[dict[str, Any]],
    output_path: Path,
    runs_per_record: int = 3,
) -> dict[str, Any]:
    """Executa 10 registros 3 vezes sem cache para verificar consistência estocástica (temp=0.0)."""
    selected_10 = records[:10]
    results_by_id: dict[str, list[dict[str, Any]]] = {}

    print(f"\n[CONSISTENCY] Iniciando teste de consistência em {len(selected_10)} registros ({runs_per_record} execuções cada)...")

    for rec in selected_10:
        rid = rec["review_id"]
        results_by_id[rid] = []
        for run_idx in range(runs_per_record):
            # use_cache=False obrigatório
            res = classifier.classify_record(rec, use_cache=False)
            results_by_id[rid].append(res.to_dict())

    # Calcular taxa de concordância
    binary_agreements = 0
    relevance_agreements = 0

    for rid, runs in results_by_id.items():
        relevant_vals = [r["relevant"] for r in runs]
        relevance_vals = [r["relevance"] for r in runs]

        if len(set(relevant_vals)) == 1:
            binary_agreements += 1
        if len(set(relevance_vals)) == 1:
            relevance_agreements += 1

    total_evaluated = len(selected_10)
    consistency_summary = {
        "records_tested": total_evaluated,
        "runs_per_record": runs_per_record,
        "binary_perfect_agreement_count": binary_agreements,
        "binary_agreement_rate": round(binary_agreements / total_evaluated, 4) if total_evaluated else 1.0,
        "relevance_perfect_agreement_count": relevance_agreements,
        "relevance_agreement_rate": round(relevance_agreements / total_evaluated, 4) if total_evaluated else 1.0,
        "detailed_runs": results_by_id,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(consistency_summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[CONSISTENCY] Concordância binária: {consistency_summary['binary_agreement_rate']:.1%}")
    print(f"[CONSISTENCY] Relatório salvo em: {output_path}")
    return consistency_summary


def compute_cost_metrics(
    results: list[LLMClassificationResult],
    cached_count: int,
    output_path: Path,
) -> dict[str, Any]:
    """Compila métricas de tokens, latência e custo computacional."""
    total_calls = len(results)
    live_results = [r for r in results if r.status != "CACHED"]

    total_in_tokens = sum(r.input_tokens for r in results)
    total_out_tokens = sum(r.output_tokens for r in results)
    total_tokens = total_in_tokens + total_out_tokens
    total_cost = round(sum(r.estimated_cost for r in results), 8)

    latencies = [r.latency_ms for r in live_results if r.latency_ms > 0]
    avg_latency = round(statistics.mean(latencies), 2) if latencies else 0.0
    p50_latency = round(statistics.median(latencies), 2) if latencies else 0.0
    p95_latency = round(statistics.quantiles(latencies, n=20)[18], 2) if len(latencies) >= 20 else (max(latencies) if latencies else 0.0)

    avg_cost = round(total_cost / total_calls, 8) if total_calls else 0.0

    cost_data = {
        "calls": total_calls,
        "cached_calls": cached_count,
        "live_calls": len(live_results),
        "tokens": {
            "input_tokens": total_in_tokens,
            "output_tokens": total_out_tokens,
            "total_tokens": total_tokens,
        },
        "cost": {
            "total_cost_usd": total_cost,
            "currency": "USD",
            "average_cost_per_record_usd": avg_cost,
        },
        "latency_ms": {
            "average_latency": avg_latency,
            "p50_latency": p50_latency,
            "p95_latency": p95_latency,
        },
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(cost_data, indent=2, ensure_ascii=False), encoding="utf-8")
    return cost_data


def show_benchmark_progress(
    corpus_path: Path,
    predictions_path: Path,
    client: LLMClient,
    prompt_version: str,
    temperature: float,
) -> None:
    """Exibe o progresso do benchmark sem revelar dados do ground truth."""
    records = load_corpus(corpus_path)
    total_corpus = len(records)
    preds: dict[str, dict[str, Any]] = {}
    if predictions_path.exists():
        with predictions_path.open("r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    item = json.loads(line)
                    if item.get("model") == client.model and item.get("prompt_version") == prompt_version:
                        preds[item["review_id"]] = item

    valid_count = sum(1 for p in preds.values() if p.get("status") in ("SUCCESS", "CACHED") and p.get("relevant") is not None)
    error_count = sum(1 for p in preds.values() if p.get("status") == "ERROR")
    pending_count = total_corpus - valid_count

    print("==================================================")
    print("LLM BENCHMARK PROGRESS")
    print("==================================================")
    print(f"Corpus:          {total_corpus}")
    print(f"Valid:           {valid_count}")
    print(f"Errors:          {error_count}")
    print(f"Pending:         {pending_count}")
    print()
    print(f"Provider:        {client.provider}")
    print(f"Model:           {client.model}")
    print(f"Prompt Version:  {prompt_version}")
    print(f"Temperature:     {temperature}")
    print("==================================================")


def main() -> int:
    parser = argparse.ArgumentParser(description="Executa classificação com LLM sobre o corpus imutável (Gate 5).")
    parser.add_argument("--corpus", type=Path, default=Path("reports/evaluation_corpus_v0.1.0.csv"))
    parser.add_argument("--phase", choices=["smoke", "sample", "full"], default="smoke", help="smoke (5), sample (10), full (76)")
    parser.add_argument("--provider", default=None, help="openai, gemini, anthropic (auto-detectado por padrão)")
    parser.add_argument("--model", default=None, help="gpt-4o-mini, gemini-2.5-flash, etc. (auto-detectado por padrão)")
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--prompt-file", type=Path, default=Path("prompts/classifier_v0.1.0.txt"))
    parser.add_argument("--prompt-version", default="0.1.0")
    parser.add_argument("--output-jsonl", type=Path, default=None)
    parser.add_argument("--cost-report", type=Path, default=None)
    parser.add_argument("--reasoning-effort", choices=["none", "low", "medium", "high"], default=None)
    parser.add_argument("--no-cache", action="store_true", help="Ignora leitura e gravação em cache")
    parser.add_argument("--estimate-cost", action="store_true", help="Calcula e exibe estimativa de custo máximo sem executar chamadas")
    parser.add_argument("--consistency", action="store_true", help="Executa teste de consistência estocástica (10 x 3)")
    parser.add_argument("--max-new-calls", type=int, default=None, help="Limite máximo de novas inferências reais nesta execução (lote seguro)")
    parser.add_argument("--progress", action="store_true", help="Exibe o progresso do benchmark sem executar novas chamadas")
    args = parser.parse_args()

    client = LLMClient(provider=args.provider, model=args.model, reasoning_effort=args.reasoning_effort)
    if args.output_jsonl is None:
        output_by_provider = {
            "groq": Path("reports/llm_predictions_groq_v0.1.0.jsonl"),
            "openai": Path("reports/llm_predictions_openai_v0.1.0.jsonl"),
            "openrouter": Path("reports/llm_predictions_openrouter_v0.1.0.jsonl"),
            "cerebras": Path("reports/llm_predictions_cerebras_v0.1.0.jsonl"),
            "nvidia": Path("reports/llm_predictions_nvidia_v0.1.0.jsonl"),
        }
        args.output_jsonl = output_by_provider.get(client.provider, Path("reports/llm_predictions_v0.1.0.jsonl"))
    if args.cost_report is None:
        cost_by_provider = {
            "groq": Path("reports/llm_cost_groq_gate5.json"),
            "openai": Path("reports/llm_cost_openai_gate5.json"),
            "openrouter": Path("reports/llm_cost_openrouter_gate5.json"),
            "cerebras": Path("reports/llm_cost_cerebras_gate5.json"),
            "nvidia": Path("reports/llm_cost_nvidia_gate5.json"),
        }
        args.cost_report = cost_by_provider.get(client.provider, Path("reports/llm_cost_gate5.json"))


    if args.progress:
        show_benchmark_progress(args.corpus, args.output_jsonl, client, args.prompt_version, args.temperature)
        return 0

    records = load_corpus(args.corpus)
    total_in_corpus = len(records)

    # 1. Definição do subset por fase
    phase_limits = {"smoke": 5, "sample": 10, "full": total_in_corpus}
    limit = phase_limits[args.phase]
    target_records = records[:limit]

    # 2. Segurança de Custo (Trava obrigatória)
    estimated_cost = client.estimate_max_cost(len(target_records))
    print("==================================================")
    print("KITCHEN INTEL — GATE 5: LLM CLASSIFIER")
    print("==================================================")
    print(f"Provedor:       {client.provider}")
    print(f"Modelo:         {client.model}")
    print(f"Temperatura:    {args.temperature}")
    print(f"Versão Prompt:  {args.prompt_version}")
    print(f"Fase:           {args.phase.upper()} ({len(target_records)} registros selecionados)")
    print(f"ESTIMATED MAX COST: ${estimated_cost:.5f} USD")

    if estimated_cost > MAX_COST_LIMIT_USD:
        print(f"\n[ERRO DE SEGURANÇA] Custo estimado (${estimated_cost:.2f}) excede o teto permitido de ${MAX_COST_LIMIT_USD:.2f} USD!")
        print("Execução abortada por precaução de segurança.")
        return 2

    if args.estimate_cost:
        print("\nEstimativa concluída. Nenhuma chamada executada (--estimate-cost informado).")
        return 0

    # 3. Verificação de Credenciais
    if not client.is_configured():
        print("\n==================================================")
        print("EXECUÇÃO REAL BLOQUEADA — CREDENCIAIS AUSENTES")
        print("==================================================")
        print(f"Nenhuma chave encontrada na variável de ambiente '{client.env_var_name}'.")
        print("Para executar chamadas reais contra o provedor:")
        print(f"    $env:{client.env_var_name} = 'sua-chave-aqui' (PowerShell)")
        print(f"    export {client.env_var_name}='sua-chave-aqui'  (Bash)")
        print("\nA infraestrutura do Gate 5 está validada e pronta para execução.")
        return 1

    classifier = LLMClassifier(
        client=client,
        cache=LLMCache(),
        prompt_path=args.prompt_file,
        prompt_version=args.prompt_version,
        temperature=args.temperature,
    )

    # 4. Teste de consistência se solicitado
    if args.consistency:
        consistency_file = Path("reports/gate5_consistency.json")
        run_consistency_test(classifier, records, consistency_file)
        return 0

    # 5. Carregar predições existentes para o modelo atual para evitar duplicações
    existing_preds: dict[str, dict[str, Any]] = {}
    if args.output_jsonl.exists():
        with args.output_jsonl.open("r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    item = json.loads(line)
                    # Não misturar resultados de modelos ou versões de prompt diferentes
                    if item.get("model") == client.model and item.get("prompt_version") == args.prompt_version:
                        existing_preds[item["review_id"]] = item

    results: list[LLMClassificationResult] = []
    cached_count = 0
    new_calls_count = 0
    api_calls_attempted = 0
    api_calls_successful = 0
    api_calls_failed = 0
    rate_limit_events = 0
    stop_reason = "NORMAL_COMPLETION"
    run_started = datetime.now(timezone.utc)
    run_id = f"{client.provider}_{run_started.strftime('%Y%m%dT%H%M%S%fZ')}"
    valid_before = sum(1 for p in existing_preds.values() if p.get("status") in ("SUCCESS", "CACHED") and p.get("relevant") is not None)
    manifest_path = Path("reports/runs") / client.provider / f"{run_id}.json"

    print(f"\nIniciando inferência para {len(target_records)} registros (limite novas chamadas: {args.max_new_calls or 'sem limite'})...")

    for idx, rec in enumerate(target_records, 1):
        clean_input, input_hash = classifier.prepare_input(rec)
        cache_key = classifier.cache.generate_key(
            input_hash=input_hash,
            provider=classifier.client.provider,
            model=classifier.client.model,
            prompt_version=classifier.prompt_version,
        )
        is_in_cache = (classifier.cache.get(cache_key) is not None) if not args.no_cache else False

        # Se não está em cache e já atingiu o limite de novas chamadas, interrompe
        if not is_in_cache and args.max_new_calls is not None and new_calls_count >= args.max_new_calls:
            print(f"\n[INCREMENTAL] Atingido o limite configurado de novas inferências (--max-new-calls {args.max_new_calls}). Parando voluntariamente.")
            stop_reason = "MAX_NEW_CALLS_REACHED"
            break

        if not is_in_cache:
            api_calls_attempted += 1
        try:
            res = classifier.classify_record(rec, use_cache=not args.no_cache)
        except DailyQuotaExhaustedError:
            rate_limit_events += 1
            stop_reason = "DAILY_RATE_LIMIT"
            valid_now = sum(1 for p in existing_preds.values() if p.get("status") in ("SUCCESS", "CACHED") and p.get("relevant") is not None)
            pending_now = total_in_corpus - valid_now
            print("\n==================================================")
            print("RATE_LIMIT_DAILY_REACHED")
            print(f"Valid predictions: {valid_now}/{total_in_corpus}")
            print(f"Pending: {pending_now}")
            print("Execute novamente após renovação da cota.")
            print("==================================================")
            break

        results.append(res)
        if res.status == "CACHED":
            cached_count += 1
        else:
            new_calls_count += 1
            if res.status == "SUCCESS":
                api_calls_successful += 1
            else:
                api_calls_failed += 1
            if idx < len(target_records):
                time.sleep(3.5)

        # Atualizar existing_preds apenas se não for erro ou se não existia predição válida anterior
        if res.status != "ERROR" or res.review_id not in existing_preds:
            existing_preds[res.review_id] = res.to_dict()

        err_suffix = f" | Err={res.error[:80]}" if res.error else ""
        print(
            f"[{idx}/{len(target_records)}] {res.review_id} -> "
            f"Rel={res.relevance} ({res.confidence}%) | "
            f"Status={res.status} | Lat={res.latency_ms}ms | Cost=${res.estimated_cost:.6f}{err_suffix}"
        )

    # 6. Salvar predições consolidadas em JSONL (ordenadas por review_id)
    args.output_jsonl.parent.mkdir(parents=True, exist_ok=True)
    sorted_predictions = sorted(
        existing_preds.values(),
        key=lambda x: int(x.get("review_id", "REV-999").split("-")[1])
        if x.get("review_id", "").startswith("REV-") and x.get("review_id", "").split("-")[1].isdigit()
        else 999
    )
    with args.output_jsonl.open("w", encoding="utf-8") as f:
        for p in sorted_predictions:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")

    print(f"\nPredições salvas em: {args.output_jsonl} ({len(sorted_predictions)} registros consolidados)")

    # 7. Salvar relatório de custos desta execução
    cost_summary = compute_cost_metrics(results, cached_count, args.cost_report)
    print(f"Relatório de custos salvo em: {args.cost_report}")
    print(f"Custo desta execução: ${cost_summary['cost']['total_cost_usd']:.6f} USD")
    print(f"Novas chamadas: {new_calls_count} | Chamadas em cache: {cached_count}/{len(results)}")

    finished_at = datetime.now(timezone.utc)
    valid_after = sum(1 for p in existing_preds.values() if p.get("status") in ("SUCCESS", "CACHED") and p.get("relevant") is not None)
    if stop_reason == "NORMAL_COMPLETION" and args.max_new_calls is not None and new_calls_count >= args.max_new_calls:
        stop_reason = "MAX_NEW_CALLS_REACHED"
    manifest = {
        "run_id": run_id,
        "started_at": run_started.isoformat(),
        "finished_at": finished_at.isoformat(),
        "provider": client.provider,
        "model": client.model,
        "prompt_version": args.prompt_version,
        "temperature": args.temperature,
        "corpus_version": "0.1.0",
        "requested_max_new_calls": args.max_new_calls,
        "valid_before": valid_before,
        "pending_before": total_in_corpus - valid_before,
        "cache_hits": cached_count,
        "api_calls_attempted": api_calls_attempted,
        "api_calls_successful": api_calls_successful,
        "api_calls_failed": api_calls_failed,
        "valid_after": valid_after,
        "pending_after": total_in_corpus - valid_after,
        "stop_reason": stop_reason,
        "rate_limit_events": rate_limit_events,
        "timeout_events": sum(r.error_type == "TIMEOUT" for r in results),
        "http_4xx_events": sum(r.http_status is not None and 400 <= r.http_status < 500 for r in results),
        "http_5xx_events": sum(r.http_status is not None and 500 <= r.http_status < 600 for r in results),
        "schema_error_events": sum(r.error_type == "SCHEMA_INVALID" for r in results),
        "network_error_events": sum(r.error_type == "NETWORK_TRANSIENT" for r in results),
        "duration_ms": round((finished_at - run_started).total_seconds() * 1000, 2),
    }
    write_run_manifest(manifest_path, manifest)
    print(f"Manifesto salvo em: {manifest_path} | stop_reason={stop_reason}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
