"""M8 shared-authority state machine tests (offline, no motion)."""

from __future__ import annotations

import pytest

from jcheng_teleop.core.authority import (
    AuthorityConfig,
    AuthorityError,
    AuthorityMachine,
    AuthorityMode,
)

MS = 1_000_000
T0 = 1_000 * MS


def _machine() -> AuthorityMachine:
    return AuthorityMachine(AuthorityConfig(min_confidence=0.5))


def test_policy_owns_every_tick_and_coverage_is_complete() -> None:
    machine = _machine()
    tick = machine.start_policy(now_ns=T0, confidence=0.9, action_ref="act-1")
    assert tick.mode is AuthorityMode.POLICY
    assert tick.policy_weight == 1.0
    for index in range(1, 20):
        machine.policy_tick(
            now_ns=T0 + index * 20 * MS, confidence=0.9, action_ref=f"act-{index}"
        )
    coverage = machine.coverage(start_ns=T0, end_ns=T0 + 19 * 20 * MS, tick_ms=20)
    assert coverage["coverage_ratio"] == 1.0
    assert coverage["gaps"] == []


def test_takeover_is_immediate_and_keeps_the_policy_action() -> None:
    machine = _machine()
    machine.start_policy(now_ns=T0, confidence=0.9, action_ref="act-7")
    tick = machine.request_takeover(now_ns=T0 + 40 * MS)
    assert tick.mode is AuthorityMode.OPERATOR
    assert tick.operator_weight == 1.0
    assert tick.policy_weight == 0.0
    assert tick.correction is True
    assert tick.policy_action_ref == "act-7"
    assert tick.policy_stopped_at_ns - T0 <= 40 * MS
    assert tick.policy_stopped_at_ns - T0 <= 150 * MS


def test_operator_takeover_bound_over_20_trials() -> None:
    for trial in range(20):
        machine = _machine()
        start = T0 + trial * 1_000 * MS
        machine.start_policy(now_ns=start, confidence=0.9, action_ref="act")
        request = start + 40 * MS
        tick = machine.request_takeover(now_ns=request)
        assert tick.t_ns - request == 0
        assert tick.policy_stopped_at_ns == request
        assert tick.policy_stopped_at_ns - request <= 100 * MS


def test_low_confidence_at_start_does_not_enter_policy() -> None:
    machine = _machine()
    tick = machine.start_policy(now_ns=T0, confidence=0.2, action_ref="act")
    assert tick.mode is AuthorityMode.STOPPED
    assert tick.reason == "policy_low_confidence_at_start"


def test_low_confidence_hands_over_to_the_operator() -> None:
    machine = _machine()
    machine.start_policy(now_ns=T0, confidence=0.9, action_ref="act-1")
    tick = machine.policy_tick(
        now_ns=T0 + 20 * MS, confidence=0.1, action_ref="act-2", operator_present=True
    )
    assert tick.mode is AuthorityMode.OPERATOR
    assert tick.correction is True
    assert tick.reason == "policy_low_confidence"


def test_low_confidence_without_an_operator_stops() -> None:
    machine = _machine()
    machine.start_policy(now_ns=T0, confidence=0.9, action_ref="act-1")
    tick = machine.policy_tick(
        now_ns=T0 + 20 * MS, confidence=0.1, action_ref="act-2", operator_present=False
    )
    assert tick.mode is AuthorityMode.STOPPED
    assert tick.reason == "policy_low_confidence_no_operator"


def test_policy_fault_stops_and_records_the_reason() -> None:
    machine = _machine()
    machine.start_policy(now_ns=T0, confidence=0.9, action_ref="act-1")
    tick = machine.policy_fault(now_ns=T0 + 20 * MS, reason="nan_action")
    assert tick.mode is AuthorityMode.STOPPED
    assert tick.policy_stopped_at_ns == T0 + 20 * MS
    assert "nan_action" in tick.reason


def test_blend_weights_sum_to_one() -> None:
    machine = _machine()
    machine.start_policy(now_ns=T0, confidence=0.9, action_ref="act-1")
    tick = machine.blend(now_ns=T0 + 20 * MS, operator_weight=0.3)
    assert tick.mode is AuthorityMode.BLEND
    assert tick.operator_weight == pytest.approx(0.3)
    assert tick.policy_weight == pytest.approx(0.7)


def test_invalid_blend_weight_is_refused() -> None:
    machine = _machine()
    machine.start_policy(now_ns=T0, confidence=0.9, action_ref="act-1")
    with pytest.raises(AuthorityError, match="operator_weight"):
        machine.blend(now_ns=T0 + 20 * MS, operator_weight=1.5)


def test_policy_cannot_start_outside_stopped() -> None:
    machine = _machine()
    machine.start_policy(now_ns=T0, confidence=0.9, action_ref="act-1")
    with pytest.raises(AuthorityError, match="STOPPED"):
        machine.start_policy(now_ns=T0 + 20 * MS, confidence=0.9, action_ref="act-2")


def test_takeover_requires_an_active_policy() -> None:
    machine = _machine()
    machine.stop(now_ns=T0, reason="idle")
    with pytest.raises(AuthorityError, match="active policy"):
        machine.request_takeover(now_ns=T0 + 20 * MS)


def test_coverage_reports_a_gap() -> None:
    machine = _machine()
    machine.start_policy(now_ns=T0, confidence=0.9, action_ref="act-1")
    machine.stop(now_ns=T0 + 60 * MS, reason="manual")
    coverage = machine.coverage(start_ns=T0, end_ns=T0 + 60 * MS, tick_ms=20)
    assert coverage["coverage_ratio"] < 1.0
    assert coverage["gaps"]
