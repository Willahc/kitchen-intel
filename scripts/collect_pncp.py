"""CLI controlada para coletar snapshots Bronze do PNCP."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# Permite `python scripts/collect_pncp.py` a partir da raiz do repositório,
# sem exigir instalação do pacote neste Gate.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.collectors.pncp import PncpCollector, PncpCollectorError
from src.config import PncpCollectionConfig
from src.logging_config import configure_logging


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Coleta Bronze da API oficial de consultas do PNCP.")
    parser.add_argument("--start-date", required=True, help="Data inicial no formato AAAAMMDD.")
    parser.add_argument("--end-date", required=True, help="Data final no formato AAAAMMDD.")
    parser.add_argument("--modality-code", type=int, default=6, help="Código PNCP da modalidade (padrão: 6).")
    parser.add_argument("--page-size", type=int, default=10, help="Registros solicitados por página (padrão: 10).")
    parser.add_argument("--start-page", type=int, default=1, help="Página inicial (padrão: 1).")
    parser.add_argument("--max-pages", type=int, default=1, help="Máximo de páginas nesta execução (padrão: 1).")
    parser.add_argument("--output-dir", type=Path, default=Path("data/bronze/pncp"), help="Diretório raiz Bronze.")
    parser.add_argument("--timeout-seconds", type=float, default=20.0, help="Timeout HTTP por tentativa.")
    parser.add_argument("--max-attempts", type=int, default=3, help="Tentativas máximas para falhas transitórias.")
    parser.add_argument("--verbose", action="store_true", help="Ativa logs de depuração.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    configure_logging(args.verbose)
    try:
        config = PncpCollectionConfig(
            start_date=args.start_date,
            end_date=args.end_date,
            modality_code=args.modality_code,
            page_size=args.page_size,
            max_pages=args.max_pages,
            start_page=args.start_page,
            timeout_seconds=args.timeout_seconds,
            max_attempts=args.max_attempts,
            output_dir=args.output_dir,
        )
        result = PncpCollector(config).collect()
    except (ValueError, PncpCollectorError) as error:
        logging.getLogger(__name__).error("Coleta falhou: %s", error)
        return 1
    logging.getLogger(__name__).info(
        "Resultado: paginas=%s registros=%s arquivos=%s",
        result.pages_collected,
        result.records_collected,
        ", ".join(str(path) for path in result.files),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
