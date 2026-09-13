"""Circuit Breaker local e determinístico para controle de falhas por provedor LLM.

Implementa os estados canônicos:
- CLOSED: Operação normal, requisições permitidas.
- OPEN: Provedor com falhas recorrentes, chamadas bloqueadas temporariamente.
- HALF_OPEN: Período de teste para avaliar se o provedor se recuperou.
"""

from __future__ import annotations

import time
from enum import Enum
from typing import Callable


class CircuitState(str, Enum):
    """Estados canônicos de um Circuit Breaker."""

    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class CircuitBreaker:
    """Controlador de circuito por provedor com transições determinísticas."""

    def __init__(
        self,
        failure_threshold: int = 3,
        cooldown_seconds: float = 60.0,
        time_fn: Callable[[], float] | None = None,
    ) -> None:
        self.failure_threshold = max(1, failure_threshold)
        self.cooldown_seconds = max(0.1, cooldown_seconds)
        self.time_fn = time_fn or time.time
        self.consecutive_failures = 0
        self.state = CircuitState.CLOSED
        self.opened_at: float | None = None
        self.last_failure_error_type: str | None = None

    def can_attempt(self) -> bool:
        """Determina se uma nova tentativa é permitida para este provedor."""
        if self.state == CircuitState.CLOSED:
            return True

        now = self.time_fn()
        if self.state == CircuitState.OPEN:
            if self.opened_at is not None and (now - self.opened_at) >= self.cooldown_seconds:
                # Transição para teste controlado
                self.state = CircuitState.HALF_OPEN
                return True
            return False

        if self.state == CircuitState.HALF_OPEN:
            # Já está no estado de prova; permite a chamada de teste
            return True

        return False

    def record_success(self) -> None:
        """Registra uma chamada bem-sucedida, fechando o circuito."""
        self.consecutive_failures = 0
        self.state = CircuitState.CLOSED
        self.opened_at = None
        self.last_failure_error_type = None

    def record_failure(self, error_type: str | None = None) -> None:
        """Registra uma falha e abre o circuito se o limiar for atingido."""
        self.consecutive_failures += 1
        self.last_failure_error_type = error_type
        now = self.time_fn()

        if self.state == CircuitState.HALF_OPEN:
            # Falha durante a tentativa de recuperação: reabre imediatamente
            self.state = CircuitState.OPEN
            self.opened_at = now
        elif self.state == CircuitState.CLOSED:
            if self.consecutive_failures >= self.failure_threshold:
                self.state = CircuitState.OPEN
                self.opened_at = now

    def reset(self) -> None:
        """Restaura forçadamente o circuito para CLOSED."""
        self.consecutive_failures = 0
        self.state = CircuitState.CLOSED
        self.opened_at = None
        self.last_failure_error_type = None

    def get_status_dict(self) -> dict[str, str | int | float | None]:
        """Retorna representação serializável do estado atual do circuito."""
        return {
            "state": self.state.value,
            "consecutive_failures": self.consecutive_failures,
            "failure_threshold": self.failure_threshold,
            "cooldown_seconds": self.cooldown_seconds,
            "opened_at": self.opened_at,
            "last_failure_error_type": self.last_failure_error_type,
        }
