"""Deadman enable-edge and staleness tracking."""

from __future__ import annotations

from dataclasses import dataclass

from .model import InputSample, Severity, TeleopEvent


@dataclass(frozen=True)
class DeadmanUpdate:
    enabled: bool
    expired: bool
    events: tuple[TeleopEvent, ...]


class DeadmanTracker:
    """Hold-to-run enable with a timeout and a required fresh edge.

    ``block()`` is called after a stop/fault. The operator must release the
    enable input and press it again before motion can resume.
    """

    def __init__(self, timeout_ns: int) -> None:
        if timeout_ns <= 0:
            raise ValueError("deadman timeout must be positive")
        self.timeout_ns = int(timeout_ns)
        self.enabled = False
        self.expired = True
        self._last_sample_ns: int | None = None
        self._blocked = False
    @property
    def last_sample_ns(self) -> int | None:
        return self._last_sample_ns

    @property
    def blocked(self) -> bool:
        return self._blocked

    def block(self) -> None:
        self._blocked = True
        self.enabled = False
        # A blocked session is not ready until a fresh release/enable edge.
        self.expired = True
        self._timeout_event_sent = False

    def update(self, sample: InputSample, now_ns: int) -> DeadmanUpdate:
        events: list[TeleopEvent] = []
        self._last_sample_ns = int(now_ns)
        self.expired = False
        if not sample.deadman:
            if self.enabled:
                events.append(
                    TeleopEvent("DEADMAN_RELEASED", Severity.INFO, now_ns, {"seq": sample.seq})
                )
            self.enabled = False
            if self._blocked:
                self._blocked = False
            return DeadmanUpdate(False, False, tuple(events))
        if self._blocked:
            return DeadmanUpdate(False, False, ())
        if not self.enabled:
            self.enabled = True
            events.append(TeleopEvent("DEADMAN_ENGAGED", Severity.INFO, now_ns, {"seq": sample.seq}))
        return DeadmanUpdate(True, False, tuple(events))

    def check(self, now_ns: int) -> DeadmanUpdate:
        if self._last_sample_ns is None:
            self.expired = True
            return DeadmanUpdate(False, True, ())
        if now_ns - self._last_sample_ns >= self.timeout_ns:
            self.expired = True
            events: list[TeleopEvent] = []
            if self.enabled:
                self.enabled = False
                self._blocked = True
                events.append(
                    TeleopEvent(
                        "INPUT_STALE",
                        Severity.FAULT,
                        now_ns,
                        {"age_ns": now_ns - self._last_sample_ns, "timeout_ns": self.timeout_ns},
                    )
                )
            return DeadmanUpdate(False, True, tuple(events))
        return DeadmanUpdate(self.enabled, False, ())
