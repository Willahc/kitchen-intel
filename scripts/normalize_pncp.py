"""CLI para reconstruir Silver PNCP exclusivamente a partir de Bronze."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.logging_config import configure_logging
from src.normalizers.pncp import PncpNormalizationError, normalize_bronze_directory


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Normaliza Bronze PNCP em JSON Lines Silver.")
    parser.add_argument("--input-dir", type=Path, default=Path("data/bronze/pncp"))
    parser.add_argument("--output-dir", type=Path, default=Path("data/silver/pncp"))
    parser.add_argument("--limit", type=int, help="Limita registros brutos processados nesta execução.")
    parser.add_argument("--verbose", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    configure_logging(args.verbose)
    try:
        result = normalize_bronze_directory(args.input_dir, args.output_dir, PROJECT_ROOT, args.limit)
    except (ValueError, PncpNormalizationError, OSError) as error:
        logging.getLogger(__name__).error("Normalização falhou: %s", error)
        return 1
    logging.getLogger(__name__).info(
        "Resultado raw=%s validos=%s rejeitados=%s duplicatas=%s silver=%s manifest=%s",
        result.raw_record_count,
        result.valid_record_count,
        result.rejected_count,
        result.duplicate_count,
        result.silver_file,
        result.manifest_file,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
