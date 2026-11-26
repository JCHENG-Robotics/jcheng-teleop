"""M9 base intent guard tests (offline; no /cmd_vel, no device)."""

from __future__ import annotations

import pytest

from jcheng_teleop.core.base import (
    BaseIntent,
    BaseIntentError,
    BaseIntentState,
    accept_base_intent,
    validate_base_intent,
)

NOW = 10_000_000_000
HASH = "lease-1"


def _intent(**overrides) -> BaseIntent:
    base = dict(
        schema=BaseIntent.SCHEMA,
        session_id="session-m9",
        source="teleop",
        lease_id=HASH,
        seq=1,
        t_source_ns=NOW - 10_000_000,
        vx_m_s=0.1,
        vy_m_s=0.0,
        wz_rad_s=0.0,
        deadman=True,
        frame="base_link",
    )
    base.update(overrides)
    return BaseIntent(**base)


def test_valid_forward_intent_is_accepted() -> None:
    state = BaseIntentState()
    accepted = accept_base_intent(_intent(), now_ns=NOW, state=state)
    assert accepted.vx_m_s == 0.1
    assert state.last_seq == 1
    assert state.last_accepted_ns == NOW


def test_zero_intent_is_a_stop_and_needs_no_deadman() -> None:
    state = BaseIntentState()
    accept_base_intent(
        _intent(vx_m_s=0.0, deadman=False), now_ns=NOW, state=state
    )


def test_nonzero_intent_without_deadman_is_rejected() -> None:
    with pytest.raises(BaseIntentError, match="deadman"):
        validate_base_intent(
            _intent(deadman=False), now_ns=NOW, state=BaseIntentState()
        )


@pytest.mark.parametrize(
    "field,value",
    [("vx_m_s", 0.26), ("vy_m_s", 0.21), ("wz_rad_s", 0.61)],
)
def test_limits_are_enforced(field: str, value: float) -> None:
    with pytest.raises(BaseIntentError, match=field):
        validate_base_intent(
            _intent(**{field: value}), now_ns=NOW, state=BaseIntentState()
        )


def test_stale_input_is_rejected() -> None:
    with pytest.raises(BaseIntentError, match="older than"):
        validate_base_intent(
            _intent(t_source_ns=NOW - 600_000_000),
            now_ns=NOW,
            state=BaseIntentState(),
        )


def test_future_input_is_rejected() -> None:
    with pytest.raises(BaseIntentError, match="future"):
        validate_base_intent(
            _intent(t_source_ns=NOW + 1), now_ns=NOW, state=BaseIntentState()
        )


def test_sequence_must_increase() -> None:
    state = BaseIntentState(last_seq=2)
    with pytest.raises(BaseIntentError, match="seq must increase"):
        validate_base_intent(_intent(seq=2), now_ns=NOW, state=state)


def test_lease_is_required() -> None:
    with pytest.raises(BaseIntentError, match="lease_id"):
        validate_base_intent(
            _intent(lease_id=""), now_ns=NOW, state=BaseIntentState()
        )


def test_rate_above_20hz_is_rejected() -> None:
    state = BaseIntentState(last_accepted_ns=NOW)
    with pytest.raises(BaseIntentError, match="20 Hz"):
        validate_base_intent(_intent(seq=2), now_ns=NOW + 40_000_000, state=state)


def test_wrong_frame_is_rejected() -> None:
    with pytest.raises(BaseIntentError, match="base_link"):
        validate_base_intent(
            _intent(frame="map"), now_ns=NOW, state=BaseIntentState()
        )


def test_non_finite_values_are_rejected() -> None:
    with pytest.raises(BaseIntentError, match="finite"):
        validate_base_intent(
            _intent(vx_m_s=float("nan")), now_ns=NOW, state=BaseIntentState()
        )


def test_rejected_intent_does_not_advance_state() -> None:
    state = BaseIntentState()
    with pytest.raises(BaseIntentError):
        accept_base_intent(_intent(vx_m_s=9.0), now_ns=NOW, state=state)
    assert state.last_seq == -1
    assert state.last_accepted_ns is None
