from __future__ import annotations

import pytest

from jcheng_teleop.core.model import (
    CartesianTwist,
    InputSample,
    Mode,
)


def _sample(**overrides):
    values = dict(
        schema=InputSample.SCHEMA,
        source_id="src",
        source_class="virtual",
        seq=0,
        t_source_ns=0,
        t_host_mono_ns=0,
        mode=Mode.JOINT_VELOCITY,
        joint_velocities_rad_s=(0.1,),
        deadman=True,
    )
    values.update(overrides)
    return InputSample(**values)


def test_valid_sample_roundtrip():
    sample = _sample(gripper_normalized=0.5, gripper_valid=True)
    assert sample.to_dict()["mode"] == "JOINT_VELOCITY"
    restored = InputSample.from_mapping(sample.to_dict())
    assert restored == sample


def test_invalid_schema():
    with pytest.raises(ValueError):
        _sample(schema="other")


def test_missing_source_id():
    with pytest.raises(ValueError):
        _sample(source_id="")


def test_negative_seq():
    with pytest.raises(ValueError):
        _sample(seq=-1)


def test_nonfinite_value():
    with pytest.raises(ValueError):
        _sample(joint_velocities_rad_s=(float("nan"),))


def test_wrong_payload_for_mode():
    with pytest.raises(ValueError):
        _sample(mode=Mode.JOINT_VELOCITY, joint_velocities_rad_s=(), joint_positions_rad=(0.0,))


def test_cartesian_requires_twist():
    with pytest.raises(ValueError):
        _sample(mode=Mode.CARTESIAN_TWIST, joint_velocities_rad_s=())


def test_cartesian_frame_required():
    with pytest.raises(ValueError):
        CartesianTwist(frame_id="")


def test_gripper_validity():
    with pytest.raises(ValueError):
        _sample(gripper_normalized=0.5)
    with pytest.raises(ValueError):
        _sample(gripper_valid=True)
    with pytest.raises(ValueError):
        _sample(gripper_normalized=1.5, gripper_valid=True)
