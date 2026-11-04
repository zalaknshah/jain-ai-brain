"""Bounded in-process peer-address rate accounting for the local HTTP server."""
from __future__ import annotations

import math
import time
from threading import Lock


def bounded_int(name: str, value: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= maximum:
        raise ValueError(f"{name} must be an integer between 1 and {maximum}")
    return value


class PeerRateLimiter:
    def __init__(self, per_minute: int = 60, burst: int = 30, max_clients: int = 1024, *, clock=time.monotonic):
        self.rate = bounded_int("rate_per_minute", per_minute, 60_000) / 60.0
        self.burst = bounded_int("rate_burst", burst, 10_000)
        self.max_clients = bounded_int("rate_max_clients", max_clients, 10_000)
        self.idle_ttl = max(60.0, self.burst / self.rate)
        self._clock = clock
        self._lock = Lock()
        self._buckets: dict[str, tuple[float, float]] = {}

    def allow(self, peer: str) -> tuple[bool, int]:
        with self._lock:
            now = self._clock()
            # Idle buckets have fully replenished, so removing them does not
            # grant extra capacity. Never evict an active peer to admit a new one.
            expired = [key for key, (_, last) in self._buckets.items() if now - last >= self.idle_ttl]
            for key in expired:
                del self._buckets[key]
            bucket = self._buckets.get(peer)
            if bucket is None:
                if len(self._buckets) >= self.max_clients:
                    remaining = min(self.idle_ttl - (now - last) for _, last in self._buckets.values())
                    return False, max(1, math.ceil(remaining))
                tokens = float(self.burst)
            else:
                tokens, last = bucket
                tokens = min(float(self.burst), tokens + max(0.0, now - last) * self.rate)
            allowed = tokens >= 1.0
            self._buckets[peer] = (tokens - 1.0 if allowed else tokens, now)
            return allowed, 0 if allowed else max(1, math.ceil((1.0 - tokens) / self.rate))
