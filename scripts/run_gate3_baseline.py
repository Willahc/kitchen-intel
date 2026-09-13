"""Executa os golden cases e salva o relatório do baseline determinístico."""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.opportunity.benchmark import evaluate_golden_cases, write_benchmark_report


def main() -> int:
    parser = argparse.ArgumentParser(description="Executa benchmark determinístico do Gate 3.")
    parser.add_argument("--cases", type=Path, default=Path("tests/fixtures/golden_opportunity_cases.json"))
    parser.add_argument("--rules", type=Path, default=Path("config/opportunity_rules.json"))
    parser.add_argument("--output", type=Path, default=Path("reports/baseline_gate3.json"))
    parser.add_argument("--as-of", type=date.fromisoformat, default=date.today())
    args = parser.parse_args()
    report = evaluate_golden_cases(args.cases, args.rules, args.as_of)
    write_benchmark_report(report, args.output)
    print(f"baseline cases={report['case_count']} accuracy={report['accuracy_relevance']} precision={report['precision_relevant']} recall={report['recall_relevant']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
