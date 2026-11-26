"""Deterministic tick runner for M1."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .clock import ManualClock
from .model import TickResult
from .session import TeleopSession
from ..adapters.input.base import InputSource


@dataclass
class TeleopRunner:
    session: TeleopSession
    source: InputSource
    clock: ManualClock
    tick_ns: int = 20_000_000
    stop_file: str | Path | None = None
    results: list[TickResult] = field(default_factory=list)
    on_tick: Callable[[TickResult], None] | None = None

    def run_ticks(self, ticks: int, *, start_ns: int | None = None) -> list[TickResult]:
        if ticks < 0:
            raise ValueError("ticks must be non-negative")
        if start_ns is not None:
            self.clock.set(start_ns)
        self.source.open()
        try:
            for _ in range(ticks):
                now = self.clock.now_ns()
                if self.stop_file is not None and Path(self.stop_file).exists():
                    stop_sent, stop_events = self.session.stop(
                        "operator_stop", system=True, now_ns=now
                    )
                    result = TickResult(
                        state=self.session.state,
                        intent=None,
                        events=stop_events,
                        submitted=False,
                        gateway_result=None,
                        stop_sent=stop_sent,
                    )
                    self.results.append(result)
                    if self.on_tick is not None:
                        self.on_tick(result)
                    break
                sample = self.source.poll(now)
                if sample is not None:
                    self.session.on_sample(sample)
                result = self.session.tick(now)
                self.results.append(result)
                if self.on_tick is not None:
                    self.on_tick(result)
                self.clock.advance(self.tick_ns)
        finally:
            self.source.close()
        return self.results

    def run_until(self, end_ns: int, *, start_ns: int | None = None) -> list[TickResult]:
        if start_ns is not None:
            self.clock.set(start_ns)
        if end_ns < self.clock.now_ns():
            raise ValueError("end_ns is before the clock")
        ticks = (end_ns - self.clock.now_ns()) // self.tick_ns
        return self.run_ticks(ticks)
