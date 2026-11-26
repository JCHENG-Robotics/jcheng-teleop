"""Deterministic tick runner for M1/M3.

The optional `observer` receives every tick result and the sample consumed by
that tick. It is an observation hook (capture recorder, tracing): an exception
is counted and swallowed, and a `False` return requests a system stop so a
recorder fault cannot leave the session running. The default path has no
observer and is byte-identical to M1.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .clock import ManualClock
from .model import InputSample, TickResult
from .session import TeleopSession
from ..adapters.input.base import InputSource

Observer = Callable[[TickResult, "InputSample | None", int], "bool | None"]


@dataclass
class TeleopRunner:
    session: TeleopSession
    source: InputSource
    clock: ManualClock
    tick_ns: int = 20_000_000
    stop_file: str | Path | None = None
    results: list[TickResult] = field(default_factory=list)
    on_tick: Callable[[TickResult], None] | None = None
    observer: Observer | None = None
    observer_errors: int = 0

    def _observe(self, result: TickResult, sample: InputSample | None, now: int) -> bool:
        """Return False when the observer asks for a stop."""
        if self.observer is None:
            return True
        try:
            return self.observer(result, sample, now) is not False
        except Exception:
            self.observer_errors += 1
            return True

    def _stop(self, reason: str, now: int) -> TickResult:
        stop_sent, stop_events = self.session.stop(reason, system=True, now_ns=now)
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
        return result

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
                    self._stop("operator_stop", now)
                    break
                sample = self.source.poll(now)
                if sample is not None:
                    self.session.on_sample(sample)
                result = self.session.tick(now)
                self.results.append(result)
                if self.on_tick is not None:
                    self.on_tick(result)
                if not self._observe(result, sample, now):
                    self._stop("recorder_fault", now)
                    break
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
