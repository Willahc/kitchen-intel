"""Leitura segura do snapshot Gold mais recente."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class GoldRepository:
    """Repositório em arquivo, sem escrita e sem caminhos fornecidos pelo cliente."""

    def __init__(self, gold_dir: Path) -> None:
        self.gold_dir = gold_dir

    def records(self) -> list[dict[str, Any]]:
        gold_file = self._latest_gold_file()
        try:
            return [json.loads(line) for line in gold_file.read_text(encoding="utf-8").splitlines() if line.strip()]
        except (OSError, json.JSONDecodeError) as error:
            raise RuntimeError(f"Gold inválido ou indisponível: {error}") from error

    def _latest_gold_file(self) -> Path:
        candidates = list(self.gold_dir.glob("opportunities_*.jsonl"))
        if not candidates:
            raise RuntimeError("Nenhum snapshot Gold encontrado")
        return max(candidates, key=lambda path: path.stat().st_mtime)
