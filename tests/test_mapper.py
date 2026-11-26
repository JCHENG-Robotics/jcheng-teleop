from __future__ import annotations

import pytest

from jcheng_teleop.core.conditioning import Conditioner
from jcheng_teleop.core.mapper import ActionMapper
from jcheng_teleop.core.model import Mode, RejectedSample
from conftest import make_sample, write_resolved


def test_velocity_mapping(tmp_path):
    resolved = write_resolved(tmp_path, joints=2)
    conditioned = Conditioner(resolved).process(make_sample(resolved, 0, values=(0.2, -0.3), gripper=0.4))
    intent = ActionMapper(resolved).map(conditioned)
    assert intent.mode is Mode.JOINT_VELOCITY
    assert intent.joint_velocities_rad_s == (0.2, -0.3)
    assert intent.gripper_normalized == 0.4
    assert intent.gripper_valid is True


def test_position_mapping_is_typed_not_converted(tmp_path):
    resolved = write_resolved(tmp_path, joints=2, modes=("JOINT_POSITION",))
    conditioned = Conditioner(resolved).process(
        make_sample(resolved, 0, values=(0.2, 0.3), mode=Mode.JOINT_POSITION)
    )
    intent = ActionMapper(resolved).map(conditioned)
    assert intent.mode is Mode.JOINT_POSITION
    assert intent.joint_positions_rad == (0.2, 0.3)
    assert intent.joint_velocities_rad_s == ()


def test_cartesian_mapping(tmp_path):
    from jcheng_teleop.core.model import CartesianTwist, InputSample

    resolved = write_resolved(tmp_path, joints=1, modes=("CARTESIAN_TWIST",))
    conditioned = Conditioner(resolved).process(
        InputSample(
            schema=InputSample.SCHEMA,
            source_id="s",
            source_class="virtual",
            seq=0,
            t_source_ns=0,
            t_host_mono_ns=0,
            mode=Mode.CARTESIAN_TWIST,
            cartesian_twist=CartesianTwist(linear_x=0.1, frame_id="base_link"),
            deadman=True,
        )
    )
    intent = ActionMapper(resolved).map(conditioned)
    assert intent.mode is Mode.CARTESIAN_TWIST
    assert intent.cartesian_twist is not None
    assert intent.frame_id == "base_link"


def test_cartesian_without_twist_rejected(tmp_path):
    from jcheng_teleop.core.model import InputSample

    with pytest.raises(ValueError):
        InputSample(
            schema=InputSample.SCHEMA,
            source_id="s",
            source_class="virtual",
            seq=0,
            t_source_ns=0,
            t_host_mono_ns=0,
            mode=Mode.CARTESIAN_TWIST,
            deadman=True,
        )
