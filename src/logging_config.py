"""Configuração mínima de logs para execução via CLI."""

from __future__ import annotations

import logging


def configure_logging(verbose: bool = False) -> None:
    """Configura logs de execução uma vez, enviados para stderr."""
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
