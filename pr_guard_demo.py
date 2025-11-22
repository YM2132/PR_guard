from __future__ import annotations

from dataclasses import dataclass, field
from time import time
from typing import List


@dataclass
class InMemoryRateLimiter:
    """
    Very small in-memory rate limiter.

    allow() returns True while the number of calls in the last `period_seconds`
    is strictly less than `max_calls`, otherwise False.
    """

    max_calls: int
    period_seconds: float
    timestamps: List[float] = field(default_factory=list)

    def allow(self) -> bool:
        """Return True if a call is allowed under the current rate limit, False otherwise."""
        now = time()
        cutoff = now - self.period_seconds

        # Keep only timestamps that are still inside the window
        self.timestamps = [t for t in self.timestamps if t >= cutoff]

        # If we've already seen max_calls in the window, block
        if len(self.timestamps) >= self.max_calls:
            return False

        # Otherwise record this call and allow it
        self.timestamps.append(now)
        return True
