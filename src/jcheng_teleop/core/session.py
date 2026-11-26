"""Deterministic teleoperation session state machine."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from .clock import Clock
from .conditioning import Conditioner
from .deadman import DeadmanTracker
from .gateway import GatewayError, GatewayPort
from .mapper import ActionMapper
from .model import (
    ActionIntent,
    GatewayResult,
    InputSample,
    Lease,
    LeaseRequest,
    Mode,
    RejectedSample,
    RejectionCode,
    SessionState,
    Severity,
    TeleopEvent,
    TickResult,
)
from .profile import ResolvedProfile
from .safety import SafetyGuard, SafetyLimits


@dataclass(frozen=True)
class SessionConfig:
    deadman_ms: int = 300
    tick_ms: int = 20
    max_rate_hz: int = 50
    lease_ttl_ms: int = 1000
    lease_scope: str = "full"
    lease_priority: int = 40
    auto_acquire: bool = True
    contract_hash: str = ""

    def __post_init__(self) -> None:
        if self.deadman_ms <= 0 or self.tick_ms <= 0 or self.max_rate_hz <= 0:
            raise ValueError("session timing must be positive")
        if self.lease_ttl_ms <= 0:
            raise ValueError("lease_ttl_ms must be positive")
        if self.lease_scope not in {"arm", "gripper", "base", "full"}:
            raise ValueError("invalid lease scope")


class TeleopSession:
    def __init__(
        self,
        profile: ResolvedProfile,
        gateway: GatewayPort,
        clock: Clock,
        *,
        config: SessionConfig | None = None,
        holder: str = "teleop:session",
    ) -> None:
        self.profile = profile
        self.gateway = gateway
        self.clock = clock
        self.config = config or SessionConfig()
        self.holder = holder
        self.state = SessionState.BOOT
        self.conditioner = Conditioner(profile)
        self.deadman = DeadmanTracker(self.config.deadman_ms * 1_000_000)
        self.mapper = ActionMapper(profile)
        self.guard = SafetyGuard(
            profile,
            SafetyLimits(
                deadman_ms=self.config.deadman_ms,
                tick_ms=self.config.tick_ms,
                max_rate_hz=self.config.max_rate_hz,
            ),
        )
        self.lease: Lease | None = None
        self.last_sample: InputSample | None = None
        self.last_conditioned = None
        self.last_intent: ActionIntent | None = None
        self.last_stop_intent: ActionIntent | None = None
        self._conditioned_seq: int | None = None
        self._conditioned_source_ns: int | None = None
        self._wire_seq = 0
        self._min_submit_interval_ns = max(
            self.config.tick_ms * 1_000_000,
            int(1_000_000_000 / self.config.max_rate_hz),
        )
        self._last_submit_ns: int | None = None
        self._last_tick_ns: int | None = None
        self._renew_at_ns: int | None = None
        self._pending_events: list[TeleopEvent] = []
        self._release_seen = False
        self._active_mode: Mode | None = None
        self._contract_hash: str | None = None
        self._lease_error: str | None = None
        self._last_arrival_key: tuple[int, int, int] | None = None
        self._closed = False

    # ---- lifecycle ----

    def _event(self, code: str, severity: Severity, detail: dict[str, Any] | None = None) -> TeleopEvent:
        return TeleopEvent(code, severity, self.clock.now_ns(), detail or {})

    def _fail(self, code: str, message: str) -> None:
        self.state = SessionState.FAULT
        self._pending_events.append(self._event(code, Severity.FAULT, {"message": message}))
        self.deadman.block()
        self._release_lease()

    def start(self) -> tuple[TeleopEvent, ...]:
        if self.state is not SessionState.BOOT:
            raise RuntimeError("session already started")
        self.state = SessionState.SELFTEST
        events: list[TeleopEvent] = []
        try:
            admission = self.gateway.admit()
        except GatewayError as exc:
            self._fail("GATEWAY_UNAVAILABLE", str(exc))
            return self._drain()
        if not admission.mock:
            self._fail("ENVIRONMENT_INVALID", "M1 only admits a mock gateway")
            return self._drain()
        self._contract_hash = admission.contract_hash
        if self.config.contract_hash and admission.contract_hash != self.config.contract_hash:
            self._fail("CONTRACT_MISMATCH", "gateway contract hash mismatch")
            return self._drain()
        if admission.profile_hash != self.profile.profile_hash:
            self._fail("PROFILE_MISMATCH", "gateway profile hash mismatch")
            return self._drain()
        if self.config.auto_acquire:
            try:
                self.lease = self.gateway.acquire(
                    LeaseRequest(
                        holder=self.holder,
                        scope=self.config.lease_scope,
                        mode="exclusive",
                        priority=self.config.lease_priority,
                        ttl_ms=self.config.lease_ttl_ms,
                        deadman_required=True,
                        contract_hash=admission.contract_hash,
                    )
                )
            except GatewayError as exc:
                self._fail("LEASE_INVALID", str(exc))
                return self._drain()
            self._renew_at_ns = self.clock.now_ns() + self.config.lease_ttl_ms * 333_333
        self.state = SessionState.IDLE
        events.append(self._event("SESSION_IDLE", Severity.INFO))
        self._pending_events.extend(events)
        return tuple(events)

    def provide_lease(self, lease: Lease) -> None:
        if self.state not in {SessionState.SELFTEST, SessionState.IDLE}:
            raise RuntimeError("lease can only be provided before activation")
        if self._contract_hash is not None and lease.contract_hash != self._contract_hash:
            raise ValueError("lease contract hash does not match admission")
        if lease.scope not in {"arm", "gripper", "full"}:
            raise ValueError("lease scope does not cover arm intent")
        if not lease.active(self.clock.now_ns()):
            raise ValueError("lease is already expired")
        self.lease = lease
        self._renew_at_ns = self.clock.now_ns() + self.config.lease_ttl_ms * 333_333

    # ---- input ----

    def on_sample(self, sample: InputSample) -> tuple[TeleopEvent, ...]:
        if self.state in {SessionState.CLOSED, SessionState.FAULT, SessionState.PREEMPTED}:
            return ()
        if sample.profile_id is not None and sample.profile_id != self.profile.profile_id:
            event = self._event("PROFILE_MISMATCH", Severity.FAULT, {"sample_profile": sample.profile_id})
            self._pending_events.append(event)
            if self.state in {SessionState.ACTIVE, SessionState.READY}:
                _, stop_events = self.stop("profile_mismatch", system=False)
                self._pending_events.extend(stop_events)
            return self._drain()
        arrival_key = (sample.seq, sample.t_source_ns, sample.t_host_mono_ns)
        if arrival_key == self._last_arrival_key:
            event = self._event("SEQ_DUPLICATE", Severity.WARNING, {"seq": sample.seq, "message": "exact duplicate arrival"})
            self._pending_events.append(event)
            if self.state is SessionState.ACTIVE:
                _, stop_events = self.stop("duplicate_input", system=False)
                self._pending_events.extend(stop_events)
            return self._drain()
        self._last_arrival_key = arrival_key
        self.last_sample = sample
        now = self.clock.now_ns()
        if self.state is SessionState.IDLE and not (self._lease_valid(now) and self._state_valid(now)):
            # No authority: a held enable must not become a latent activation
            # when a lease or fresh state appears later. Require a fresh edge.
            if sample.deadman:
                self.deadman.block()
        update = self.deadman.update(sample, now)
        events = list(update.events)
        if self.state is SessionState.ACTIVE and not sample.deadman:
            # Latch the release so a re-press inside the same tick cannot erase it.
            self._release_seen = True
        if self.state is SessionState.IDLE and self._lease_valid() and self._state_valid():
            self.state = SessionState.READY
            events.append(self._event("SESSION_READY", Severity.INFO))
        if self.state is SessionState.READY and update.enabled:
            self.state = SessionState.ACTIVE
            events.append(self._event("SESSION_ACTIVE", Severity.INFO))
        if self.state is SessionState.ACTIVE and not update.enabled:
            self._pending_events.append(self._event("DEADMAN_RELEASE_STOP", Severity.WARNING))
        self._pending_events.extend(events)
        return tuple(events)

    # ---- tick ----

    def tick(self, now_ns: int | None = None) -> TickResult:
        now = self.clock.now_ns() if now_ns is None else int(now_ns)
        self.last_stop_intent = None
        events = list(self._pending_events)
        self._pending_events.clear()
        previous_tick = self._last_tick_ns
        delta = None if previous_tick is None else now - previous_tick
        if (
            delta is not None
            and self.config.tick_ms * 1_000_000 < delta <= 2 * self.config.tick_ms * 1_000_000
        ):
            events.append(self._event("LOOP_OVERRUN", Severity.WARNING, {"delta_ns": delta}))
        self._last_tick_ns = now
        if (
            delta is not None
            and delta > 2 * self.config.tick_ms * 1_000_000
            and self.state in {SessionState.ACTIVE, SessionState.READY}
        ):
            events.append(self._event("LOOP_WATCHDOG", Severity.FAULT, {"delta_ns": delta}))
            stop_sent, stop_events = self.stop("loop_overrun", system=False, now_ns=now)
            events.extend(stop_events)
            return TickResult(self.state, None, tuple(events), False, None, stop_sent)
        intent: ActionIntent | None = None
        submitted = False
        result: GatewayResult | None = None
        stop_sent = False

        if self.state in {SessionState.BOOT, SessionState.SELFTEST, SessionState.CLOSED}:
            return TickResult(self.state, None, tuple(events), False, None, False)

        if self.state is SessionState.FAULT:
            return TickResult(self.state, None, tuple(events), False, None, False)

        if self.state is SessionState.IDLE:
            deadman = self.deadman.check(now)
            events.extend(deadman.events)
            if self._lease_valid(now) and self._state_valid(now) and self.last_sample is not None:
                if not deadman.expired:
                    self.state = SessionState.READY
                    events.append(self._event("SESSION_READY", Severity.INFO))
            return TickResult(self.state, None, tuple(events), False, None, False)

        if self.state is SessionState.READY:
            deadman = self.deadman.check(now)
            events.extend(deadman.events)
            if deadman.expired:
                self.state = SessionState.IDLE
                return TickResult(self.state, None, tuple(events), False, None, False)
            if not self._lease_valid(now):
                stop_sent, stop_events = self.stop(
                    "lease_lost", system=False, now_ns=now, preempted=True
                )
                events.extend(stop_events)
                return TickResult(self.state, None, tuple(events), False, None, stop_sent)
            if not self._state_valid(now):
                self._fail("STATE_STALE", "state stale before activation")
                events.extend(self._drain())
                return TickResult(self.state, None, tuple(events), False, None, False)
            if self.deadman.enabled:
                self.state = SessionState.ACTIVE
                events.append(self._event("SESSION_ACTIVE", Severity.INFO))
            return TickResult(self.state, None, tuple(events), False, None, False)

        if self.state is SessionState.PREEMPTED:
            return TickResult(self.state, None, tuple(events), False, None, False)

        # ACTIVE
        if self._release_seen:
            stop_sent, stop_events = self.stop("deadman_release", system=False, now_ns=now)
            events.extend(stop_events)
            return TickResult(self.state, None, tuple(events), False, None, stop_sent)

        deadman = self.deadman.check(now)
        events.extend(deadman.events)
        if deadman.expired or not deadman.enabled:
            reason = "deadman_timeout" if deadman.expired else "deadman_release"
            stop_sent, stop_events = self.stop(reason, system=False, now_ns=now)
            events.extend(stop_events)
            return TickResult(self.state, None, tuple(events), False, None, stop_sent)

        if not self._lease_valid(now):
            stop_sent, stop_events = self.stop("lease_lost", system=False, now_ns=now, preempted=True)
            events.extend(stop_events)
            return TickResult(self.state, None, tuple(events), False, None, stop_sent)

        if not self._state_valid(now):
            stop_sent, stop_events = self.stop("state_stale", system=False, now_ns=now)
            events.extend(stop_events)
            return TickResult(self.state, None, tuple(events), False, None, stop_sent)

        if self.last_sample is None:
            stop_sent, stop_events = self.stop("input_missing", system=False, now_ns=now)
            events.extend(stop_events)
            return TickResult(self.state, None, tuple(events), False, None, stop_sent)

        if (
            self._last_submit_ns is not None
            and now - self._last_submit_ns < self._min_submit_interval_ns
        ):
            return TickResult(self.state, None, tuple(events), False, None, False)

        try:
            if (
                self._conditioned_seq != self.last_sample.seq
                or self._conditioned_source_ns != self.last_sample.t_source_ns
            ):
                conditioned = self.conditioner.process(self.last_sample)
                self.last_conditioned = conditioned
                self._conditioned_seq = self.last_sample.seq
                self._conditioned_source_ns = self.last_sample.t_source_ns
            else:
                conditioned = self.last_conditioned
            if conditioned is None:
                raise RejectedSample(RejectionCode.SAMPLE_INVALID, "no conditioned sample")
            events.extend(conditioned.events)
            if self._active_mode is None:
                self._active_mode = conditioned.mode
            elif conditioned.mode is not self._active_mode:
                stop_sent, stop_events = self.stop("mode_change", system=False, now_ns=now)
                events.extend(stop_events)
                return TickResult(self.state, None, tuple(events), False, None, stop_sent)
            intent = self.mapper.map(conditioned)
            intent = replace(intent, seq=self._next_wire_seq())
            if self.lease is not None:
                intent = replace(intent, lease_id=self.lease.lease_id)
            self.guard.validate(intent)
        except RejectedSample as exc:
            self._pending_events.append(self._event(exc.code, Severity.WARNING, {"message": str(exc)}))
            stop_sent, stop_events = self.stop("invalid_input", system=False, now_ns=now)
            events.extend(stop_events)
            events.extend(self._drain())
            return TickResult(self.state, None, tuple(events), False, None, stop_sent)

        if not self.gateway.supports_mode(intent.mode.value):
            stop_sent, stop_events = self.stop("mode_unsupported", system=False, now_ns=now)
            events.extend(stop_events)
            return TickResult(self.state, None, tuple(events), False, None, stop_sent)

        try:
            result = self.gateway.submit(intent)
        except GatewayError as exc:
            stop_sent, stop_events = self.stop("gateway_unavailable", system=True, now_ns=now)
            events.extend(stop_events)
            return TickResult(self.state, None, tuple(events), False, None, stop_sent)

        if result.outcome == "COMPLETED":
            self.last_intent = intent
            self._last_submit_ns = now
            submitted = True
        elif result.outcome == "REJECTED" and result.reason_code in {"MOTION_BUSY", "RATE_LIMITED"}:
            self._last_submit_ns = now
            submitted = False
        elif result.outcome == "UNKNOWN":
            stop_sent, stop_events = self.stop("gateway_unknown", system=True, now_ns=now)
            events.extend(stop_events)
        else:
            stop_sent, stop_events = self.stop("gateway_rejected", system=False, now_ns=now)
            events.extend(stop_events)
        return TickResult(self.state, intent if submitted else None, tuple(events), submitted, result, stop_sent)

    # ---- stop ----

    def stop(
        self,
        reason: str,
        *,
        system: bool = False,
        now_ns: int | None = None,
        preempted: bool = False,
    ) -> tuple[bool, tuple[TeleopEvent, ...]]:
        now = self.clock.now_ns() if now_ns is None else int(now_ns)
        events: list[TeleopEvent] = []
        if self.state in {SessionState.CLOSED, SessionState.FAULT, SessionState.PREEMPTED} and not system:
            return False, tuple(events)
        if self.state in {SessionState.ACTIVE, SessionState.READY}:
            self.state = SessionState.STOPPING
        stop_sent = False
        stop_failed = False
        if self.state is SessionState.STOPPING and self.last_intent is not None:
            stop_intent = self.guard.stop_intent(
                self.last_intent,
                self.last_intent.mode,
                seq=self._next_wire_seq(),
                t_source_ns=(self.last_sample.t_source_ns if self.last_sample is not None else now),
            )
            if stop_intent is not None:
                self.last_stop_intent = stop_intent
                try:
                    result = self.gateway.submit(stop_intent)
                    stop_sent = result.outcome == "COMPLETED"
                except GatewayError:
                    stop_sent = False
                if not stop_sent:
                    stop_failed = True
                    events.append(
                        self._event(
                            "STOP_INTENT_FAILED",
                            Severity.FAULT,
                            {"reason": reason, "sent": False},
                        )
                    )
                else:
                    events.append(
                        self._event("STOP_INTENT", Severity.WARNING, {"reason": reason, "sent": True})
                    )
        if system or stop_failed:
            try:
                stop_result = self.gateway.stop(reason)
                if not stop_result.accepted:
                    events.append(
                        self._event(
                            "SYSTEM_STOP_FAILED",
                            Severity.FAULT,
                            {"reason": reason, "accepted": False, "confirmed": stop_result.confirmed},
                        )
                    )
                else:
                    events.append(
                        self._event(
                            "SYSTEM_STOP",
                            Severity.FAULT,
                            {"reason": reason, "accepted": True, "confirmed": stop_result.confirmed},
                        )
                    )
            except GatewayError:
                events.append(self._event("SYSTEM_STOP_FAILED", Severity.FAULT, {"reason": reason}))
            self._release_lease()
            self.state = SessionState.FAULT
        else:
            self._release_lease()
            self.state = SessionState.PREEMPTED if preempted else SessionState.IDLE
            detail = {"reason": reason}
            if preempted and self._lease_error:
                detail["lease_error"] = self._lease_error
            events.append(
                self._event(
                    "SESSION_PREEMPTED" if preempted else "SESSION_ABORT",
                    Severity.WARNING,
                    detail,
                )
            )
        self.deadman.block()
        self.last_intent = None
        self._release_seen = False
        self._active_mode = None
        return stop_sent, tuple(events)

    def reset(self) -> tuple[TeleopEvent, ...]:
        """Local reset after a fault/preemption/session abort.

        This does not clear a system safety latch and does not auto-resume
        motion. It releases any lease and, in managed mode, acquires a new one;
        the operator must still produce a fresh release/enable edge.
        """
        if self.state not in {SessionState.FAULT, SessionState.PREEMPTED, SessionState.IDLE}:
            raise RuntimeError(f"reset requires FAULT/PREEMPTED/IDLE, not {self.state.value}")
        self._release_lease()
        events: list[TeleopEvent] = []
        if self.config.auto_acquire and self._contract_hash is not None:
            try:
                self.lease = self.gateway.acquire(
                    LeaseRequest(
                        holder=self.holder,
                        scope=self.config.lease_scope,
                        mode="exclusive",
                        priority=self.config.lease_priority,
                        ttl_ms=self.config.lease_ttl_ms,
                        deadman_required=True,
                        contract_hash=self._contract_hash,
                    )
                )
                self._renew_at_ns = self.clock.now_ns() + self.config.lease_ttl_ms * 333_333
            except GatewayError as exc:
                self._fail("LEASE_INVALID", str(exc))
                return self._drain()
        self.state = SessionState.IDLE
        self.deadman.block()
        self.last_intent = None
        self._active_mode = None
        self._release_seen = False
        self._lease_error = None
        events.append(self._event("SESSION_RESET", Severity.INFO))
        self._pending_events.extend(events)
        return tuple(events)

    def close(self) -> None:
        if self._closed:
            return
        if self.state in {SessionState.ACTIVE, SessionState.READY}:
            self.stop("close", system=False)
        self._release_lease()
        self.state = SessionState.CLOSED
        self._closed = True

    # ---- helpers ----

    def _drain(self) -> tuple[TeleopEvent, ...]:
        events = tuple(self._pending_events)
        self._pending_events.clear()
        return events

    def _next_wire_seq(self) -> int:
        value = self._wire_seq
        self._wire_seq += 1
        return value

    def _release_lease(self) -> None:
        if self.lease is not None:
            try:
                self.gateway.release(self.lease.lease_id)
            except GatewayError:
                pass
            self.lease = None

    def _lease_valid(self, now_ns: int | None = None) -> bool:
        if self.lease is None:
            return False
        now = self.clock.now_ns() if now_ns is None else int(now_ns)
        if now >= self.lease.expires_at_ns:
            self.lease = None
            return False
        if self._renew_at_ns is not None and now >= self._renew_at_ns:
            try:
                self.lease = self.gateway.renew(self.lease.lease_id, self.config.lease_ttl_ms)
                self._renew_at_ns = now + self.config.lease_ttl_ms * 333_333
            except GatewayError as exc:
                self._lease_error = str(exc)
                self.lease = None
                return False
        return True

    def _state_valid(self, now_ns: int | None = None) -> bool:
        try:
            state = self.gateway.state()
        except GatewayError:
            return False
        if not state.fresh or state.profile_hash != self.profile.profile_hash:
            return False
        now = self.clock.now_ns() if now_ns is None else int(now_ns)
        if state.stamp_ns > now or now - state.stamp_ns > self.guard.limits.state_age_max_ns:
            return False
        return True
