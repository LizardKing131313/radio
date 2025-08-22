"""
Backoff policy and state for process restarts.
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass, field


@dataclass(slots=True)
class BackoffPolicy:
    base_s: float = 0.5
    factor: float = 2.0
    max_s: float = 30.0
    jitter_s: float = 0.4  # +/- uniform jitter
    reset_after_ok_s: float = 60.0  # uptime threshold to reset attempts
    max_restarts_in_window: int = 20
    window_s: float = 300.0  # rolling time window for breaker


@dataclass(slots=True)
class BackoffState:
    policy: BackoffPolicy
    attempt: int = 0
    recent_starts: list[float] = field(default_factory=list)

    def next_delay_with_jitter(self) -> float:
        base = min(
            self.policy.max_s,
            self.policy.base_s * (self.policy.factor ** max(self.attempt - 1, 0)),
        )
        jitter = random.uniform(-self.policy.jitter_s, self.policy.jitter_s)
        return max(0.0, base + jitter)

    def register_start(self) -> None:
        now = time.monotonic()
        self.recent_starts.append(now)
        cutoff = now - self.policy.window_s
        self.recent_starts = [t for t in self.recent_starts if t >= cutoff]
        self.attempt += 1

    def reset_if_uptime_good(self, uptime_s: float) -> None:
        if uptime_s >= self.policy.reset_after_ok_s:
            self.attempt = 0

    def too_many_restarts(self) -> bool:
        return len(self.recent_starts) > self.policy.max_restarts_in_window
