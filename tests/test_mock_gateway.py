from __future__ import annotations

import pytest

from jcheng_teleop.adapters.gateway.mock import MockGateway
from jcheng_teleop.core.clock import ManualClock
from jcheng_teleop.core.gateway import GatewayError, GatewayUnavailable
from jcheng_teleop.core.model import ActionIntent, LeaseRequest, Mode

CONTRACT = "sha256:" + "1" * 64
PROFILE = "sha256:" + "2" * 64


def _gateway():
    return MockGateway(ManualClock(0), contract_hash=CONTRACT, profile_hash=PROFILE, joint_count=2)


def _lease_request():
    return LeaseRequest(
        holder="teleop:test",
        scope="full",
        mode="exclusive",
        priority=40,
        ttl_ms=1000,
        deadman_required=True,
        contract_hash=CONTRACT,
    )


def _intent(lease_id: str = ""):
    return ActionIntent(
        mode=Mode.JOINT_VELOCITY,
        profile_id="p",
        profile_hash=PROFILE,
        deadman=True,
        t_source_ns=0,
        seq=1,
        joint_velocities_rad_s=(0.1, 0.0),
        lease_id=lease_id,
    )


def test_admission_identifies_mock():
    admission = _gateway().admit()
    assert admission.mock is True
    assert admission.capabilities == ("mock",)


def test_lease_lifecycle():
    gateway = _gateway()
    lease = gateway.acquire(_lease_request())
    assert gateway.renew(lease.lease_id, 2000).expires_at_ns == 2_000_000_000
    gateway.release(lease.lease_id)
    with pytest.raises(GatewayError):
        gateway.renew(lease.lease_id, 1000)


def test_lease_conflict():
    gateway = _gateway()
    gateway.acquire(_lease_request())
    with pytest.raises(GatewayError):
        gateway.acquire(_lease_request())


def test_revoked_lease_cannot_renew():
    gateway = _gateway()
    lease = gateway.acquire(_lease_request())
    gateway.revoke(lease.lease_id)
    with pytest.raises(GatewayError):
        gateway.renew(lease.lease_id, 1000)


def test_submit_completes_and_records():
    gateway = _gateway()
    lease = gateway.acquire(_lease_request())
    result = gateway.submit(_intent(lease.lease_id))
    assert result.outcome == "COMPLETED"
    assert len(gateway.submitted) == 1


def test_submit_unsupported_mode_rejected():
    gateway = _gateway()
    lease = gateway.acquire(_lease_request())
    intent = ActionIntent(
        mode=Mode.JOINT_POSITION,
        profile_id="p",
        profile_hash=PROFILE,
        deadman=True,
        t_source_ns=0,
        seq=1,
        joint_positions_rad=(0.1, 0.0),
        lease_id=lease.lease_id,
    )
    result = gateway.submit(intent)
    assert result.outcome == "REJECTED"
    assert result.reason_code == "UNKNOWN_KIND"


def test_unknown_and_busy_faults():
    gateway = _gateway()
    gateway.fail("submit_unknown")
    assert gateway.submit(_intent()).outcome == "UNKNOWN"
    gateway.clear_faults()
    gateway.fail("motion_busy")
    assert gateway.submit(_intent()).reason_code == "MOTION_BUSY"


def test_unavailable_submit():
    gateway = _gateway()
    gateway.fail("submit_unavailable")
    with pytest.raises(GatewayUnavailable):
        gateway.submit(_intent())


def test_state_stale_and_profile_hash():
    gateway = _gateway()
    assert gateway.state().fresh is True
    gateway.set_stale(True)
    assert gateway.state().fresh is False
    assert gateway.state().profile_hash == PROFILE
    assert gateway.state().truth == "mock"
    assert gateway.state().verification == "none"


def test_stop_returns_unconfirmed():
    gateway = _gateway()
    result = gateway.stop("operator")
    assert result.accepted is True
    assert result.confirmed is None
    assert gateway.stop_requests == ["operator"]


def test_submit_without_lease_is_rejected():
    gateway = _gateway()
    result = gateway.submit(_intent())
    assert result.outcome == "REJECTED"
    assert result.reason_code == "NO_LEASE"


def test_unleased_motion_intent_is_rejected():
    gateway = _gateway()
    intent = ActionIntent(
        mode=Mode.JOINT_VELOCITY,
        profile_id="p",
        profile_hash=PROFILE,
        deadman=False,
        t_source_ns=0,
        seq=1,
        joint_velocities_rad_s=(0.9, -0.9),
    )
    result = gateway.submit(intent)
    assert result.outcome == "REJECTED"
    assert result.reason_code == "INVALID_COMMAND"


def test_stop_intent_is_accepted_without_a_lease():
    gateway = _gateway()
    intent = ActionIntent(
        mode=Mode.JOINT_VELOCITY,
        profile_id="p",
        profile_hash=PROFILE,
        deadman=False,
        t_source_ns=0,
        seq=1,
        joint_velocities_rad_s=(0.0, 0.0),
        purpose="stop",
    )
    result = gateway.submit(intent)
    assert result.outcome == "COMPLETED"


def test_non_increasing_seq_is_rejected():
    gateway = _gateway()
    lease = gateway.acquire(_lease_request())
    first = gateway.submit(_intent(lease.lease_id))
    assert first.outcome == "COMPLETED"
    second = gateway.submit(_intent(lease.lease_id))
    assert second.outcome == "REJECTED"
    assert second.reason_code == "INVALID_COMMAND"
