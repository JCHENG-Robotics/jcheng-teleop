from __future__ import annotations

import pytest

from jcheng_teleop.core.conditioning import Conditioner
from jcheng_teleop.core.model import Mode, RejectedSample, RejectionCode
from conftest import make_sample, write_resolved


def test_deadzone_and_hysteresis(tmp_path):
    resolved = write_resolved(tmp_path, joints=1, deadzone=0.05, hysteresis=0.02)
    conditioner = Conditioner(resolved)
    assert conditioner.process(make_sample(resolved, 0, values=(0.04,))).values == (0.0,)
    assert conditioner.process(make_sample(resolved, 1, values=(0.06,))).values == (0.0,)
    assert conditioner.process(make_sample(resolved, 2, values=(0.10,))).values == (0.10,)
    assert conditioner.process(make_sample(resolved, 3, values=(0.06,))).values == (0.06,)
    assert conditioner.process(make_sample(resolved, 4, values=(0.04,))).values == (0.0,)


def test_velocity_limit_and_single_event(tmp_path):
    resolved = write_resolved(tmp_path, joints=1)
    conditioner = Conditioner(resolved)
    first = conditioner.process(make_sample(resolved, 0, values=(10.0,)))
    assert first.values == (1.2,)
    assert [event.code for event in first.events] == ["LIMIT_CLAMPED"]
    second = conditioner.process(make_sample(resolved, 1, values=(9.0,)))
    assert second.values == (1.2,)
    assert second.events == ()
    third = conditioner.process(make_sample(resolved, 2, values=(0.0,)))
    assert third.values == (0.0,)
    fourth = conditioner.process(make_sample(resolved, 3, values=(10.0,)))
    assert [event.code for event in fourth.events] == ["LIMIT_CLAMPED"]


def test_position_limit(tmp_path):
    resolved = write_resolved(tmp_path, joints=1, modes=("JOINT_POSITION",))
    conditioner = Conditioner(resolved)
    result = conditioner.process(make_sample(resolved, 0, values=(9.0,), mode=Mode.JOINT_POSITION))
    assert result.values == (1.8,)
    assert result.events[0].code == "LIMIT_CLAMPED"


def test_duplicate_and_rollback_seq(tmp_path):
    resolved = write_resolved(tmp_path, joints=1)
    conditioner = Conditioner(resolved)
    conditioner.process(make_sample(resolved, 5))
    with pytest.raises(RejectedSample) as duplicate:
        conditioner.process(make_sample(resolved, 5))
    assert duplicate.value.code == RejectionCode.SEQ_DUPLICATE.value
    with pytest.raises(RejectedSample) as rollback:
        conditioner.process(make_sample(resolved, 4))
    assert rollback.value.code == RejectionCode.SEQ_GAP.value


def test_stamp_rollback(tmp_path):
    resolved = write_resolved(tmp_path, joints=1)
    conditioner = Conditioner(resolved)
    conditioner.process(make_sample(resolved, 0, t_ns=20))
    with pytest.raises(RejectedSample) as exc:
        conditioner.process(make_sample(resolved, 1, t_ns=10))
    assert exc.value.code == RejectionCode.STAMP_ROLLBACK.value


def test_mode_not_enabled(tmp_path):
    resolved = write_resolved(tmp_path, joints=1, modes=("JOINT_VELOCITY",))
    conditioner = Conditioner(resolved)
    with pytest.raises(RejectedSample) as exc:
        conditioner.process(make_sample(resolved, 0, values=(0.1,), mode=Mode.JOINT_POSITION))
    assert exc.value.code == RejectionCode.MODE_UNSUPPORTED.value


def test_profile_mismatch(tmp_path):
    resolved = write_resolved(tmp_path, joints=1)
    conditioner = Conditioner(resolved)
    with pytest.raises(RejectedSample) as exc:
        conditioner.process(make_sample(resolved, 0, profile_id="other"))
    assert exc.value.code == RejectionCode.PROFILE_MISMATCH.value


def test_gripper_requires_binding(tmp_path):
    resolved = write_resolved(tmp_path, joints=1, gripper=False)
    conditioner = Conditioner(resolved)
    with pytest.raises(RejectedSample):
        conditioner.process(make_sample(resolved, 0, gripper=0.5))


def test_gripper_maps_to_normalized(tmp_path):
    resolved = write_resolved(tmp_path, joints=1)
    conditioner = Conditioner(resolved)
    result = conditioner.process(make_sample(resolved, 0, gripper=0.75))
    assert result.gripper_normalized == 0.75


def test_large_forward_gap_is_rejected(tmp_path):
    resolved = write_resolved(tmp_path, joints=1)
    conditioner = Conditioner(resolved, max_seq_gap=5)
    conditioner.process(make_sample(resolved, 0))
    with pytest.raises(RejectedSample) as exc:
        conditioner.process(make_sample(resolved, 10))
    assert exc.value.code == RejectionCode.SEQ_GAP.value
