from __future__ import annotations

import pytest

from jcheng_teleop.core.model import ActionIntent, Mode, RejectedSample
from jcheng_teleop.core.safety import SafetyGuard
from conftest import write_resolved


def _intent(resolved, mode=Mode.JOINT_VELOCITY, **overrides):
    values = dict(
        mode=mode,
        profile_id=resolved.profile_id,
        profile_hash=resolved.profile_hash,
        deadman=True,
        t_source_ns=0,
        seq=1,
    )
    values.update(overrides)
    return ActionIntent(**values)


def test_velocity_guard_accepts_bounded(tmp_path):
    resolved = write_resolved(tmp_path, joints=2)
    guard = SafetyGuard(resolved)
    guard.validate(_intent(resolved, joint_velocities_rad_s=(0.5, -0.5)))


def test_velocity_guard_rejects_over_limit(tmp_path):
    resolved = write_resolved(tmp_path, joints=1)
    with pytest.raises(RejectedSample):
        SafetyGuard(resolved).validate(_intent(resolved, joint_velocities_rad_s=(5.0,)))


def test_position_guard_rejects_out_of_bounds(tmp_path):
    resolved = write_resolved(tmp_path, joints=1, modes=("JOINT_POSITION",))
    with pytest.raises(RejectedSample):
        SafetyGuard(resolved).validate(
            _intent(resolved, mode=Mode.JOINT_POSITION, joint_positions_rad=(9.0,))
        )


def test_profile_hash_guard(tmp_path):
    resolved = write_resolved(tmp_path, joints=1)
    with pytest.raises(RejectedSample):
        SafetyGuard(resolved).validate(
            _intent(resolved, profile_hash="sha256:" + "0" * 64, joint_velocities_rad_s=(0.1,))
        )


def test_stop_velocity_is_zero(tmp_path):
    resolved = write_resolved(tmp_path, joints=2)
    guard = SafetyGuard(resolved)
    last = _intent(resolved, joint_velocities_rad_s=(0.4, -0.2), gripper_normalized=0.5, gripper_valid=True)
    stop = guard.stop_intent(last, Mode.JOINT_VELOCITY, seq=2, t_source_ns=10)
    assert stop is not None
    assert stop.joint_velocities_rad_s == (0.0, 0.0)
    assert stop.deadman is False
    assert stop.gripper_normalized == 0.5


def test_stop_position_holds_last_target(tmp_path):
    resolved = write_resolved(tmp_path, joints=2, modes=("JOINT_POSITION",))
    guard = SafetyGuard(resolved)
    last = _intent(resolved, mode=Mode.JOINT_POSITION, joint_positions_rad=(0.3, 0.4))
    stop = guard.stop_intent(last, Mode.JOINT_POSITION, seq=2, t_source_ns=10)
    assert stop is not None
    assert stop.joint_positions_rad == (0.3, 0.4)
    assert stop.joint_velocities_rad_s == ()
    assert stop.deadman is False


def test_stop_position_without_target_is_none(tmp_path):
    resolved = write_resolved(tmp_path, joints=2, modes=("JOINT_POSITION",))
    assert SafetyGuard(resolved).stop_intent(None, Mode.JOINT_POSITION, seq=1, t_source_ns=1) is None
