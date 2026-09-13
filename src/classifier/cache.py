"""Gerenciamento de cache determinístico de inferência de LLM (Gate 5)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


class LLMCache:
    """Cache em disco indexado por hash de entrada, provedor, modelo e versão de prompt."""

    def __init__(self, cache_file: Path | None = None) -> None:
        self.cache_file = cache_file or Path("data/cache/llm_cache_v0.1.0.json")
        self._entries: dict[str, dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        if self.cache_file.exists():
            try:
                content = self.cache_file.read_text(encoding="utf-8")
                self._entries = json.loads(content)
            except Exception:
                self._entries = {}
        else:
            self._entries = {}

    def _save(self) -> None:
        self.cache_file.parent.mkdir(parents=True, exist_ok=True)
        self.cache_file.write_text(
            json.dumps(self._entries, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    @staticmethod
    def generate_key(input_hash: str, provider: str, model: str, prompt_version: str) -> str:
        """Gera chave criptográfica única para combinação de entrada + parâmetros do modelo."""
        raw = f"{input_hash}:{provider.strip().lower()}:{model.strip().lower()}:{prompt_version.strip()}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def get(self, cache_key: str) -> dict[str, Any] | None:
        return self._entries.get(cache_key)

    def set(self, cache_key: str, data: dict[str, Any]) -> None:
        self._entries[cache_key] = data
        self._save()

    def size(self) -> int:
        return len(self._entries)
