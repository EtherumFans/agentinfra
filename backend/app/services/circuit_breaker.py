"""Circuit breaker for LLM service — fast-fail when provider is unhealthy."""
import time
import logging
from enum import Enum

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    CLOSED = "closed"        # Normal operation
    OPEN = "open"            # Requests fail immediately
    HALF_OPEN = "half_open"  # Probing recovery


class CircuitBreaker:
    """Protects downstream LLM calls from cascading retries when the provider is down.

    State transitions:
      CLOSED → OPEN: consecutive failures exceed threshold
      OPEN → HALF_OPEN: timeout expires, allowing one probe
      HALF_OPEN → CLOSED: probe succeeds
      HALF_OPEN → OPEN: probe fails
    """

    def __init__(self, name: str = "llm",
                 failure_threshold: int = 20,
                 recovery_timeout: float = 30.0):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.state = CircuitState.CLOSED
        self._failures = 0
        self._last_failure_time: float = 0
        self._opened_at: float = 0

    @property
    def is_open(self) -> bool:
        if self.state == CircuitState.CLOSED:
            return False
        if self.state == CircuitState.OPEN:
            if time.time() - self._opened_at >= self.recovery_timeout:
                self.state = CircuitState.HALF_OPEN
                logger.info(f"CircuitBreaker({self.name}): OPEN → HALF_OPEN (probing)")
                return False
            return True
        # HALF_OPEN: allow one probe
        return False

    def record_success(self):
        if self.state == CircuitState.HALF_OPEN:
            self.state = CircuitState.CLOSED
            self._failures = 0
            logger.info(f"CircuitBreaker({self.name}): HALF_OPEN → CLOSED (recovered)")
        elif self.state == CircuitState.CLOSED:
            self._failures = 0

    def record_failure(self):
        self._failures += 1
        self._last_failure_time = time.time()
        if self.state == CircuitState.HALF_OPEN:
            self.state = CircuitState.OPEN
            self._opened_at = time.time()
            logger.warning(f"CircuitBreaker({self.name}): HALF_OPEN → OPEN (probe failed)")
        elif self.state == CircuitState.CLOSED and self._failures >= self.failure_threshold:
            self.state = CircuitState.OPEN
            self._opened_at = time.time()
            logger.warning(f"CircuitBreaker({self.name}): CLOSED → OPEN ({self._failures} failures)")

    def status(self) -> dict:
        return {
            "name": self.name,
            "state": self.state.value,
            "failures": self._failures,
            "last_failure": self._last_failure_time,
            "opened_at": self._opened_at,
        }


# Global singleton
llm_circuit_breaker = CircuitBreaker(name="llm")
