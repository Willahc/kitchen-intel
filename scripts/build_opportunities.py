"""CLI do Opportunity Engine determinístico do Gate 3."""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.logging_config import configure_logging
from src.opportunity.engine import build_gold


def main() -> int:
    parser = argparse.ArgumentParser(description="Gera Gold explicável a partir de Silver PNCP.")
    parser.add_argument("--input-dir", type=Path, default=Path("data/silver/pncp"))
    parser.add_argument("--output-dir", type=Path, default=Path("data/gold/opportunities"))
    parser.add_argument("--rules", type=Path, default=Path("config/opportunity_rules.json"))
    parser.add_argument("--as-of", type=date.fromisoformat, default=date.today(), help="Data de referência AAAA-MM-DD.")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    configure_logging(args.verbose)
    try:
        result = build_gold(args.input_dir, args.output_dir, PROJECT_ROOT, args.rules, args.as_of)
    except (OSError, ValueError) as error:
        logging.getLogger(__name__).error("Geração Gold falhou: %s", error)
        return 1
    logging.getLogger(__name__).info("Gold concluído input=%s relevantes=%s irrelevantes=%s arquivo=%s manifest=%s", result.input_record_count, result.relevant_count, result.irrelevant_count, result.gold_file, result.manifest_file)
    return 0


if __name__ == "__main__":
    sys.exit(main())
