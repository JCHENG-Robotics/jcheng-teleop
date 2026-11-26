"""Clocks for the deterministic core."""

from __future__ import annotations

import time
from typing import Protocol


class Clock(Protocol):
    def now_ns(self) -> int: ...


class SystemClock:
    """Monotonic host clock in nanoseconds."""

    def now_ns(self) -> int:
        return time.monotonic_ns()


class ManualClock:
    """Injectable clock used by tests and replay."""

    def __init__(self, now_ns: int = 0) -> None:
        self._now_ns = int(now_ns)

    def now_ns(self) -> int:
        return self._now_ns

    def set(self, now_ns: int) -> None:
        if now_ns < self._now_ns:
            raise ValueError("manual clock cannot move backwards")
        self._now_ns = int(now_ns)

    def advance(self, delta_ns: int) -> int:
        if delta_ns < 0:
            raise ValueError("manual clock cannot move backwards")
        self._now_ns += int(delta_ns)
        return self._now_ns
