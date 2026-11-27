"""Shared-autonomy authority state machine (M8, offline model).

Every tick has exactly one authority source: operator, policy, or an explicit
blend with weights that sum to one. There is no implicit mixing and no silent
switch: every transition carries a reason and, when it ends a policy episode,
the policy action reference. The model records who held authority; it does not
publish intent or move anything.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class AuthorityError(ValueError):
    pass

class AuthorityMode(str, Enum):
    STOPPED = "STOPPED"
    POLICY = "POLICY"
    OPERATOR = "OPERATOR"
    BLEND = "BLEND"


@dataclass(frozen=True)
class AuthorityTick:
    t_ns: int
    mode: AuthorityMode
    operator_weight: float
    policy_weight: float
    reason: str
    correction: bool = False
    policy_action_ref: str | None = None
    policy_stopped_at_ns: int | None = None

    def to_dict(self) -> dict:
        return {
            "t_ns": self.t_ns,
            "mode": self.mode.value,
            "operator_weight": self.operator_weight,
            "policy_weight": self.policy_weight,
            "reason": self.reason,
            "correction": self.correction,
            "policy_action_ref": self.policy_action_ref,
            "policy_stopped_at_ns": self.policy_stopped_at_ns,
        }


@dataclass
class AuthorityConfig:
    min_confidence: float = 0.5
    takeover_bound_ms: int = 100
    policy_stop_bound_ms: int = 150


@dataclass
class AuthorityMachine:
    config: AuthorityConfig = field(default_factory=AuthorityConfig)
    mode: AuthorityMode = AuthorityMode.STOPPED
    log: list[AuthorityTick] = field(default_factory=list)
    _policy_action_ref: str | None = None

    def _record(
        self,
        *,
        now_ns: int,
        mode: AuthorityMode,
        operator_weight: float,
        policy_weight: float,
        reason: str,
        correction: bool = False,
        policy_stopped_at_ns: int | None = None,
    ) -> AuthorityTick:
        if mode is AuthorityMode.STOPPED:
            if operator_weight != 0.0 or policy_weight != 0.0:
                raise AuthorityError("STOPPED must have zero weights")
        else:
            if abs((operator_weight + policy_weight) - 1.0) > 1e-9:
                raise AuthorityError("authority weights must sum to 1")
            if operator_weight < 0 or policy_weight < 0:
                raise AuthorityError("authority weights must be non-negative")
        tick = AuthorityTick(
            t_ns=int(now_ns),
            mode=mode,
            operator_weight=float(operator_weight),
            policy_weight=float(policy_weight),
            reason=reason,
            correction=bool(correction),
            policy_action_ref=self._policy_action_ref,
            policy_stopped_at_ns=policy_stopped_at_ns,
        )
        self.mode = mode
        self.log.append(tick)
        return tick

    def start_policy(self, *, now_ns: int, confidence: float, action_ref: str) -> AuthorityTick:
        if self.mode is not AuthorityMode.STOPPED:
            raise AuthorityError("policy can only start from STOPPED")
        if not action_ref:
            raise AuthorityError("a policy action reference is required")
        if not 0.0 <= confidence <= 1.0:
            raise AuthorityError("confidence must be in [0, 1]")
        if confidence < self.config.min_confidence:
            self._policy_action_ref = action_ref
            return self._record(
                now_ns=now_ns,
                mode=AuthorityMode.STOPPED,
                operator_weight=0.0,
                policy_weight=0.0,
                reason="policy_low_confidence_at_start",
            )
        self._policy_action_ref = action_ref
        return self._record(
            now_ns=now_ns,
            mode=AuthorityMode.POLICY,
            operator_weight=0.0,
            policy_weight=1.0,
            reason="policy_started",
        )

    def policy_tick(
        self,
        *,
        now_ns: int,
        confidence: float,
        action_ref: str,
        operator_present: bool = True,
    ) -> AuthorityTick:
        if self.mode is not AuthorityMode.POLICY:
            raise AuthorityError("policy tick requires POLICY mode")
        if action_ref:
            self._policy_action_ref = action_ref
        if confidence < self.config.min_confidence:
            return self.handover(
                now_ns=now_ns,
                reason="policy_low_confidence",
                operator_present=operator_present,
            )
        return self._record(
            now_ns=now_ns,
            mode=AuthorityMode.POLICY,
            operator_weight=0.0,
            policy_weight=1.0,
            reason="policy_tick",
        )

    def request_takeover(self, *, now_ns: int, operator_present: bool = True) -> AuthorityTick:
        """Operator takeover; the policy stops on this tick."""
        if self.mode not in {AuthorityMode.POLICY, AuthorityMode.BLEND}:
            raise AuthorityError("takeover requires an active policy or blend")
        if not operator_present:
            raise AuthorityError("takeover requires a present operator")
        was_policy = self.mode is AuthorityMode.POLICY or self.mode is AuthorityMode.BLEND
        return self._record(
            now_ns=now_ns,
            mode=AuthorityMode.OPERATOR,
            operator_weight=1.0,
            policy_weight=0.0,
            reason="operator_takeover",
            correction=was_policy,
            policy_stopped_at_ns=int(now_ns),
        )

    def handover(
        self, *, now_ns: int, reason: str, operator_present: bool
    ) -> AuthorityTick:
        """Policy yields: to the operator if present, otherwise to STOPPED."""
        if self.mode not in {AuthorityMode.POLICY, AuthorityMode.BLEND}:
            raise AuthorityError("handover requires an active policy or blend")
        if operator_present:
            return self._record(
                now_ns=now_ns,
                mode=AuthorityMode.OPERATOR,
                operator_weight=1.0,
                policy_weight=0.0,
                reason=reason,
                correction=True,
                policy_stopped_at_ns=int(now_ns),
            )
        return self._record(
            now_ns=now_ns,
            mode=AuthorityMode.STOPPED,
            operator_weight=0.0,
            policy_weight=0.0,
            reason=f"{reason}_no_operator",
            policy_stopped_at_ns=int(now_ns),
        )

    def policy_fault(self, *, now_ns: int, reason: str) -> AuthorityTick:
        if self.mode not in {AuthorityMode.POLICY, AuthorityMode.BLEND}:
            raise AuthorityError("policy fault requires an active policy or blend")
        return self._record(
            now_ns=now_ns,
            mode=AuthorityMode.STOPPED,
            operator_weight=0.0,
            policy_weight=0.0,
            reason=f"policy_fault:{reason}",
            policy_stopped_at_ns=int(now_ns),
        )

    def operator_tick(self, *, now_ns: int, reason: str = "operator_tick") -> AuthorityTick:
        if self.mode is not AuthorityMode.OPERATOR:
            raise AuthorityError("operator tick requires OPERATOR mode")
        return self._record(
            now_ns=now_ns,
            mode=AuthorityMode.OPERATOR,
            operator_weight=1.0,
            policy_weight=0.0,
            reason=reason,
        )

    def blend(self, *, now_ns: int, operator_weight: float) -> AuthorityTick:
        if self.mode not in {AuthorityMode.POLICY, AuthorityMode.OPERATOR, AuthorityMode.BLEND}:
            raise AuthorityError("blend requires an active authority")
        if not 0.0 <= operator_weight <= 1.0:
            raise AuthorityError("operator_weight must be in [0, 1]")
        return self._record(
            now_ns=now_ns,
            mode=AuthorityMode.BLEND,
            operator_weight=operator_weight,
            policy_weight=1.0 - operator_weight,
            reason="explicit_blend",
        )

    def stop(self, *, now_ns: int, reason: str) -> AuthorityTick:
        self._policy_action_ref = None
        return self._record(
            now_ns=now_ns,
            mode=AuthorityMode.STOPPED,
            operator_weight=0.0,
            policy_weight=0.0,
            reason=reason,
            policy_stopped_at_ns=int(now_ns)
            if self.mode in {AuthorityMode.POLICY, AuthorityMode.BLEND}
            else None,
        )

    def coverage(self, *, start_ns: int, end_ns: int, tick_ms: int) -> dict:
        """Report authority coverage over a time window."""
        if tick_ms <= 0 or end_ns <= start_ns:
            raise AuthorityError("invalid coverage window")
        expected = (end_ns - start_ns) // (tick_ms * 1_000_000) + 1
        covered = [
            tick for tick in self.log if start_ns <= tick.t_ns <= end_ns
        ]
        ticks = {tick.t_ns for tick in covered}
        gaps = [
            start_ns + index * tick_ms * 1_000_000
            for index in range(expected)
            if start_ns + index * tick_ms * 1_000_000 not in ticks
        ]
        return {
            "expected_ticks": expected,
            "covered_ticks": len(covered),
            "coverage_ratio": len(covered) / expected,
            "gaps": gaps[:10],
        }
